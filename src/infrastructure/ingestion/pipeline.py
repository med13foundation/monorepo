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

    def run(self, records: list[RawRecord], study_id: str) -> IngestResult:
        """
        Run the ingestion pipeline on a batch of records.

        Args:
            records: List of raw records to process.
            study_id: The study ID to ingest data into.

        Returns:
            IngestResult summarizing the outcome.
        """
        result = IngestResult(success=True)

        for record in records:
            try:
                # 0. Track Provenance (Source Level)
                # We create a provenance record for this source record
                provenance_id = self.provenance_tracker.track_ingestion(
                    study_id=study_id,
                    source_type="PIPELINE_INGESTION",  # or from record.metadata
                    source_ref=record.source_id,
                    raw_input=record.data,
                    # agent_model, mapping_method could be passed if available
                )

                # 1. Map
                mapped_observations = self.mapper.map(record)

                for observation in mapped_observations:
                    # 2. Normalize
                    normalized = self.normalizer.normalize(observation)

                    # 3. Resolve Subject
                    # Resolve the entity to get a stable Kernel ID
                    if not normalized.subject_anchor:
                        result.errors.append("Missing subject anchor")
                        continue

                    # We assume the entity_type is implied by the variable's domain or context,
                    # OR the mapper could return it?
                    # Actually, the anchor might imply it, or we default to something.
                    # MappedObservation doesn't currently carry entity_type.
                    # We might need to look it up from the variable?
                    # Or pass it in.

                    # Hack/Assumption: For now, we try to guess or use a default if not present.
                    # Better: MappedObservation should have `subject_entity_type`?
                    # Or VariableDefinition has `domain_context`.

                    # For this phase, let's assume the Anchor has explicit "type" or we try to resolve
                    # based on keys.
                    # 4. Resolve entities
                    # We need an entity type from somewhere. metadata?
                    entity_type = record.metadata.get("entity_type")
                    if not isinstance(entity_type, str):
                        continue

                    resolved_entity = self.resolver.resolve(
                        anchor=normalized.subject_anchor,
                        entity_type=entity_type,
                        study_id=study_id,
                    )

                    # 4. Validate
                    if self.validator.validate(normalized):
                        # 5. Persist
                        self.observation_service.record_observation(
                            study_id=study_id,
                            subject_id=resolved_entity.id,
                            variable_id=normalized.variable_id,
                            value_numeric=self._extract_numeric(normalized.value),
                            value_text=self._extract_text(normalized.value),
                            value_date=normalized.observed_at,  # or from value if it's a date
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

    def _extract_numeric(self, value: object) -> float | None:
        if isinstance(value, int | float):
            return float(value)
        return None

    def _extract_text(self, value: object) -> str | None:
        if isinstance(value, str):
            return value
        return None
