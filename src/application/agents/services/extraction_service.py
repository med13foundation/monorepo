"""Application service for extraction agent orchestration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._extraction_chunk_execution_helpers import (
    extract_contract_with_optional_chunking,
)
from src.application.agents.services._extraction_relation_persistence_helpers import (
    _ExtractionRelationPersistenceHelpers,
)
from src.application.agents.services._extraction_service_support import (
    ExtractionDocumentOutcome,
    ExtractionServiceDependencies,
    build_extraction_outcome,
    build_initial_extraction_funnel,
    merge_extraction_funnels,
    normalize_seed_entity_ids,
    review_priority_for_reason,
)
from src.application.agents.services.governance_service import GovernanceService
from src.domain.agents.contexts.extraction_context import ExtractionContext
from src.domain.value_objects.relation_types import normalize_relation_type
from src.type_definitions.ingestion import RawRecord
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.application.agents.services._extraction_chunking_helpers import (
        ChunkedExtractionSummary,
    )
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.domain.agents.contracts.extraction import ExtractionContract
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)
_EXTRACTION_ENTITY_TYPE_CREATED_BY = "agent:extraction_service"


class ExtractionService(_ExtractionRelationPersistenceHelpers):
    """Coordinate Extraction Agent -> Governance -> Kernel ingestion."""

    def __init__(self, dependencies: ExtractionServiceDependencies) -> None:
        self._agent = dependencies.extraction_agent
        self._policy_agent = dependencies.extraction_policy_agent
        self._ingestion_pipeline = dependencies.ingestion_pipeline
        self._relations = dependencies.relation_repository
        self._relation_claims = dependencies.relation_claim_repository
        self._entities = dependencies.entity_repository
        self._dictionary = dependencies.dictionary_service
        self._concepts = dependencies.concept_service
        self._evidence_sentence_harness = dependencies.evidence_sentence_harness
        self._endpoint_shape_judge = dependencies.endpoint_shape_judge
        self._governance = dependencies.governance_service or GovernanceService()
        self._review_queue_submitter = dependencies.review_queue_submitter
        self._rollback_on_error = dependencies.rollback_on_error

    async def extract_from_entity_recognition(  # noqa: PLR0913, PLR0911
        self,
        *,
        document: SourceDocument,
        recognition_contract: EntityRecognitionContract,
        research_space_settings: ResearchSpaceSettings,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
    ) -> ExtractionDocumentOutcome:
        """Run extraction for one recognized document and forward to kernel ingest."""
        started_at = datetime.now(UTC)
        if document.research_space_id is None:
            logger.warning(
                "Extraction service skipped document without research space id",
                extra={"document_id": str(document.id)},
            )
            return ExtractionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason="missing_research_space_id",
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                errors=("missing_research_space_id",),
            )

        logger.info(
            "Extraction service document started",
            extra={
                "document_id": str(document.id),
                "source_type": document.source_type.value,
                "research_space_id": str(document.research_space_id),
                "requested_shadow_mode": shadow_mode,
                "recognition_shadow_mode": recognition_contract.shadow_mode,
                "recognized_entities_count": len(
                    recognition_contract.recognized_entities,
                ),
                "recognized_observations_count": len(
                    recognition_contract.recognized_observations,
                ),
                "recognition_run_id": recognition_contract.agent_run_id,
                "model_id": model_id,
            },
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
        contract_started_at = datetime.now(UTC)
        logger.info(
            "Extraction contract generation started",
            extra={
                "document_id": str(document.id),
                "source_type": context.source_type,
                "shadow_mode": requested_shadow_mode,
                "model_id": model_id,
            },
        )
        contract, chunk_summary = await self._extract_contract_with_optional_chunking(
            context=context,
            model_id=model_id,
        )
        logger.info(
            "Extraction contract generation finished",
            extra={
                "document_id": str(document.id),
                "duration_ms": int(
                    (datetime.now(UTC) - contract_started_at).total_seconds() * 1000,
                ),
                "contract_run_id": contract.agent_run_id,
                "decision": contract.decision,
                "confidence_score": contract.confidence_score,
                "observations_count": len(contract.observations),
                "relations_count": len(contract.relations),
                "rejected_facts_count": len(contract.rejected_facts),
                "chunk_mode": chunk_summary.mode,
                "chunk_count": chunk_summary.chunk_count,
                "chunk_successful": chunk_summary.successful_chunks,
                "chunk_failed": chunk_summary.failed_chunks,
            },
        )
        initial_funnel = build_initial_extraction_funnel(
            contract=contract,
            chunk_summary=chunk_summary,
        )
        run_id = self._resolve_run_id(contract)
        governance = self._governance.evaluate(
            confidence_score=contract.confidence_score,
            evidence_count=len(contract.evidence),
            decision=self._resolve_governance_decision(contract),
            requested_shadow_mode=requested_shadow_mode,
            research_space_settings=research_space_settings,
            relation_types=self._resolve_relation_types(contract),
        )
        logger.info(
            "Extraction governance decision evaluated",
            extra={
                "document_id": str(document.id),
                "allow_write": governance.allow_write,
                "requires_review": governance.requires_review,
                "shadow_mode": governance.shadow_mode,
                "reason": governance.reason,
                "run_id": run_id,
            },
        )
        if governance.requires_review:
            self._submit_review_item(
                document=document,
                reason=governance.reason,
            )
        if governance.shadow_mode:
            logger.info(
                "Extraction service completed in shadow mode",
                extra={
                    "document_id": str(document.id),
                    "run_id": run_id,
                    "duration_ms": int(
                        (datetime.now(UTC) - started_at).total_seconds() * 1000,
                    ),
                },
            )
            return build_extraction_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="shadow_mode_enabled",
                extraction_funnel=initial_funnel,
            )
        if not governance.allow_write:
            logger.info(
                "Extraction service blocked by governance",
                extra={
                    "document_id": str(document.id),
                    "run_id": run_id,
                    "reason": governance.reason,
                    "duration_ms": int(
                        (datetime.now(UTC) - started_at).total_seconds() * 1000,
                    ),
                },
            )
            return build_extraction_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason=governance.reason,
                extraction_funnel=initial_funnel,
                errors=(governance.reason,),
            )

        primary_entity_type = recognition_contract.primary_entity_type.strip().upper()
        if not primary_entity_type:
            logger.warning(
                "Extraction service missing primary entity type",
                extra={"document_id": str(document.id), "run_id": run_id},
            )
            return build_extraction_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="missing_primary_entity_type",
                extraction_funnel=initial_funnel,
                errors=("missing_primary_entity_type",),
            )
        if not self._ensure_active_primary_entity_type_for_ingestion(
            entity_type=primary_entity_type,
            source_ref=f"source_document:{document.id}:extraction_ingestion",
        ):
            logger.warning(
                "Extraction service failed to ensure active primary entity type",
                extra={
                    "document_id": str(document.id),
                    "run_id": run_id,
                    "entity_type": primary_entity_type,
                },
            )
            return build_extraction_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="primary_entity_type_invalid_or_inactive",
                extraction_funnel=initial_funnel,
                errors=(
                    f"primary_entity_type_invalid_or_inactive:{primary_entity_type}",
                ),
            )

        pipeline_records = self._build_pipeline_records(
            contract=contract,
            document=document,
            raw_record=raw_record,
            run_id=run_id,
            primary_entity_type=primary_entity_type,
        )
        logger.info(
            "Extraction pipeline records built",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "record_count": len(pipeline_records),
            },
        )
        if not pipeline_records:
            logger.warning(
                "Extraction service produced no pipeline payloads",
                extra={"document_id": str(document.id), "run_id": run_id},
            )
            return build_extraction_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="no_pipeline_payloads",
                extraction_funnel=initial_funnel,
                errors=("no_pipeline_payloads",),
            )

        ingestion_started_at = datetime.now(UTC)
        logger.info(
            "Extraction ingestion pipeline started",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "record_count": len(pipeline_records),
            },
        )
        ingestion_result = self._ingestion_pipeline.run(
            pipeline_records,
            str(document.research_space_id),
        )
        logger.info(
            "Extraction ingestion pipeline finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - ingestion_started_at).total_seconds() * 1000,
                ),
                "success": ingestion_result.success,
                "entities_created": ingestion_result.entities_created,
                "observations_created": ingestion_result.observations_created,
                "entity_ids_touched": len(ingestion_result.entity_ids_touched),
                "error_count": len(ingestion_result.errors),
            },
        )
        if not ingestion_result.success:
            logger.warning(
                "Extraction ingestion pipeline failed",
                extra={
                    "document_id": str(document.id),
                    "run_id": run_id,
                    "errors": tuple(ingestion_result.errors),
                },
            )
            return build_extraction_outcome(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_kernel=False,
                reason="kernel_ingestion_failed",
                ingestion_entities_created=ingestion_result.entities_created,
                ingestion_observations_created=ingestion_result.observations_created,
                extraction_funnel=initial_funnel,
                seed_entity_ids=normalize_seed_entity_ids(
                    ingestion_result.entity_ids_touched,
                ),
                errors=tuple(ingestion_result.errors),
            )

        relation_persistence_started_at = datetime.now(UTC)
        logger.info(
            "Extraction relation persistence started",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "relations_count": len(contract.relations),
                "publication_entity_ids_count": len(
                    ingestion_result.entity_ids_touched,
                ),
            },
        )
        relation_persistence_result = await self._persist_extracted_relations(
            document=document,
            contract=contract,
            research_space_settings=research_space_settings,
            publication_entity_ids=tuple(ingestion_result.entity_ids_touched),
            model_id=model_id,
        )
        logger.info(
            "Extraction relation persistence finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (
                        datetime.now(UTC) - relation_persistence_started_at
                    ).total_seconds()
                    * 1000,
                ),
                "persisted_relations_count": (
                    relation_persistence_result.persisted_relations_count
                ),
                "pending_review_relations_count": (
                    relation_persistence_result.pending_review_relations_count
                ),
                "relation_claims_count": relation_persistence_result.relation_claims_count,
                "non_persistable_claims_count": (
                    relation_persistence_result.non_persistable_claims_count
                ),
                "forbidden_relations_count": (
                    relation_persistence_result.forbidden_relations_count
                ),
                "undefined_relations_count": (
                    relation_persistence_result.undefined_relations_count
                ),
                "concept_members_created_count": (
                    relation_persistence_result.concept_members_created_count
                ),
                "concept_aliases_created_count": (
                    relation_persistence_result.concept_aliases_created_count
                ),
                "concept_decisions_proposed_count": (
                    relation_persistence_result.concept_decisions_proposed_count
                ),
                "error_count": len(relation_persistence_result.errors),
            },
        )
        merged_funnel = merge_extraction_funnels(
            initial_funnel=initial_funnel,
            persistence_funnel=relation_persistence_result.funnel,
        )

        logger.info(
            "Extraction service document finished",
            extra={
                "document_id": str(document.id),
                "run_id": run_id,
                "duration_ms": int(
                    (datetime.now(UTC) - started_at).total_seconds() * 1000,
                ),
                "ingestion_entities_created": ingestion_result.entities_created,
                "ingestion_observations_created": ingestion_result.observations_created,
                "persisted_relations_count": (
                    relation_persistence_result.persisted_relations_count
                ),
                "pending_review_relations_count": (
                    relation_persistence_result.pending_review_relations_count
                ),
                "error_count": len(ingestion_result.errors)
                + len(relation_persistence_result.errors),
            },
        )
        return build_extraction_outcome(
            document=document,
            contract=contract,
            governance=governance,
            run_id=run_id,
            wrote_to_kernel=True,
            reason="processed",
            ingestion_entities_created=ingestion_result.entities_created,
            ingestion_observations_created=ingestion_result.observations_created,
            persisted_relations_count=(
                relation_persistence_result.persisted_relations_count
            ),
            pending_review_relations_count=(
                relation_persistence_result.pending_review_relations_count
            ),
            forbidden_relations_count=(
                relation_persistence_result.forbidden_relations_count
            ),
            undefined_relations_count=(
                relation_persistence_result.undefined_relations_count
            ),
            concept_members_created_count=(
                relation_persistence_result.concept_members_created_count
            ),
            concept_aliases_created_count=(
                relation_persistence_result.concept_aliases_created_count
            ),
            concept_decisions_proposed_count=(
                relation_persistence_result.concept_decisions_proposed_count
            ),
            policy_step_run_id=relation_persistence_result.policy_run_id,
            policy_proposals_count=relation_persistence_result.policy_proposals_count,
            relation_rejected_reasons=(
                relation_persistence_result.rejected_relation_reasons
            ),
            relation_rejected_details=(
                relation_persistence_result.rejected_relation_details
            ),
            extraction_funnel=merged_funnel,
            seed_entity_ids=normalize_seed_entity_ids(
                ingestion_result.entity_ids_touched,
            ),
            errors=tuple(ingestion_result.errors) + relation_persistence_result.errors,
        )

    async def close(self) -> None:
        """Release resources held by the underlying extraction adapter."""
        await self._agent.close()
        if self._policy_agent is not None:
            await self._policy_agent.close()

    @staticmethod
    def _extract_raw_record(document: SourceDocument) -> JSONObject:
        raw_record = document.metadata.get("raw_record")
        if not isinstance(raw_record, dict):
            return {}
        return {str(key): to_json_value(value) for key, value in raw_record.items()}

    def _ensure_active_primary_entity_type_for_ingestion(  # noqa: PLR0911
        self,
        *,
        entity_type: str,
        source_ref: str,
    ) -> bool:
        dictionary = self._dictionary
        if dictionary is None:
            return False

        normalized = entity_type.strip().upper()
        if not normalized:
            return False

        existing = dictionary.get_entity_type(
            normalized,
            include_inactive=True,
        )
        if existing is not None:
            if existing.is_active and existing.review_status == "ACTIVE":
                return True
            try:
                dictionary.set_entity_type_review_status(
                    normalized,
                    review_status="ACTIVE",
                    reviewed_by=_EXTRACTION_ENTITY_TYPE_CREATED_BY,
                )
            except ValueError as exc:
                logger.warning(
                    "Failed to activate extraction primary entity type=%s (%s)",
                    normalized,
                    exc,
                )
                return False
            return dictionary.get_entity_type(normalized) is not None

        creation_settings: ResearchSpaceSettings = {
            "dictionary_agent_creation_policy": "ACTIVE",
        }
        try:
            dictionary.create_entity_type(
                entity_type=normalized,
                display_name=normalized.replace("_", " ").title(),
                description=(
                    "Auto-created entity type for extraction ingestion "
                    "primary-entity persistence."
                ),
                domain_context="general",
                created_by=_EXTRACTION_ENTITY_TYPE_CREATED_BY,
                source_ref=source_ref,
                research_space_settings=creation_settings,
            )
        except ValueError as exc:
            logger.warning(
                "Failed to create extraction primary entity type=%s (%s)",
                normalized,
                exc,
            )
            return False
        return dictionary.get_entity_type(normalized) is not None

    @staticmethod
    def _resolve_run_id(contract: ExtractionContract) -> str | None:
        run_id = contract.agent_run_id
        if not isinstance(run_id, str):
            return None
        normalized = run_id.strip()
        return normalized or None

    @staticmethod
    def _resolve_governance_decision(
        contract: ExtractionContract,
    ) -> Literal["generated", "fallback", "escalate"]:
        if contract.decision != "escalate":
            return contract.decision
        has_structured_output = bool(
            contract.observations
            or contract.relations
            or contract.rejected_facts
            or contract.pipeline_payloads,
        )
        return "generated" if has_structured_output else contract.decision

    @staticmethod
    def _build_pipeline_records(
        *,
        contract: ExtractionContract,
        document: SourceDocument,
        raw_record: JSONObject,
        run_id: str | None,
        primary_entity_type: str,
    ) -> list[RawRecord]:
        normalized_primary_entity_type = primary_entity_type.strip().upper()
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
                "entity_type": normalized_primary_entity_type,
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
            normalized = normalize_relation_type(relation.relation_type)
            if not normalized or normalized in relation_types:
                continue
            relation_types.append(normalized)
        return tuple(relation_types) if relation_types else None

    async def _extract_contract_with_optional_chunking(
        self,
        *,
        context: ExtractionContext,
        model_id: str | None,
    ) -> tuple[ExtractionContract, ChunkedExtractionSummary]:
        return await extract_contract_with_optional_chunking(
            agent=self._agent,
            context=context,
            model_id=model_id,
        )

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
                review_priority_for_reason(reason),
            )
        except Exception as exc:  # noqa: BLE001 - never block extraction on queue write
            logger.warning(
                "Failed to enqueue extraction review item for document_id=%s: %s",
                document.id,
                exc,
            )


__all__ = [
    "ExtractionDocumentOutcome",
    "ExtractionService",
    "ExtractionServiceDependencies",
]
