"""Application service for orchestrating PubMed ingestion per data source."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities import data_source_configs, publication, user_data_source
from src.domain.services.pubmed_ingestion import PubMedGateway, PubMedIngestionSummary
from src.domain.transform.transformers.pubmed_record_transformer import (
    PubMedRecordTransformer,
)
from src.type_definitions.ingestion import RawRecord as IngestionRawRecord
from src.type_definitions.storage import StorageUseCase

# Confidence threshold below which queries are logged as warnings
LOW_CONFIDENCE_THRESHOLD = 0.5

if TYPE_CHECKING:
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.domain.agents.ports.query_agent_port import QueryAgentPort
    from src.domain.repositories import PublicationRepository, ResearchSpaceRepository
    from src.type_definitions.common import (
        JSONObject,
        PublicationUpdate,
        RawRecord,
        SourceMetadata,
    )

logger = logging.getLogger(__name__)


class PubMedIngestionService:
    """Coordinate fetching, transforming, and persisting PubMed data per source."""

    def __init__(  # noqa: PLR0913
        self,
        gateway: PubMedGateway,
        pipeline: IngestionPipelinePort,
        publication_repository: (
            PublicationRepository | None
        ) = None,  # Optional/Deprecated
        transformer: PubMedRecordTransformer | None = None,  # Optional/Deprecated
        storage_service: StorageConfigurationService | None = None,
        query_agent: QueryAgentPort | None = None,
        research_space_repository: ResearchSpaceRepository | None = None,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline
        self._publication_repository = publication_repository
        self._transformer = transformer or PubMedRecordTransformer()
        self._storage_service = storage_service
        self._query_agent = query_agent
        self._research_space_repository = research_space_repository

    async def ingest(
        self,
        source: user_data_source.UserDataSource,
    ) -> PubMedIngestionSummary:
        """Execute ingestion for a PubMed data source."""
        self._assert_source_type(source)
        config = self._build_config(source.configuration)

        # AI-Managed Logic (Preserved)
        if (
            config.agent_config.is_ai_managed
            and self._query_agent
            and self._research_space_repository
        ):
            research_space_description = ""
            if (
                config.agent_config.use_research_space_context
                and source.research_space_id
            ):
                space = self._research_space_repository.find_by_id(
                    source.research_space_id,
                )
                if space:
                    research_space_description = space.description

            # Generate intelligent query using the new contract-based interface
            contract = await self._query_agent.generate_query(
                research_space_description=research_space_description,
                user_instructions=config.agent_config.agent_prompt,
                source_type="pubmed",
                model_id=config.agent_config.model_id,
            )

            if contract.decision == "generated" and contract.query:
                # Override static query with AI-generated one
                config = config.model_copy(update={"query": contract.query})
            elif contract.decision == "escalate":
                logger.warning(
                    "AI query generation escalated: %s (confidence=%.2f)",
                    contract.rationale,
                    contract.confidence_score,
                )
            elif contract.confidence_score < LOW_CONFIDENCE_THRESHOLD:
                logger.warning(
                    "Low confidence AI query (%.2f): %s",
                    contract.confidence_score,
                    contract.rationale,
                )

        raw_records_data = await self._gateway.fetch_records(config)

        # Persist raw records if a storage backend is configured (Preserved)
        if self._storage_service:
            await self._persist_raw_records(raw_records_data, source)

        # Convert gateway JSON records to pipeline RawRecord contracts.
        raw_records = self._to_pipeline_records(
            raw_records_data,
            original_source_id=str(source.id),
        )

        observations_created = 0

        # Run kernel pipeline only when the source is scoped to a research space.
        # Some legacy workflows still create PubMed sources without a space.
        if source.research_space_id is not None:
            result = self._pipeline.run(
                raw_records,
                research_space_id=str(source.research_space_id),
            )
            observations_created = result.observations_created
        else:
            logger.warning(
                "PubMed source %s has no research_space_id; skipping kernel pipeline",
                source.id,
            )

        # Map IngestResult to PubMedIngestionSummary
        # Note: PubMedIngestionSummary expects created_publication_ids (ints)
        # But pipeline works with UUIDs.
        # We might need to adjust the Summary or return simplified summary.
        # For now, we return placeholder counts.

        return PubMedIngestionSummary(
            source_id=source.id,
            fetched_records=len(raw_records),
            parsed_publications=len(raw_records),  # parsed = fetched
            created_publications=observations_created,  # kernel observations created
            updated_publications=0,
            created_publication_ids=(),  # Pipeline uses UUIDs, Summary expects ints?
            updated_publication_ids=(),
            executed_query=config.query,
        )

    def _to_pipeline_records(
        self,
        records: list[JSONObject],
        *,
        original_source_id: str,
    ) -> list[IngestionRawRecord]:
        """
        Adapt PubMed JSON records into the kernel ingestion pipeline record format.

        This lives in the application layer (not infrastructure) because it is a
        coordination concern: converting a gateway response into a pipeline input.
        """
        raw_records: list[IngestionRawRecord] = []
        for record in records:
            pmid = record.get("pmid")
            record_id = pmid if isinstance(pmid, str) and pmid.strip() else str(uuid4())

            raw_records.append(
                IngestionRawRecord(
                    source_id=record_id,
                    data=record,
                    metadata={
                        "original_source_id": original_source_id,
                        "type": "pubmed",
                        "entity_type": "PUBLICATION",
                        "pmid": record.get("pmid"),
                        "doi": record.get("doi"),
                    },
                ),
            )

        return raw_records

    async def _persist_raw_records(
        self,
        records: list[RawRecord],
        source: user_data_source.UserDataSource,
    ) -> None:
        """Persist raw records to storage if backend is available."""
        if not self._storage_service:
            return

        backend = self._storage_service.resolve_backend_for_use_case(
            StorageUseCase.RAW_SOURCE,
        )
        if not backend:
            return

        # Create a temporary file to store the raw records
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(list(records), tmp, default=str)
            tmp_path = Path(tmp.name)

        try:
            # Generate a unique key for this ingestion run
            timestamp = source.updated_at.strftime("%Y%m%d_%H%M%S")
            key = f"pubmed/{source.id}/raw/{timestamp}_{uuid4().hex[:8]}.json"

            await self._storage_service.record_store_operation(
                configuration=backend,
                key=key,
                file_path=tmp_path,
                content_type="application/json",
                user_id=source.owner_id,
                metadata={
                    "source_id": str(source.id),
                    "record_count": len(list(records)),
                },
            )
        finally:
            # clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()

    def _transform_records(
        self,
        records: list[RawRecord],
    ) -> list[publication.Publication]:
        transformed: list[publication.Publication] = []
        for record in records:
            try:
                publication = self._transformer.to_publication(record)
            except ValueError:
                continue
            transformed.append(publication)
        return transformed

    def _persist_publications(
        self,
        publications: list[publication.Publication],
    ) -> tuple[int, int, tuple[int, ...], tuple[int, ...]]:
        created = 0
        updated = 0
        created_ids: list[int] = []
        updated_ids: list[int] = []

        if not self._publication_repository:
            logger.warning(
                "Publication repository not configured, skipping persistence.",
            )
            return created, updated, tuple(created_ids), tuple(updated_ids)

        for publication_record in publications:
            pmid = publication_record.identifier.pubmed_id
            if pmid and (existing := self._publication_repository.find_by_pmid(pmid)):
                if existing.id is None:
                    continue
                updates = self._build_update_payload(publication_record)
                updated_entity = self._publication_repository.update_publication(
                    existing.id,
                    updates,
                )
                if updated_entity.id is not None:
                    updated_ids.append(updated_entity.id)
                updated += 1
            else:
                created_entity = self._publication_repository.create(publication_record)
                if created_entity.id is not None:
                    created_ids.append(created_entity.id)
                created += 1
        return created, updated, tuple(created_ids), tuple(updated_ids)

    @staticmethod
    def _build_update_payload(
        publication: publication.Publication,
    ) -> PublicationUpdate:
        return {
            "title": publication.title,
            "authors": list(publication.authors),
            "journal": publication.journal,
            "publication_year": publication.publication_year,
            "abstract": publication.abstract,
            "doi": publication.identifier.doi,
            "pmid": publication.identifier.pubmed_id,
        }

    @staticmethod
    def _build_config(
        configuration: user_data_source.SourceConfiguration,
    ) -> data_source_configs.PubMedQueryConfig:
        metadata: SourceMetadata = dict(configuration.metadata or {})
        if configuration.query:
            metadata["query"] = configuration.query
        return data_source_configs.PubMedQueryConfig.model_validate(metadata)

    @staticmethod
    def _assert_source_type(source: user_data_source.UserDataSource) -> None:
        if source.source_type != user_data_source.SourceType.PUBMED:
            message = (
                f"PubMed ingestion can only be executed for PubMed sources "
                f"(got {source.source_type.value})"
            )
            raise ValueError(message)
