"""
Orchestrator for the kernel ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
                # 0. Track Provenance (Source Level)
                # We create a provenance record for this source record
                provenance_id = self.provenance_tracker.track_ingestion(
                    research_space_id=research_space_id,
                    source_type="PIPELINE_INGESTION",  # or from record.metadata
                    source_ref=record.source_id,
                    raw_input=record.data,
                    # agent_model, mapping_method could be passed if available
                )

                # 1. Map
                mapped_observations = self.mapper.map(record)
                if not mapped_observations:
                    continue

                # 2. Resolve subject entity once per source record.
                entity_type = record.metadata.get("entity_type")
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

                for observation in mapped_observations:
                    # 3. Normalize
                    normalized = self.normalizer.normalize(observation)

                    # 4. Validate
                    if self.validator.validate(normalized):
                        # 5. Persist
                        self.observation_service.record_observation_value(
                            research_space_id=research_space_id,
                            subject_id=resolved_entity.id,
                            variable_id=normalized.variable_id,
                            value=normalized.value,
                            unit=normalized.unit,
                            observed_at=normalized.observed_at,
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
