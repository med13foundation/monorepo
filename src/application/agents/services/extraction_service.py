"""Application service for extraction agent orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.application.agents.services.governance_service import (
    GovernanceDecision,
    GovernanceService,
)
from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.type_definitions.ingestion import RawRecord
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.domain.agents.contracts.extraction import ExtractionContract
    from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionServiceDependencies:
    """Dependencies required by extraction orchestration."""

    extraction_agent: ExtractionAgentPort
    ingestion_pipeline: IngestionPipelinePort
    governance_service: GovernanceService | None = None
    review_queue_submitter: Callable[[str, str, str | None, str], None] | None = None


@dataclass(frozen=True)
class ExtractionDocumentOutcome:
    """Outcome of extraction + ingestion for one document."""

    document_id: UUID
    status: Literal["extracted", "failed"]
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_kernel: bool
    run_id: str | None = None
    observations_extracted: int = 0
    relations_extracted: int = 0
    rejected_facts: int = 0
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    ingestion_entities_created: int = 0
    ingestion_observations_created: int = 0
    seed_entity_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class ExtractionService:
    """Coordinate Extraction Agent -> Governance -> Kernel ingestion."""

    def __init__(self, dependencies: ExtractionServiceDependencies) -> None:
        self._agent = dependencies.extraction_agent
        self._ingestion_pipeline = dependencies.ingestion_pipeline
        self._governance = dependencies.governance_service or GovernanceService()
        self._review_queue_submitter = dependencies.review_queue_submitter

    async def extract_from_entity_recognition(  # noqa: PLR0913
        self,
        *,
        document: SourceDocument,
        recognition_contract: EntityRecognitionContract,
        research_space_settings: ResearchSpaceSettings,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
    ) -> ExtractionDocumentOutcome:
        """Run extraction for one recognized document and forward to kernel ingest."""
        if document.research_space_id is None:
            return ExtractionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason="missing_research_space_id",
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                errors=("missing_research_space_id",),
            )

        raw_record = self._extract_raw_record(document)
        requested_shadow_mode = (
            shadow_mode
            if isinstance(shadow_mode, bool)
            else recognition_contract.shadow_mode
        )
        context = ExtractionContext(
            document_id=str(document.id),
            source_type=document.source_type.value,
            research_space_id=str(document.research_space_id),
            research_space_settings=research_space_settings,
            raw_record=raw_record,
            recognized_entities=recognition_contract.recognized_entities,
            recognized_observations=recognition_contract.recognized_observations,
            shadow_mode=requested_shadow_mode,
        )

        contract = await self._agent.extract(context, model_id=model_id)
        run_id = self._resolve_run_id(contract)
        governance = self._governance.evaluate(
            confidence_score=contract.confidence_score,
            evidence_count=len(contract.evidence),
            decision=contract.decision,
            requested_shadow_mode=requested_shadow_mode,
            research_space_settings=research_space_settings,
            relation_types=self._resolve_relation_types(contract),
        )
        if governance.requires_review:
            self._submit_review_item(
                document=document,
                reason=governance.reason,
            )
        if governance.shadow_mode:
            return self._build_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="shadow_mode_enabled",
            )
        if not governance.allow_write:
            return self._build_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason=governance.reason,
                errors=(governance.reason,),
            )

        pipeline_records = self._build_pipeline_records(
            contract=contract,
            document=document,
            raw_record=raw_record,
            run_id=run_id,
            primary_entity_type=recognition_contract.primary_entity_type,
        )
        if not pipeline_records:
            return self._build_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="no_pipeline_payloads",
                errors=("no_pipeline_payloads",),
            )

        ingestion_result = self._ingestion_pipeline.run(
            pipeline_records,
            str(document.research_space_id),
        )
        if not ingestion_result.success:
            return self._build_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="kernel_ingestion_failed",
                ingestion_entities_created=ingestion_result.entities_created,
                ingestion_observations_created=ingestion_result.observations_created,
                seed_entity_ids=self._normalize_seed_entity_ids(
                    ingestion_result.entity_ids_touched,
                ),
                errors=tuple(ingestion_result.errors),
            )

        return self._build_outcome(
            document=document,
            contract=contract,
            governance=governance,
            run_id=run_id,
            wrote_to_kernel=True,
            reason="processed",
            ingestion_entities_created=ingestion_result.entities_created,
            ingestion_observations_created=ingestion_result.observations_created,
            seed_entity_ids=self._normalize_seed_entity_ids(
                ingestion_result.entity_ids_touched,
            ),
            errors=tuple(ingestion_result.errors),
        )

    async def close(self) -> None:
        """Release resources held by the underlying extraction adapter."""
        await self._agent.close()

    @staticmethod
    def _extract_raw_record(document: SourceDocument) -> JSONObject:
        raw_record = document.metadata.get("raw_record")
        if not isinstance(raw_record, dict):
            return {}
        return {str(key): to_json_value(value) for key, value in raw_record.items()}

    @staticmethod
    def _resolve_run_id(contract: ExtractionContract) -> str | None:
        run_id = contract.agent_run_id
        if not isinstance(run_id, str):
            return None
        normalized = run_id.strip()
        return normalized or None

    @staticmethod
    def _build_pipeline_records(
        *,
        contract: ExtractionContract,
        document: SourceDocument,
        raw_record: JSONObject,
        run_id: str | None,
        primary_entity_type: str,
    ) -> list[RawRecord]:
        payloads = contract.pipeline_payloads or [raw_record]
        records: list[RawRecord] = []
        for index, payload in enumerate(payloads):
            source_record_id = (
                document.external_record_id
                if index == 0
                else f"{document.external_record_id}:{index}"
            )
            metadata: JSONObject = {
                "type": document.source_type.value,
                "entity_type": primary_entity_type,
                "source_document_id": str(document.id),
                "source_record_id": source_record_id,
                "extraction_decision": contract.decision,
                "extraction_observations_count": len(contract.observations),
                "extraction_relations_count": len(contract.relations),
            }
            if run_id:
                metadata["extraction_run_id"] = run_id

            normalized_payload: JSONObject = {
                str(key): to_json_value(value) for key, value in payload.items()
            }
            records.append(
                RawRecord(
                    source_id=source_record_id,
                    data=normalized_payload,
                    metadata=metadata,
                ),
            )
        return records

    @staticmethod
    def _resolve_relation_types(
        contract: ExtractionContract,
    ) -> tuple[str, ...] | None:
        relation_types: list[str] = []
        for relation in contract.relations:
            normalized = relation.relation_type.strip().upper()
            if not normalized or normalized in relation_types:
                continue
            relation_types.append(normalized)
        return tuple(relation_types) if relation_types else None

    @staticmethod
    def _resolve_rejected_relation_reasons(
        contract: ExtractionContract,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        for rejected_fact in contract.rejected_facts:
            if rejected_fact.fact_type != "relation":
                continue
            reason = rejected_fact.reason.strip()
            if not reason or reason in reasons:
                continue
            reasons.append(reason)
        return tuple(reasons)

    @staticmethod
    def _resolve_rejected_relation_details(
        contract: ExtractionContract,
    ) -> tuple[JSONObject, ...]:
        details: list[JSONObject] = []
        for rejected_fact in contract.rejected_facts:
            if rejected_fact.fact_type != "relation":
                continue
            normalized_payload: JSONObject = {
                str(key): to_json_value(value)
                for key, value in rejected_fact.payload.items()
            }
            details.append(
                {
                    "reason": rejected_fact.reason.strip(),
                    "payload": normalized_payload,
                },
            )
        return tuple(details)

    def _submit_review_item(
        self,
        *,
        document: SourceDocument,
        reason: str,
    ) -> None:
        submitter = self._review_queue_submitter
        if submitter is None:
            return
        try:
            submitter(
                "extraction_document",
                str(document.id),
                (
                    str(document.research_space_id)
                    if document.research_space_id is not None
                    else None
                ),
                self._review_priority_for_reason(reason),
            )
        except Exception as exc:  # noqa: BLE001 - never block extraction on queue write
            logger.warning(
                "Failed to enqueue extraction review item for document_id=%s: %s",
                document.id,
                exc,
            )

    @staticmethod
    def _review_priority_for_reason(reason: str) -> str:
        if reason in {"agent_requested_escalation", "evidence_required"}:
            return "high"
        if reason == "confidence_below_threshold":
            return "medium"
        return "low"

    @staticmethod
    def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> tuple[str, ...]:
        normalized_ids: list[str] = []
        for seed_entity_id in seed_entity_ids:
            normalized = seed_entity_id.strip()
            if not normalized or normalized in normalized_ids:
                continue
            normalized_ids.append(normalized)
        return tuple(normalized_ids)

    @staticmethod
    def _build_outcome(  # noqa: PLR0913
        *,
        document: SourceDocument,
        contract: ExtractionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        wrote_to_kernel: bool,
        reason: str,
        ingestion_entities_created: int = 0,
        ingestion_observations_created: int = 0,
        seed_entity_ids: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
    ) -> ExtractionDocumentOutcome:
        status: Literal["extracted", "failed"] = (
            "extracted" if wrote_to_kernel or governance.shadow_mode else "failed"
        )
        return ExtractionDocumentOutcome(
            document_id=document.id,
            status=status,
            reason=reason,
            review_required=governance.requires_review,
            shadow_mode=governance.shadow_mode,
            wrote_to_kernel=wrote_to_kernel,
            run_id=run_id,
            observations_extracted=len(contract.observations),
            relations_extracted=len(contract.relations),
            rejected_facts=len(contract.rejected_facts),
            rejected_relation_reasons=(
                ExtractionService._resolve_rejected_relation_reasons(contract)
            ),
            rejected_relation_details=(
                ExtractionService._resolve_rejected_relation_details(contract)
            ),
            ingestion_entities_created=ingestion_entities_created,
            ingestion_observations_created=ingestion_observations_created,
            seed_entity_ids=seed_entity_ids,
            errors=errors,
        )


__all__ = [
    "ExtractionDocumentOutcome",
    "ExtractionService",
    "ExtractionServiceDependencies",
]
