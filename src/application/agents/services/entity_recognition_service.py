"""Application service for Tier-3 entity recognition orchestration."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from src.application.agents.services._entity_recognition_bootstrap_helpers import (
    _EntityRecognitionBootstrapHelpers,
)
from src.application.agents.services._entity_recognition_metadata_helpers import (
    _EntityRecognitionMetadataHelpers,
)
from src.application.agents.services.governance_service import (
    GovernanceDecision,
    GovernanceService,
)
from src.domain.agents.contexts.entity_recognition_context import (
    EntityRecognitionContext,
)
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    SourceDocument,
)
from src.type_definitions.ingestion import RawRecord
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.application.agents.services.extraction_service import (
        ExtractionService,
    )
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
    from src.domain.agents.ports.entity_recognition_port import EntityRecognitionPort
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )
    from src.type_definitions.common import JSONObject, JSONValue, ResearchSpaceSettings

logger = logging.getLogger(__name__)

_AGENT_CREATED_BY = "agent:entity_recognition"
_ID_CLEANUP_PATTERN = re.compile(r"[^A-Za-z0-9_]+")
_SEPARATOR_PATTERN = re.compile(r"[_\s]+")
_ISO_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class EntityRecognitionServiceDependencies:
    """Dependencies required by the entity-recognition orchestration service."""

    entity_recognition_agent: EntityRecognitionPort
    source_document_repository: SourceDocumentRepository
    ingestion_pipeline: IngestionPipelinePort
    dictionary_service: DictionaryPort
    extraction_service: ExtractionService | None = None
    governance_service: GovernanceService | None = None
    research_space_repository: ResearchSpaceRepository | None = None


@dataclass(frozen=True)
class EntityRecognitionDocumentOutcome:
    """Outcome of processing a single source document."""

    document_id: UUID
    status: Literal["extracted", "failed", "skipped"]
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_kernel: bool
    run_id: str | None = None
    dictionary_variables_created: int = 0
    dictionary_synonyms_created: int = 0
    dictionary_entity_types_created: int = 0
    ingestion_entities_created: int = 0
    ingestion_observations_created: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityRecognitionRunSummary:
    """Batch summary for processing pending source documents."""

    requested: int
    processed: int
    extracted: int
    failed: int
    skipped: int
    review_required: int
    shadow_runs: int
    dictionary_variables_created: int
    dictionary_synonyms_created: int
    dictionary_entity_types_created: int
    ingestion_entities_created: int
    ingestion_observations_created: int
    errors: tuple[str, ...]
    started_at: datetime
    completed_at: datetime


class EntityRecognitionService(
    _EntityRecognitionBootstrapHelpers,
    _EntityRecognitionMetadataHelpers,
):
    """Coordinate Document Store -> Entity Agent -> Governance -> Kernel ingestion."""

    def __init__(
        self,
        dependencies: EntityRecognitionServiceDependencies,
        *,
        default_shadow_mode: bool = True,
        agent_created_by: str = _AGENT_CREATED_BY,
    ) -> None:
        self._agent = dependencies.entity_recognition_agent
        self._source_documents = dependencies.source_document_repository
        self._ingestion_pipeline = dependencies.ingestion_pipeline
        self._dictionary = dependencies.dictionary_service
        self._extraction_service = dependencies.extraction_service
        self._governance = dependencies.governance_service or GovernanceService()
        self._research_spaces = dependencies.research_space_repository
        self._default_shadow_mode = default_shadow_mode
        normalized_created_by = agent_created_by.strip()
        self._agent_created_by = normalized_created_by or _AGENT_CREATED_BY

    async def process_pending_documents(  # noqa: PLR0913
        self,
        *,
        limit: int = 25,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        source_type: str | None = None,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
    ) -> EntityRecognitionRunSummary:
        """Process pending extraction documents through entity recognition."""
        started_at = datetime.now(UTC)
        pending_documents = self._source_documents.list_pending_extraction(
            limit=max(limit, 1),
            source_id=source_id,
            research_space_id=research_space_id,
        )
        normalized_source_type = (
            source_type.strip().lower() if isinstance(source_type, str) else None
        )
        if normalized_source_type:
            pending_documents = [
                document
                for document in pending_documents
                if document.source_type.value.strip().lower() == normalized_source_type
            ]

        outcomes: list[EntityRecognitionDocumentOutcome] = []
        for document in pending_documents:
            outcome = await self._process_document_entity(
                document=document,
                model_id=model_id,
                shadow_mode=shadow_mode,
                force=False,
                pipeline_run_id=pipeline_run_id,
            )
            outcomes.append(outcome)

        completed_at = datetime.now(UTC)
        return self._build_run_summary(
            outcomes=outcomes,
            requested=len(pending_documents),
            started_at=started_at,
            completed_at=completed_at,
        )

    async def process_document(
        self,
        *,
        document_id: UUID,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        force: bool = False,
    ) -> EntityRecognitionDocumentOutcome:
        """Process a single source document by id."""
        document = self._source_documents.get_by_id(document_id)
        if document is None:
            message = f"Source document not found: {document_id}"
            raise LookupError(message)
        return await self._process_document_entity(
            document=document,
            model_id=model_id,
            shadow_mode=shadow_mode,
            force=force,
            pipeline_run_id=None,
        )

    async def close(self) -> None:
        """Release resources held by the underlying entity-recognition adapter."""
        await self._agent.close()
        if self._extraction_service is not None:
            await self._extraction_service.close()

    async def _process_document_entity(  # noqa: C901, PLR0911
        self,
        *,
        document: SourceDocument,
        model_id: str | None,
        shadow_mode: bool | None,
        force: bool,
        pipeline_run_id: str | None,
    ) -> EntityRecognitionDocumentOutcome:
        if not force and document.extraction_status != DocumentExtractionStatus.PENDING:
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="skipped",
                reason=f"document_status={document.extraction_status.value}",
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
            )

        raw_record = self._extract_raw_record(document)
        if not raw_record:
            failure_reason = "missing_raw_record_metadata"
            self._persist_failed_document(
                document=document,
                run_uuid=None,
                metadata_patch={"entity_recognition_error": failure_reason},
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                errors=(failure_reason,),
            )

        research_space_settings = self._resolve_research_space_settings(document)
        requested_shadow_mode = self._resolve_shadow_mode(
            override=shadow_mode,
            settings=research_space_settings,
        )
        context = EntityRecognitionContext(
            document_id=str(document.id),
            source_type=document.source_type.value,
            research_space_id=(
                str(document.research_space_id) if document.research_space_id else None
            ),
            research_space_settings=research_space_settings,
            raw_record=raw_record,
            shadow_mode=requested_shadow_mode,
        )

        in_progress = document.mark_extraction_in_progress(started_at=datetime.now(UTC))
        document = self._source_documents.upsert(
            in_progress.model_copy(
                update={
                    "metadata": self._merge_metadata(
                        in_progress.metadata,
                        {
                            "entity_recognition_started_at": datetime.now(
                                UTC,
                            ).isoformat(),
                            "entity_recognition_shadow_mode": requested_shadow_mode,
                            "pipeline_run_id": pipeline_run_id,
                        },
                    ),
                },
            ),
        )

        try:
            contract = await self._agent.recognize(context, model_id=model_id)
        except Exception as exc:  # noqa: BLE001 - surfaced via metadata/outcome
            logger.exception(
                "Entity recognition failed for document=%s",
                document.id,
            )
            failure_reason = "agent_execution_failed"
            self._persist_failed_document(
                document=document,
                run_uuid=None,
                metadata_patch={
                    "entity_recognition_error": str(exc),
                    "entity_recognition_failure_reason": failure_reason,
                },
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=requested_shadow_mode,
                wrote_to_kernel=False,
                errors=(str(exc),),
            )

        run_id = self._resolve_run_id(contract)
        run_uuid = self._try_parse_uuid(run_id)
        governance = self._governance.evaluate(
            confidence_score=contract.confidence_score,
            evidence_count=len(contract.evidence),
            decision=contract.decision,
            requested_shadow_mode=requested_shadow_mode,
            research_space_settings=research_space_settings,
        )

        if governance.shadow_mode:
            self._persist_extracted_document(
                document=document,
                run_uuid=run_uuid,
                metadata_patch=self._build_outcome_metadata(
                    contract=contract,
                    governance=governance,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    wrote_to_kernel=False,
                    dictionary_variables_created=0,
                    dictionary_synonyms_created=0,
                    dictionary_entity_types_created=0,
                    ingestion_result=None,
                ),
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="extracted",
                reason="shadow_mode_enabled",
                review_required=False,
                shadow_mode=True,
                wrote_to_kernel=False,
                run_id=run_id,
            )

        if not governance.allow_write:
            failure_reason = governance.reason
            self._persist_failed_document(
                document=document,
                run_uuid=run_uuid,
                metadata_patch=self._build_outcome_metadata(
                    contract=contract,
                    governance=governance,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    wrote_to_kernel=False,
                    dictionary_variables_created=0,
                    dictionary_synonyms_created=0,
                    dictionary_entity_types_created=0,
                    ingestion_result=None,
                ),
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=governance.requires_review,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                errors=(failure_reason,),
            )

        if document.research_space_id is None:
            failure_reason = "missing_research_space_id"
            self._persist_failed_document(
                document=document,
                run_uuid=run_uuid,
                metadata_patch={
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_run_id": run_id,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                errors=(failure_reason,),
            )

        try:
            (
                dictionary_variables_created,
                dictionary_synonyms_created,
                dictionary_entity_types_created,
            ) = self._apply_dictionary_mutations(
                contract=contract,
                raw_record=raw_record,
                source_type=document.source_type.value,
                source_ref=f"source_document:{document.id}",
                research_space_settings=research_space_settings,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced via metadata/outcome
            logger.exception(
                "Dictionary mutation failed for document=%s",
                document.id,
            )
            failure_reason = "dictionary_mutation_failed"
            self._persist_failed_document(
                document=document,
                run_uuid=run_uuid,
                metadata_patch={
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_error": str(exc),
                    "entity_recognition_run_id": run_id,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                errors=(str(exc),),
            )

        if self._extraction_service is not None:
            return await self._process_document_with_extraction(
                document=document,
                contract=contract,
                governance=governance,
                run_id=run_id,
                run_uuid=run_uuid,
                model_id=model_id,
                requested_shadow_mode=requested_shadow_mode,
                research_space_settings=research_space_settings,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                pipeline_run_id=pipeline_run_id,
            )

        pipeline_records = self._build_pipeline_records(
            contract=contract,
            document=document,
            raw_record=raw_record,
            run_id=run_id,
        )
        if not pipeline_records:
            failure_reason = "no_pipeline_payloads"
            self._persist_failed_document(
                document=document,
                run_uuid=run_uuid,
                metadata_patch={
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_run_id": run_id,
                    "pipeline_run_id": pipeline_run_id,
                },
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                errors=(failure_reason,),
            )

        ingestion_result = self._ingestion_pipeline.run(
            pipeline_records,
            str(document.research_space_id),
        )
        if not ingestion_result.success:
            failure_reason = "kernel_ingestion_failed"
            self._persist_failed_document(
                document=document,
                run_uuid=run_uuid,
                metadata_patch=self._build_outcome_metadata(
                    contract=contract,
                    governance=governance,
                    run_id=run_id,
                    pipeline_run_id=pipeline_run_id,
                    wrote_to_kernel=False,
                    dictionary_variables_created=dictionary_variables_created,
                    dictionary_synonyms_created=dictionary_synonyms_created,
                    dictionary_entity_types_created=dictionary_entity_types_created,
                    ingestion_result=ingestion_result,
                ),
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=False,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_entities_created=ingestion_result.entities_created,
                ingestion_observations_created=ingestion_result.observations_created,
                errors=tuple(ingestion_result.errors),
            )

        self._persist_extracted_document(
            document=document,
            run_uuid=run_uuid,
            metadata_patch=self._build_outcome_metadata(
                contract=contract,
                governance=governance,
                run_id=run_id,
                pipeline_run_id=pipeline_run_id,
                wrote_to_kernel=True,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_result=ingestion_result,
            ),
        )
        return EntityRecognitionDocumentOutcome(
            document_id=document.id,
            status="extracted",
            reason="processed",
            review_required=False,
            shadow_mode=False,
            wrote_to_kernel=True,
            run_id=run_id,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_entities_created=ingestion_result.entities_created,
            ingestion_observations_created=ingestion_result.observations_created,
            errors=tuple(ingestion_result.errors),
        )

    def _resolve_research_space_settings(  # noqa: C901, PLR0912
        self,
        document: SourceDocument,
    ) -> ResearchSpaceSettings:
        if self._research_spaces is None or document.research_space_id is None:
            return {}
        space = self._research_spaces.find_by_id(document.research_space_id)
        if space is None:
            return {}
        raw_settings = space.settings
        settings: ResearchSpaceSettings = {}

        auto_approve = raw_settings.get("auto_approve")
        if isinstance(auto_approve, bool):
            settings["auto_approve"] = auto_approve

        require_review = raw_settings.get("require_review")
        if isinstance(require_review, bool):
            settings["require_review"] = require_review

        review_threshold = raw_settings.get("review_threshold")
        if isinstance(review_threshold, float | int):
            normalized = max(0.0, min(float(review_threshold), 1.0))
            settings["review_threshold"] = normalized

        relation_default_review_threshold = raw_settings.get(
            "relation_default_review_threshold",
        )
        if isinstance(relation_default_review_threshold, float | int):
            settings["relation_default_review_threshold"] = max(
                0.0,
                min(float(relation_default_review_threshold), 1.0),
            )

        raw_relation_review_thresholds = raw_settings.get("relation_review_thresholds")
        if isinstance(raw_relation_review_thresholds, dict):
            relation_review_thresholds: dict[str, float] = {}
            for (
                raw_relation_type,
                raw_threshold,
            ) in raw_relation_review_thresholds.items():
                if not isinstance(raw_relation_type, str):
                    continue
                normalized_relation_type = raw_relation_type.strip().upper()
                if not normalized_relation_type:
                    continue
                if isinstance(raw_threshold, float | int):
                    relation_review_thresholds[normalized_relation_type] = max(
                        0.0,
                        min(float(raw_threshold), 1.0),
                    )
            if relation_review_thresholds:
                settings["relation_review_thresholds"] = relation_review_thresholds

        creation_policy = raw_settings.get("dictionary_agent_creation_policy")
        if isinstance(creation_policy, str):
            normalized_policy = creation_policy.strip().upper()
            if normalized_policy == "ACTIVE":
                settings["dictionary_agent_creation_policy"] = "ACTIVE"
            elif normalized_policy == "PENDING_REVIEW":
                settings["dictionary_agent_creation_policy"] = "PENDING_REVIEW"

        raw_custom = raw_settings.get("custom")
        if isinstance(raw_custom, dict):
            custom: dict[str, str | int | float | bool | None] = {}
            for key, value in raw_custom.items():
                if isinstance(value, str | int | float | bool) or value is None:
                    custom[str(key)] = value
            if custom:
                settings["custom"] = custom

        return settings

    def _resolve_shadow_mode(
        self,
        *,
        override: bool | None,
        settings: ResearchSpaceSettings,
    ) -> bool:
        if isinstance(override, bool):
            return override

        custom = settings.get("custom")
        if isinstance(custom, dict):
            explicit = custom.get("entity_recognition_shadow_mode")
            if isinstance(explicit, bool):
                return explicit

        return self._default_shadow_mode

    @staticmethod
    def _extract_raw_record(document: SourceDocument) -> JSONObject:
        raw_record = document.metadata.get("raw_record")
        if not isinstance(raw_record, dict):
            return {}
        return {str(key): to_json_value(value) for key, value in raw_record.items()}

    def _apply_dictionary_mutations(  # noqa: C901, PLR0913
        self,
        *,
        contract: EntityRecognitionContract,
        raw_record: JSONObject,
        source_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int, int]:
        (
            bootstrap_variables_created,
            bootstrap_entity_types_created,
        ) = self._ensure_domain_bootstrap(
            source_type=source_type,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )

        if (
            contract.decision == "generated"
            and isinstance(contract.agent_run_id, str)
            and contract.agent_run_id.strip()
        ):
            (
                reconciled_variables,
                reconciled_synonyms,
                reconciled_entity_types,
            ) = self._reconcile_agent_dictionary_mutations(contract)
            return (
                reconciled_variables + bootstrap_variables_created,
                reconciled_synonyms,
                reconciled_entity_types + bootstrap_entity_types_created,
            )

        domain_context = self._infer_domain_context(source_type)
        created_entity_types = bootstrap_entity_types_created
        for entity in contract.recognized_entities:
            entity_type_id = self._normalize_identifier(
                entity.entity_type,
                prefix="ENTITY",
                max_length=64,
            )
            if self._dictionary.get_entity_type(entity_type_id) is not None:
                continue
            self._dictionary.create_entity_type(
                entity_type=entity_type_id,
                display_name=self._to_display_name(entity_type_id),
                description=(
                    f"Autogenerated entity type from {source_type} "
                    "entity-recognition run"
                ),
                domain_context=domain_context,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            created_entity_types += 1

        created_variables = bootstrap_variables_created
        created_synonyms = 0
        for observation in contract.recognized_observations:
            field_name = observation.field_name.strip()
            if not field_name:
                continue

            variable_id = self._resolve_variable_id(
                explicit_variable_id=observation.variable_id,
                field_name=field_name,
            )
            variable = self._dictionary.get_variable(variable_id)
            if variable is None:
                variable = self._dictionary.create_variable(
                    variable_id=variable_id,
                    canonical_name=self._to_canonical_name(field_name),
                    display_name=self._to_display_name(field_name),
                    data_type=self._infer_data_type(observation.value),
                    domain_context=domain_context,
                    sensitivity="INTERNAL",
                    description=(
                        f"Autogenerated variable from {source_type} "
                        f"field '{field_name}'"
                    ),
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=research_space_settings,
                )
                created_variables += 1

            matched_variable = self._dictionary.resolve_synonym(field_name)
            if matched_variable is None:
                self._dictionary.create_synonym(
                    variable_id=variable.id,
                    synonym=field_name,
                    source=source_type.lower(),
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=research_space_settings,
                )
                created_synonyms += 1
            elif matched_variable.id != variable.id:
                logger.warning(
                    "Synonym conflict for '%s': existing=%s candidate=%s",
                    field_name,
                    matched_variable.id,
                    variable.id,
                )

        if not contract.recognized_observations and raw_record:
            for raw_field, raw_value in raw_record.items():
                if self._dictionary.resolve_synonym(raw_field) is not None:
                    continue
                variable_id = self._resolve_variable_id(
                    explicit_variable_id=None,
                    field_name=raw_field,
                )
                existing_variable = self._dictionary.get_variable(variable_id)
                if existing_variable is None:
                    existing_variable = self._dictionary.create_variable(
                        variable_id=variable_id,
                        canonical_name=self._to_canonical_name(raw_field),
                        display_name=self._to_display_name(raw_field),
                        data_type=self._infer_data_type(raw_value),
                        domain_context=domain_context,
                        sensitivity="INTERNAL",
                        description=(
                            f"Autogenerated fallback variable from {source_type} "
                            f"field '{raw_field}'"
                        ),
                        created_by=self._agent_created_by,
                        source_ref=source_ref,
                        research_space_settings=research_space_settings,
                    )
                    created_variables += 1
                self._dictionary.create_synonym(
                    variable_id=existing_variable.id,
                    synonym=raw_field,
                    source=source_type.lower(),
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=research_space_settings,
                )
                created_synonyms += 1

        return created_variables, created_synonyms, created_entity_types

    def _reconcile_agent_dictionary_mutations(
        self,
        contract: EntityRecognitionContract,
    ) -> tuple[int, int, int]:
        """
        Reconcile dictionary mutations already applied by the agent tool loop.

        When a Flujo run id is present we treat dictionary writes as in-agent
        side effects and avoid duplicating them in post-hoc service logic.
        """
        created_variables = 0
        for variable_id in set(contract.created_definitions):
            if self._dictionary.get_variable(variable_id) is not None:
                created_variables += 1

        created_synonyms = 0
        for synonym in set(contract.created_synonyms):
            if self._dictionary.resolve_synonym(synonym) is not None:
                created_synonyms += 1

        created_entity_types = 0
        for entity_type_id in set(contract.created_entity_types):
            if self._dictionary.get_entity_type(entity_type_id) is not None:
                created_entity_types += 1

        return created_variables, created_synonyms, created_entity_types

    async def _process_document_with_extraction(  # noqa: PLR0913
        self,
        *,
        document: SourceDocument,
        contract: EntityRecognitionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        run_uuid: UUID | None,
        model_id: str | None,
        requested_shadow_mode: bool,
        research_space_settings: ResearchSpaceSettings,
        dictionary_variables_created: int,
        dictionary_synonyms_created: int,
        dictionary_entity_types_created: int,
        pipeline_run_id: str | None,
    ) -> EntityRecognitionDocumentOutcome:
        if self._extraction_service is None:
            msg = "Extraction service is not configured"
            raise RuntimeError(msg)

        try:
            extraction_outcome = (
                await self._extraction_service.extract_from_entity_recognition(
                    document=document,
                    recognition_contract=contract,
                    research_space_settings=research_space_settings,
                    model_id=model_id,
                    shadow_mode=requested_shadow_mode,
                )
            )
        except Exception as exc:  # noqa: BLE001 - surfaced via metadata/outcome
            logger.exception(
                "Extraction stage failed for document=%s",
                document.id,
            )
            failure_reason = "extraction_stage_failed"
            metadata_patch = self._build_outcome_metadata(
                contract=contract,
                governance=governance,
                run_id=run_id,
                pipeline_run_id=pipeline_run_id,
                wrote_to_kernel=False,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_result=None,
            )
            metadata_patch["extraction_stage_error"] = str(exc)
            metadata_patch["extraction_stage_failure_reason"] = failure_reason
            self._persist_failed_document(
                document=document,
                run_uuid=run_uuid,
                metadata_patch=metadata_patch,
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=failure_reason,
                review_required=governance.requires_review,
                shadow_mode=False,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                errors=(str(exc),),
            )

        extraction_run_uuid = (
            self._try_parse_uuid(extraction_outcome.run_id) or run_uuid
        )
        metadata_patch = self._build_outcome_metadata(
            contract=contract,
            governance=governance,
            run_id=run_id,
            pipeline_run_id=pipeline_run_id,
            wrote_to_kernel=extraction_outcome.wrote_to_kernel,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_result=None,
        )
        metadata_patch = self._merge_metadata(
            metadata_patch,
            self._build_extraction_metadata(extraction_outcome),
        )

        review_required = (
            governance.requires_review or extraction_outcome.review_required
        )
        if extraction_outcome.status == "failed":
            self._persist_failed_document(
                document=document,
                run_uuid=extraction_run_uuid,
                metadata_patch=metadata_patch,
            )
            return EntityRecognitionDocumentOutcome(
                document_id=document.id,
                status="failed",
                reason=extraction_outcome.reason,
                review_required=review_required,
                shadow_mode=extraction_outcome.shadow_mode,
                wrote_to_kernel=False,
                run_id=run_id,
                dictionary_variables_created=dictionary_variables_created,
                dictionary_synonyms_created=dictionary_synonyms_created,
                dictionary_entity_types_created=dictionary_entity_types_created,
                ingestion_entities_created=(
                    extraction_outcome.ingestion_entities_created
                ),
                ingestion_observations_created=(
                    extraction_outcome.ingestion_observations_created
                ),
                errors=extraction_outcome.errors,
            )

        self._persist_extracted_document(
            document=document,
            run_uuid=extraction_run_uuid,
            metadata_patch=metadata_patch,
        )
        return EntityRecognitionDocumentOutcome(
            document_id=document.id,
            status="extracted",
            reason=extraction_outcome.reason,
            review_required=review_required,
            shadow_mode=extraction_outcome.shadow_mode,
            wrote_to_kernel=extraction_outcome.wrote_to_kernel,
            run_id=run_id,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_entities_created=extraction_outcome.ingestion_entities_created,
            ingestion_observations_created=(
                extraction_outcome.ingestion_observations_created
            ),
            errors=extraction_outcome.errors,
        )

    def _build_pipeline_records(
        self,
        *,
        contract: EntityRecognitionContract,
        document: SourceDocument,
        raw_record: JSONObject,
        run_id: str | None,
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
                "entity_type": contract.primary_entity_type,
                "source_document_id": str(document.id),
                "source_record_id": source_record_id,
                "agent_decision": contract.decision,
            }
            if run_id:
                metadata["entity_recognition_run_id"] = run_id

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

    def _persist_extracted_document(
        self,
        *,
        document: SourceDocument,
        run_uuid: UUID | None,
        metadata_patch: JSONObject,
    ) -> SourceDocument:
        extracted = document.mark_extracted(
            extraction_agent_run_id=run_uuid,
            extracted_at=datetime.now(UTC),
        )
        updated = extracted.model_copy(
            update={
                "metadata": self._merge_metadata(
                    extracted.metadata,
                    metadata_patch,
                ),
            },
        )
        return self._source_documents.upsert(updated)

    def _persist_failed_document(
        self,
        *,
        document: SourceDocument,
        run_uuid: UUID | None,
        metadata_patch: JSONObject,
    ) -> SourceDocument:
        failed = document.model_copy(
            update={
                "extraction_status": DocumentExtractionStatus.FAILED,
                "extraction_agent_run_id": run_uuid,
                "updated_at": datetime.now(UTC),
                "metadata": self._merge_metadata(document.metadata, metadata_patch),
            },
        )
        return self._source_documents.upsert(failed)

    @staticmethod
    def _merge_metadata(
        existing: JSONObject,
        patch: JSONObject,
    ) -> JSONObject:
        merged: JSONObject = {
            str(key): to_json_value(value) for key, value in existing.items()
        }
        for key, value in patch.items():
            merged[str(key)] = to_json_value(value)
        return merged

    @staticmethod
    def _resolve_run_id(contract: EntityRecognitionContract) -> str | None:
        run_id = contract.agent_run_id
        if not isinstance(run_id, str):
            return None
        normalized = run_id.strip()
        return normalized or None

    @staticmethod
    def _try_parse_uuid(raw_value: str | None) -> UUID | None:
        if raw_value is None:
            return None
        try:
            return UUID(raw_value)
        except ValueError:
            return None

    @staticmethod
    def _normalize_identifier(
        value: str,
        *,
        prefix: str,
        max_length: int,
    ) -> str:
        stripped = value.strip()
        cleaned = _ID_CLEANUP_PATTERN.sub("_", stripped.upper())
        normalized = cleaned.strip("_")
        normalized = re.sub(r"_+", "_", normalized)
        if not normalized:
            normalized = prefix
        return normalized[:max_length]

    @classmethod
    def _to_canonical_name(cls, field_name: str) -> str:
        base = cls._normalize_identifier(
            field_name,
            prefix="field",
            max_length=128,
        )
        return base.lower()

    @staticmethod
    def _to_display_name(field_name: str) -> str:
        tokens = _SEPARATOR_PATTERN.split(field_name.strip())
        words = [token.capitalize() for token in tokens if token]
        display = " ".join(words)
        return display[:255] if display else "Unnamed Field"

    @classmethod
    def _resolve_variable_id(
        cls,
        *,
        explicit_variable_id: str | None,
        field_name: str,
    ) -> str:
        if isinstance(explicit_variable_id, str) and explicit_variable_id.strip():
            return cls._normalize_identifier(
                explicit_variable_id,
                prefix="VAR_AUTO",
                max_length=64,
            )
        normalized_field = cls._normalize_identifier(
            field_name,
            prefix="FIELD",
            max_length=56,
        )
        return f"VAR_{normalized_field}"[:64]

    @staticmethod
    def _infer_data_type(value: JSONValue) -> str:  # noqa: PLR0911
        if isinstance(value, bool):
            return "BOOLEAN"
        if isinstance(value, int):
            return "INTEGER"
        if isinstance(value, float):
            return "FLOAT"
        if isinstance(value, dict | list):
            return "JSON"
        if isinstance(value, str):
            normalized = value.strip()
            if _ISO_DATE_ONLY_PATTERN.match(normalized):
                return "DATE"
            try:
                datetime.fromisoformat(normalized)
            except ValueError:
                return "STRING"
            return "DATE"
        return "STRING"

    @staticmethod
    def _infer_domain_context(source_type: str) -> str:
        normalized = source_type.strip().lower()
        if normalized == "clinvar":
            return "genomics"
        if normalized == "pubmed":
            return "clinical"
        return "general"

    @staticmethod
    def _build_run_summary(
        *,
        outcomes: list[EntityRecognitionDocumentOutcome],
        requested: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> EntityRecognitionRunSummary:
        extracted = sum(1 for outcome in outcomes if outcome.status == "extracted")
        failed = sum(1 for outcome in outcomes if outcome.status == "failed")
        skipped = sum(1 for outcome in outcomes if outcome.status == "skipped")
        review_required = sum(1 for outcome in outcomes if outcome.review_required)
        shadow_runs = sum(1 for outcome in outcomes if outcome.shadow_mode)

        dictionary_variables_created = sum(
            outcome.dictionary_variables_created for outcome in outcomes
        )
        dictionary_synonyms_created = sum(
            outcome.dictionary_synonyms_created for outcome in outcomes
        )
        dictionary_entity_types_created = sum(
            outcome.dictionary_entity_types_created for outcome in outcomes
        )
        ingestion_entities_created = sum(
            outcome.ingestion_entities_created for outcome in outcomes
        )
        ingestion_observations_created = sum(
            outcome.ingestion_observations_created for outcome in outcomes
        )

        errors: list[str] = []
        for outcome in outcomes:
            errors.extend(outcome.errors)

        return EntityRecognitionRunSummary(
            requested=requested,
            processed=len(outcomes),
            extracted=extracted,
            failed=failed,
            skipped=skipped,
            review_required=review_required,
            shadow_runs=shadow_runs,
            dictionary_variables_created=dictionary_variables_created,
            dictionary_synonyms_created=dictionary_synonyms_created,
            dictionary_entity_types_created=dictionary_entity_types_created,
            ingestion_entities_created=ingestion_entities_created,
            ingestion_observations_created=ingestion_observations_created,
            errors=tuple(errors),
            started_at=started_at,
            completed_at=completed_at,
        )


__all__ = [
    "EntityRecognitionDocumentOutcome",
    "EntityRecognitionRunSummary",
    "EntityRecognitionService",
    "EntityRecognitionServiceDependencies",
]
