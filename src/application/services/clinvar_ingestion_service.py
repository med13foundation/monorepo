"""Application service for orchestrating ClinVar ingestion per data source."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities import data_source_configs, user_data_source
from src.domain.services.clinvar_ingestion import (
    ClinVarGateway,
    ClinVarIngestionSummary,
)
from src.type_definitions.ingestion import RawRecord as IngestionRawRecord
from src.type_definitions.json_utils import to_json_value
from src.type_definitions.storage import StorageUseCase

if TYPE_CHECKING:
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.application.services.storage_configuration_service import (
        StorageConfigurationService,
    )
    from src.type_definitions.common import JSONObject, RawRecord

logger = logging.getLogger(__name__)


class ClinVarIngestionService:
    """Coordinate fetching, transforming, and persisting ClinVar data per source."""

    def __init__(
        self,
        gateway: ClinVarGateway,
        pipeline: IngestionPipelinePort,
        storage_service: StorageConfigurationService | None = None,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline
        self._storage_service = storage_service

    async def ingest(
        self,
        source: user_data_source.UserDataSource,
    ) -> ClinVarIngestionSummary:
        """Execute ingestion for a ClinVar data source."""
        self._assert_source_type(source)
        config = self._build_config(source.configuration)

        raw_records_data = await self._gateway.fetch_records(config)

        if self._storage_service:
            await self._persist_raw_records(raw_records_data, source)

        raw_records = self._to_pipeline_records(
            raw_records_data,
            original_source_id=str(source.id),
        )

        observations_created = 0
        if source.research_space_id is not None:
            result = self._pipeline.run(
                raw_records,
                research_space_id=str(source.research_space_id),
            )
            observations_created = result.observations_created
        else:
            logger.warning(
                "ClinVar source %s has no research_space_id; skipping kernel pipeline",
                source.id,
            )

        return ClinVarIngestionSummary(
            source_id=source.id,
            fetched_records=len(raw_records),
            parsed_publications=len(raw_records),
            created_publications=observations_created,
            updated_publications=0,
            created_publication_ids=(),
            updated_publication_ids=(),
            executed_query=config.query,
        )

    def _to_pipeline_records(
        self,
        records: list[JSONObject],
        *,
        original_source_id: str,
    ) -> list[IngestionRawRecord]:
        """Adapt ClinVar JSON records into the kernel ingestion pipeline format."""
        raw_records: list[IngestionRawRecord] = []
        for record in records:
            clinvar_id = record.get("clinvar_id")
            record_id = (
                clinvar_id
                if isinstance(clinvar_id, str) and clinvar_id.strip()
                else str(uuid4())
            )
            payload = self._extract_pipeline_payload(record)

            raw_records.append(
                IngestionRawRecord(
                    source_id=record_id,
                    data=payload,
                    metadata={
                        "original_source_id": original_source_id,
                        "type": "clinvar",
                        "entity_type": "VARIANT",
                        "clinvar_id": payload.get("clinvar_id"),
                        "gene_symbol": payload.get("gene_symbol"),
                        "clinical_significance": payload.get(
                            "clinical_significance",
                        ),
                    },
                ),
            )

        return raw_records

    @staticmethod
    def _extract_pipeline_payload(record: JSONObject) -> JSONObject:
        payload: JSONObject = {}
        parsed_data = record.get("parsed_data")
        if isinstance(parsed_data, dict):
            for key, value in parsed_data.items():
                payload[str(key)] = to_json_value(value)

        for key in (
            "clinvar_id",
            "source",
            "fetched_at",
            "gene_symbol",
            "variant_type",
            "clinical_significance",
            "review_status",
        ):
            value = record.get(key)
            if value is not None:
                payload[key] = to_json_value(value)

        if payload:
            return payload

        for key, value in record.items():
            payload[str(key)] = to_json_value(value)
        return payload

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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(list(records), tmp, default=str)
            tmp_path = Path(tmp.name)

        try:
            timestamp = source.updated_at.strftime("%Y%m%d_%H%M%S")
            key = f"clinvar/{source.id}/raw/{timestamp}_{uuid4().hex[:8]}.json"

            await self._storage_service.record_store_operation(
                configuration=backend,
                key=key,
                file_path=tmp_path,
                content_type="application/json",
                user_id=source.owner_id,
                metadata={
                    "source_id": str(source.id),
                    "record_count": len(records),
                },
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    @staticmethod
    def _build_config(
        source_config: user_data_source.SourceConfiguration,
    ) -> data_source_configs.ClinVarQueryConfig:
        metadata = source_config.metadata or {}
        return data_source_configs.ClinVarQueryConfig.model_validate(metadata)

    @staticmethod
    def _assert_source_type(source: user_data_source.UserDataSource) -> None:
        if source.source_type != user_data_source.SourceType.CLINVAR:
            msg = (
                "ClinVar ingestion can only run for ClinVar sources "
                f"(got {source.source_type.value})"
            )
            raise ValueError(msg)
