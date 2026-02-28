"""
Orchestrator for the kernel ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.services.domain_context_resolver import DomainContextResolver
from src.infrastructure.ingestion.types import IngestResult, RawRecord

if TYPE_CHECKING:
    from src.application.services.kernel.kernel_observation_service import (
        KernelObservationService,
    )
    from src.infrastructure.ingestion.interfaces import (
        Mapper,
        Normalizer,
        Resolver,
        Validator,
    )
    from src.infrastructure.ingestion.provenance.tracker import ProvenanceTracker

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Orchestrates the ingestion process: Map -> Normalize -> Resolve -> Validate.
    """

    def __init__(  # noqa: PLR0913
        self,
        mapper: Mapper,
        normalizer: Normalizer,
        resolver: Resolver,
        validator: Validator,
        observation_service: KernelObservationService,
        provenance_tracker: ProvenanceTracker,
    ) -> None:
        self.mapper = mapper
        self.normalizer = normalizer
        self.resolver = resolver
        self.validator = validator
        self.observation_service = observation_service
        self.provenance_tracker = provenance_tracker

    def run(self, records: list[RawRecord], research_space_id: str) -> IngestResult:
        """
        Run the ingestion pipeline on a batch of records.

        Args:
            records: List of raw records to process.
            research_space_id: The research space ID to ingest data into.

        Returns:
            IngestResult summarizing the outcome.
        """
        result = IngestResult(success=True)

        for record in records:
            try:
                resolved_record = self._normalize_domain_context_metadata(record)

                # 0. Track Provenance (Source Level)
                # We create a provenance record for this source record
                provenance_id = self.provenance_tracker.track_ingestion(
                    research_space_id=research_space_id,
                    source_type="PIPELINE_INGESTION",  # or from record.metadata
                    source_ref=resolved_record.source_id,
                    raw_input=resolved_record.data,
                    # agent_model, mapping_method could be passed if available
                )

                # 1. Map
                mapped_observations = self.mapper.map(resolved_record)
                if not mapped_observations:
                    continue

                # 2. Resolve subject entity once per source record.
                entity_type = resolved_record.metadata.get("entity_type")
                if not isinstance(entity_type, str) or not entity_type.strip():
                    result.errors.append("Missing entity_type")
                    continue

                subject_anchor = mapped_observations[0].subject_anchor
                if not subject_anchor:
                    result.errors.append("Missing subject anchor")
                    continue

                resolved_entity = self.resolver.resolve(
                    anchor=subject_anchor,
                    entity_type=entity_type,
                    research_space_id=research_space_id,
                )
                if resolved_entity.created:
                    result.entities_created += 1
                if resolved_entity.id not in result.entity_ids_touched:
                    result.entity_ids_touched.append(resolved_entity.id)

                for observation in mapped_observations:
                    # 3. Normalize
                    normalized = self.normalizer.normalize(observation)

                    # 4. Validate
                    validated = self.validator.validate(normalized)
                    if validated is not None:
                        # 5. Persist
                        self.observation_service.record_observation_value(
                            research_space_id=research_space_id,
                            subject_id=resolved_entity.id,
                            variable_id=validated.variable_id,
                            value=validated.value,
                            unit=validated.unit,
                            observed_at=validated.observed_at,
                            provenance_id=provenance_id,
                        )
                        result.observations_created += 1
                    else:
                        result.errors.append(
                            f"Validation failed for {normalized.variable_id}",
                        )

            except Exception as e:
                logger.exception("Error processing record %s", record.source_id)
                result.errors.append(f"Error processing {record.source_id}: {e!s}")
                result.success = False

        return result

    @staticmethod
    def _normalize_domain_context_metadata(record: RawRecord) -> RawRecord:
        """
        Canonicalize domain metadata without source-specific behavior.

        Source connectors are responsible for enforcing domain requirements.
        """
        explicit_domain_context = DomainContextResolver.from_metadata(record.metadata)
        if explicit_domain_context is None:
            return record

        raw_domain_context = record.metadata.get("domain_context")
        current_domain_context = DomainContextResolver.normalize(
            raw_domain_context if isinstance(raw_domain_context, str) else None,
        )
        if current_domain_context == explicit_domain_context:
            return record

        enriched_metadata = dict(record.metadata)
        enriched_metadata["domain_context"] = explicit_domain_context
        return RawRecord(
            source_id=record.source_id,
            data=record.data,
            metadata=enriched_metadata,
        )
