"""Metadata helper mixin for entity-recognition orchestration outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.agents.services.extraction_service import (
        ExtractionDocumentOutcome,
    )
    from src.application.agents.services.governance_service import GovernanceDecision
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.type_definitions.common import JSONObject
    from src.type_definitions.ingestion import IngestResult


class _EntityRecognitionMetadataHelpers:
    """Mixin that builds metadata payloads for ERA and extraction outcomes."""

    @staticmethod
    def _build_outcome_metadata(  # noqa: PLR0913
        *,
        contract: EntityRecognitionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        pipeline_run_id: str | None,
        wrote_to_kernel: bool,
        dictionary_variables_created: int,
        dictionary_synonyms_created: int,
        dictionary_entity_types_created: int,
        ingestion_result: IngestResult | None,
    ) -> JSONObject:
        metadata: JSONObject = {
            "entity_recognition_decision": contract.decision,
            "entity_recognition_confidence": contract.confidence_score,
            "entity_recognition_rationale": contract.rationale,
            "entity_recognition_run_id": run_id,
            "entity_recognition_shadow_mode": governance.shadow_mode,
            "entity_recognition_requires_review": governance.requires_review,
            "entity_recognition_governance_reason": governance.reason,
            "entity_recognition_wrote_to_kernel": wrote_to_kernel,
            "entity_recognition_dictionary_variables_created": (
                dictionary_variables_created
            ),
            "entity_recognition_dictionary_synonyms_created": (
                dictionary_synonyms_created
            ),
            "entity_recognition_dictionary_entity_types_created": (
                dictionary_entity_types_created
            ),
            "entity_recognition_processed_at": datetime.now(UTC).isoformat(),
        }
        if pipeline_run_id is not None and pipeline_run_id.strip():
            metadata["pipeline_run_id"] = pipeline_run_id.strip()
        if ingestion_result is not None:
            metadata["entity_recognition_ingestion_success"] = ingestion_result.success
            metadata["entity_recognition_ingestion_entities_created"] = (
                ingestion_result.entities_created
            )
            metadata["entity_recognition_ingestion_observations_created"] = (
                ingestion_result.observations_created
            )
            metadata["entity_recognition_ingestion_errors"] = ingestion_result.errors
        return metadata

    @staticmethod
    def _build_extraction_metadata(
        extraction_outcome: ExtractionDocumentOutcome,
    ) -> JSONObject:
        return {
            "extraction_stage_status": extraction_outcome.status,
            "extraction_stage_reason": extraction_outcome.reason,
            "extraction_stage_run_id": extraction_outcome.run_id,
            "extraction_stage_review_required": extraction_outcome.review_required,
            "extraction_stage_shadow_mode": extraction_outcome.shadow_mode,
            "extraction_stage_wrote_to_kernel": extraction_outcome.wrote_to_kernel,
            "extraction_stage_observations_extracted": (
                extraction_outcome.observations_extracted
            ),
            "extraction_stage_relations_extracted": (
                extraction_outcome.relations_extracted
            ),
            "extraction_stage_rejected_facts": extraction_outcome.rejected_facts,
            "extraction_stage_ingestion_entities_created": (
                extraction_outcome.ingestion_entities_created
            ),
            "extraction_stage_ingestion_observations_created": (
                extraction_outcome.ingestion_observations_created
            ),
            "extraction_stage_errors": list(extraction_outcome.errors),
        }


__all__ = ["_EntityRecognitionMetadataHelpers"]
