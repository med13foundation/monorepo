"""Tests for EntityRecognitionService orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from src.application.agents.services.entity_recognition_service import (
    EntityRecognitionService,
    EntityRecognitionServiceDependencies,
)
from src.application.agents.services.extraction_service import (
    ExtractionDocumentOutcome,
)
from src.application.agents.services.governance_service import (
    GovernancePolicy,
    GovernanceService,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.entity_recognition import (
    EntityRecognitionContract,
    RecognizedEntityCandidate,
    RecognizedObservationCandidate,
)
from src.domain.agents.ports.entity_recognition_port import EntityRecognitionPort
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user_data_source import SourceType
from src.domain.repositories.source_document_repository import SourceDocumentRepository
from src.type_definitions.ingestion import IngestResult, RawRecord
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.application.agents.services.extraction_service import ExtractionService
    from src.domain.agents.contexts.entity_recognition_context import (
        EntityRecognitionContext,
    )
    from src.domain.ports.dictionary_port import DictionaryPort


class StubEntityRecognitionAgent(EntityRecognitionPort):
    """Simple stub for deterministic entity-recognition responses."""

    def __init__(self, contract: EntityRecognitionContract) -> None:
        self.contract = contract
        self.calls: list[EntityRecognitionContext] = []

    async def recognize(
        self,
        context: EntityRecognitionContext,
        *,
        model_id: str | None = None,
    ) -> EntityRecognitionContract:
        _ = model_id
        self.calls.append(context)
        return self.contract

    async def close(self) -> None:
        return None


class SlowEntityRecognitionAgent(EntityRecognitionPort):
    """Agent stub that intentionally exceeds configured timeout."""

    def __init__(
        self,
        *,
        contract: EntityRecognitionContract,
        delay_seconds: float,
    ) -> None:
        self._contract = contract
        self._delay_seconds = delay_seconds
        self.calls: list[EntityRecognitionContext] = []

    async def recognize(
        self,
        context: EntityRecognitionContext,
        *,
        model_id: str | None = None,
    ) -> EntityRecognitionContract:
        _ = model_id
        self.calls.append(context)
        await asyncio.sleep(self._delay_seconds)
        return self._contract

    async def close(self) -> None:
        return None


class StubSourceDocumentRepository(SourceDocumentRepository):
    """In-memory SourceDocument repository for service tests."""

    def __init__(self, documents: list[SourceDocument]) -> None:
        self._documents: dict[UUID, SourceDocument] = {doc.id: doc for doc in documents}
        self.recovery_calls: list[dict[str, object]] = []

    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        return self._documents.get(document_id)

    def get_by_source_external_record(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceDocument | None:
        for document in self._documents.values():
            if (
                document.source_id == source_id
                and document.external_record_id == external_record_id
            ):
                return document
        return None

    def upsert(self, document: SourceDocument) -> SourceDocument:
        self._documents[document.id] = document
        return document

    def upsert_many(
        self,
        documents: list[SourceDocument],
    ) -> list[SourceDocument]:
        for document in documents:
            self.upsert(document)
        return documents

    def list_pending_enrichment(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
    ) -> list[SourceDocument]:
        _ = source_id
        _ = research_space_id
        return list(self._documents.values())[: max(limit, 1)]

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
    ) -> list[SourceDocument]:
        pending = [
            document
            for document in self._documents.values()
            if document.extraction_status == DocumentExtractionStatus.PENDING
        ]
        if source_id is not None:
            pending = [
                document for document in pending if document.source_id == source_id
            ]
        if research_space_id is not None:
            pending = [
                document
                for document in pending
                if document.research_space_id == research_space_id
            ]
        return pending[: max(limit, 1)]

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int:
        self.recovery_calls.append(
            {
                "stale_before": stale_before,
                "source_id": source_id,
                "research_space_id": research_space_id,
                "ingestion_job_id": ingestion_job_id,
                "limit": limit,
            },
        )
        candidates = sorted(
            self._documents.values(),
            key=lambda document: document.updated_at,
        )[: max(limit, 1)]
        recovered = 0
        for document in candidates:
            if document.extraction_status != DocumentExtractionStatus.IN_PROGRESS:
                continue
            if source_id is not None and document.source_id != source_id:
                continue
            if (
                research_space_id is not None
                and document.research_space_id != research_space_id
            ):
                continue
            if (
                ingestion_job_id is not None
                and document.ingestion_job_id != ingestion_job_id
            ):
                continue
            if document.updated_at >= stale_before:
                continue
            metadata = dict(document.metadata)
            metadata["extraction_stale_recovery_reason"] = (
                "in_progress_timeout_recovered_to_pending"
            )
            self._documents[document.id] = document.model_copy(
                update={
                    "extraction_status": DocumentExtractionStatus.PENDING,
                    "extraction_agent_run_id": None,
                    "updated_at": datetime.now(UTC),
                    "metadata": metadata,
                },
            )
            recovered += 1
        return recovered

    def delete_by_source(self, source_id: UUID) -> int:
        existing_ids = [
            document_id
            for document_id, document in self._documents.items()
            if document.source_id == source_id
        ]
        for document_id in existing_ids:
            self._documents.pop(document_id, None)
        return len(existing_ids)

    def count_for_source(self, source_id: UUID) -> int:
        return sum(
            1
            for document in self._documents.values()
            if document.source_id == source_id
        )


class StubIngestionPipeline:
    """Ingestion pipeline stub that captures calls."""

    def __init__(self, result: IngestResult) -> None:
        self.result = result
        self.calls: list[tuple[list[RawRecord], str]] = []

    def run(self, records: list[RawRecord], research_space_id: str) -> IngestResult:
        self.calls.append((records, research_space_id))
        return self.result


class StubExtractionService:
    """Extraction service stub to assert ERA->EXA handoff."""

    def __init__(self, outcome: ExtractionDocumentOutcome) -> None:
        self.outcome = outcome
        self.calls: list[tuple[SourceDocument, EntityRecognitionContract]] = []

    async def extract_from_entity_recognition(
        self,
        *,
        document: SourceDocument,
        recognition_contract: EntityRecognitionContract,
        research_space_settings: object,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
    ) -> ExtractionDocumentOutcome:
        _ = research_space_settings
        _ = model_id
        _ = shadow_mode
        self.calls.append((document, recognition_contract))
        return self.outcome

    async def close(self) -> None:
        return None


class SlowExtractionService(StubExtractionService):
    """Extraction service stub that intentionally exceeds timeout."""

    def __init__(
        self,
        outcome: ExtractionDocumentOutcome,
        *,
        delay_seconds: float,
    ) -> None:
        super().__init__(outcome)
        self._delay_seconds = delay_seconds

    async def extract_from_entity_recognition(
        self,
        *,
        document: SourceDocument,
        recognition_contract: EntityRecognitionContract,
        research_space_settings: object,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
    ) -> ExtractionDocumentOutcome:
        _ = research_space_settings
        _ = model_id
        _ = shadow_mode
        self.calls.append((document, recognition_contract))
        await asyncio.sleep(self._delay_seconds)
        return self.outcome


@dataclass(frozen=True)
class _DictionaryEntityType:
    id: str


@dataclass(frozen=True)
class _DictionaryVariable:
    id: str


@dataclass(frozen=True)
class _DictionarySynonym:
    variable_id: str
    synonym: str


@dataclass(frozen=True)
class _DictionaryRelationType:
    id: str


@dataclass(frozen=True)
class _DictionaryRelationConstraint:
    source_type: str
    relation_type: str
    target_type: str


class StubDictionaryService:
    """Minimal dictionary double for service orchestration tests."""

    def __init__(self, *, domain_has_entries: bool = True) -> None:
        self._domain_has_entries = domain_has_entries
        self.entity_types: dict[str, _DictionaryEntityType] = {}
        self.relation_types: dict[str, _DictionaryRelationType] = {}
        self.relation_constraints: list[_DictionaryRelationConstraint] = []
        self.variables: dict[str, _DictionaryVariable] = {}
        self.synonyms: dict[str, str] = {}
        self.created_entity_types = 0
        self.created_variables = 0
        self.created_synonyms = 0
        self.created_relation_types = 0
        self.created_constraints = 0
        self.creation_policies: list[str] = []

    def _capture_creation_policy(self, kwargs: dict[str, object]) -> None:
        settings = kwargs.get("research_space_settings")
        if not isinstance(settings, dict):
            return
        raw_policy = settings.get("dictionary_agent_creation_policy")
        if isinstance(raw_policy, str) and raw_policy.strip():
            self.creation_policies.append(raw_policy.strip().upper())

    def get_entity_type(self, entity_type_id: str) -> _DictionaryEntityType | None:
        return self.entity_types.get(entity_type_id)

    def create_entity_type(self, **kwargs: object) -> _DictionaryEntityType:
        self._capture_creation_policy(kwargs)
        entity_type = str(kwargs["entity_type"])
        created = _DictionaryEntityType(id=entity_type)
        self.entity_types[entity_type] = created
        self.created_entity_types += 1
        return created

    def get_variable(self, variable_id: str) -> _DictionaryVariable | None:
        return self.variables.get(variable_id)

    def create_variable(self, **kwargs: object) -> _DictionaryVariable:
        self._capture_creation_policy(kwargs)
        variable_id = str(kwargs["variable_id"])
        created = _DictionaryVariable(id=variable_id)
        self.variables[variable_id] = created
        self.created_variables += 1
        return created

    def resolve_synonym(
        self,
        synonym: str,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> _DictionaryVariable | None:
        _ = domain_context
        _ = include_inactive
        variable_id = self.synonyms.get(synonym)
        if variable_id is None:
            return None
        return self.variables.get(variable_id)

    def create_synonym(self, **kwargs: object) -> _DictionarySynonym:
        variable_id = str(kwargs["variable_id"])
        synonym = str(kwargs["synonym"])
        if synonym in self.synonyms:
            msg = f"Synonym already exists: {synonym}"
            raise ValueError(msg)
        self.synonyms[synonym] = variable_id
        self.created_synonyms += 1
        return _DictionarySynonym(variable_id=variable_id, synonym=synonym)

    def dictionary_search_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[object]:
        _ = domain_context
        _ = limit
        _ = include_inactive
        if self._domain_has_entries:
            return [{"id": "existing"}]
        return []

    def get_relation_type(
        self,
        relation_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> _DictionaryRelationType | None:
        _ = include_inactive
        return self.relation_types.get(relation_type_id)

    def create_relation_type(self, **kwargs: object) -> _DictionaryRelationType:
        self._capture_creation_policy(kwargs)
        relation_type = str(kwargs["relation_type"])
        created = _DictionaryRelationType(id=relation_type)
        self.relation_types[relation_type] = created
        self.created_relation_types += 1
        self._domain_has_entries = True
        return created

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[_DictionaryRelationConstraint]:
        _ = include_inactive
        constraints = self.relation_constraints
        if source_type is not None:
            constraints = [
                constraint
                for constraint in constraints
                if constraint.source_type == source_type
            ]
        if relation_type is not None:
            constraints = [
                constraint
                for constraint in constraints
                if constraint.relation_type == relation_type
            ]
        return constraints

    def create_relation_constraint(
        self,
        **kwargs: object,
    ) -> _DictionaryRelationConstraint:
        self._capture_creation_policy(kwargs)
        constraint = _DictionaryRelationConstraint(
            source_type=str(kwargs["source_type"]),
            relation_type=str(kwargs["relation_type"]),
            target_type=str(kwargs["target_type"]),
        )
        self.relation_constraints.append(constraint)
        self.created_constraints += 1
        self._domain_has_entries = True
        return constraint


def _build_governance_service() -> GovernanceService:
    return GovernanceService(
        policy=GovernancePolicy(
            confidence_threshold=0.8,
            require_evidence=True,
        ),
    )


def _build_document(*, include_raw_record: bool = True) -> SourceDocument:
    metadata = (
        {
            "raw_record": to_json_value(
                {
                    "clinvar_id": "1234",
                    "gene_symbol": "MED13",
                    "clinical_significance": "pathogenic",
                },
            ),
        }
        if include_raw_record
        else {}
    )
    return SourceDocument(
        id=uuid4(),
        research_space_id=uuid4(),
        source_id=uuid4(),
        external_record_id="clinvar:clinvar_id:1234",
        source_type=SourceType.CLINVAR,
        document_format=DocumentFormat.CLINVAR_XML,
        raw_storage_key="clinvar/raw/batch.json",
        enrichment_status=EnrichmentStatus.PENDING,
        extraction_status=DocumentExtractionStatus.PENDING,
        metadata=metadata,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_contract(document_id: UUID) -> EntityRecognitionContract:
    return EntityRecognitionContract(
        decision="generated",
        confidence_score=0.95,
        rationale="ClinVar variant and observations recognized",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator=f"source_document:{document_id}",
                excerpt="ClinVar payload includes variant and significance fields",
                relevance=0.9,
            ),
        ],
        source_type="clinvar",
        document_id=str(document_id),
        primary_entity_type="VARIANT",
        field_candidates=["clinical_significance"],
        recognized_entities=[
            RecognizedEntityCandidate(
                entity_type="VARIANT",
                display_label="1234",
                identifiers={"clinvar_id": "1234"},
                confidence=0.9,
            ),
        ],
        recognized_observations=[
            RecognizedObservationCandidate(
                field_name="clinical_significance",
                value="pathogenic",
                confidence=0.9,
            ),
        ],
        pipeline_payloads=[
            {
                "clinvar_id": "1234",
                "gene_symbol": "MED13",
                "clinical_significance": "pathogenic",
            },
        ],
        shadow_mode=False,
    )


@pytest.mark.asyncio
async def test_process_document_writes_to_dictionary_and_kernel() -> None:
    document = _build_document(include_raw_record=True)
    repository = StubSourceDocumentRepository([document])
    contract = _build_contract(document.id)
    agent = StubEntityRecognitionAgent(contract=contract)
    dictionary = StubDictionaryService()
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "extracted"
    assert outcome.wrote_to_kernel is True
    assert outcome.dictionary_variables_created == 1
    assert outcome.dictionary_synonyms_created == 1
    assert outcome.dictionary_entity_types_created == 1
    assert ingestion.calls
    persisted_document = repository.get_by_id(document.id)
    assert persisted_document is not None
    assert persisted_document.extraction_status == DocumentExtractionStatus.EXTRACTED


@pytest.mark.asyncio
async def test_process_document_hands_off_to_extraction_service_when_configured() -> (
    None
):
    document = _build_document(include_raw_record=True)
    repository = StubSourceDocumentRepository([document])
    contract = _build_contract(document.id)
    agent = StubEntityRecognitionAgent(contract=contract)
    dictionary = StubDictionaryService()
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    extraction_outcome = ExtractionDocumentOutcome(
        document_id=document.id,
        status="extracted",
        reason="processed",
        review_required=False,
        shadow_mode=False,
        wrote_to_kernel=True,
        run_id="extract:clinvar:sha256:handoff-run",
        observations_extracted=1,
        relations_extracted=0,
        rejected_facts=0,
        ingestion_entities_created=2,
        ingestion_observations_created=3,
    )
    extraction_service = StubExtractionService(extraction_outcome)
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            extraction_service=cast("ExtractionService", extraction_service),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "extracted"
    assert outcome.wrote_to_kernel is True
    assert outcome.dictionary_variables_created == 1
    assert outcome.dictionary_synonyms_created == 1
    assert outcome.dictionary_entity_types_created == 1
    assert outcome.ingestion_entities_created == 2
    assert outcome.ingestion_observations_created == 3
    assert extraction_service.calls
    assert ingestion.calls == []
    persisted_document = repository.get_by_id(document.id)
    assert persisted_document is not None
    assert persisted_document.extraction_status == DocumentExtractionStatus.EXTRACTED
    assert (
        persisted_document.extraction_agent_run_id
        == "extract:clinvar:sha256:handoff-run"
    )
    assert (
        persisted_document.metadata.get("extraction_stage_status")
        == extraction_outcome.status
    )


@pytest.mark.asyncio
async def test_process_document_uses_shadow_mode_by_default() -> None:
    document = _build_document(include_raw_record=True)
    repository = StubSourceDocumentRepository([document])
    contract = _build_contract(document.id)
    agent = StubEntityRecognitionAgent(contract=contract)
    dictionary = StubDictionaryService()
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=True,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "extracted"
    assert outcome.shadow_mode is True
    assert outcome.wrote_to_kernel is False
    assert len(ingestion.calls) == 0
    assert dictionary.created_variables == 0
    persisted_document = repository.get_by_id(document.id)
    assert persisted_document is not None
    assert persisted_document.extraction_status == DocumentExtractionStatus.EXTRACTED


@pytest.mark.asyncio
async def test_process_document_fails_when_raw_record_missing() -> None:
    document = _build_document(include_raw_record=False)
    repository = StubSourceDocumentRepository([document])
    contract = _build_contract(document.id)
    agent = StubEntityRecognitionAgent(contract=contract)
    dictionary = StubDictionaryService()
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "failed"
    assert outcome.reason == "missing_raw_record_metadata"
    assert not agent.calls
    persisted_document = repository.get_by_id(document.id)
    assert persisted_document is not None
    assert persisted_document.extraction_status == DocumentExtractionStatus.FAILED


@pytest.mark.asyncio
async def test_process_document_uses_agent_mutation_reconciliation_when_run_id_present() -> (
    None
):
    document = _build_document(include_raw_record=True)
    repository = StubSourceDocumentRepository([document])
    dictionary = StubDictionaryService()
    dictionary.variables["VAR_CLINICAL_SIGNIFICANCE"] = _DictionaryVariable(
        id="VAR_CLINICAL_SIGNIFICANCE",
    )
    dictionary.synonyms["clinical_significance"] = "VAR_CLINICAL_SIGNIFICANCE"
    dictionary.entity_types["VARIANT"] = _DictionaryEntityType(id="VARIANT")

    contract = _build_contract(document.id).model_copy(
        update={
            "agent_run_id": "recognize:clinvar:sha256:mutation-run",
            "created_definitions": ["VAR_CLINICAL_SIGNIFICANCE"],
            "created_synonyms": ["clinical_significance"],
            "created_entity_types": ["VARIANT"],
        },
    )
    agent = StubEntityRecognitionAgent(contract=contract)
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "extracted"
    assert outcome.dictionary_variables_created == 1
    assert outcome.dictionary_synonyms_created == 1
    assert outcome.dictionary_entity_types_created == 1
    assert dictionary.created_variables == 0
    assert dictionary.created_synonyms == 0
    assert dictionary.created_entity_types == 0
    persisted_document = repository.get_by_id(document.id)
    assert persisted_document is not None
    assert (
        persisted_document.extraction_agent_run_id
        == "recognize:clinvar:sha256:mutation-run"
    )


@pytest.mark.asyncio
async def test_process_document_bootstraps_domain_when_dictionary_is_empty() -> None:
    document = _build_document(include_raw_record=True)
    repository = StubSourceDocumentRepository([document])
    contract = _build_contract(document.id)
    agent = StubEntityRecognitionAgent(contract=contract)
    dictionary = StubDictionaryService(domain_has_entries=False)
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "extracted"
    assert outcome.dictionary_entity_types_created >= 3
    assert outcome.dictionary_variables_created >= 2
    assert dictionary.created_relation_types >= 1
    assert dictionary.created_constraints >= 1
    assert "PENDING_REVIEW" in dictionary.creation_policies


@pytest.mark.asyncio
async def test_process_document_fails_when_agent_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS", "0.01")
    document = _build_document(include_raw_record=True)
    repository = StubSourceDocumentRepository([document])
    contract = _build_contract(document.id)
    agent = SlowEntityRecognitionAgent(contract=contract, delay_seconds=0.05)
    dictionary = StubDictionaryService()
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "failed"
    assert outcome.reason == "agent_execution_timeout"
    persisted_document = repository.get_by_id(document.id)
    assert persisted_document is not None
    assert persisted_document.extraction_status == DocumentExtractionStatus.FAILED
    assert (
        persisted_document.metadata.get("entity_recognition_failure_reason")
        == "agent_execution_timeout"
    )


@pytest.mark.asyncio
async def test_process_document_fails_when_extraction_stage_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MED13_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS",
        "0.01",
    )
    document = _build_document(include_raw_record=True)
    repository = StubSourceDocumentRepository([document])
    contract = _build_contract(document.id)
    agent = StubEntityRecognitionAgent(contract=contract)
    dictionary = StubDictionaryService()
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    extraction_service = SlowExtractionService(
        ExtractionDocumentOutcome(
            document_id=document.id,
            status="extracted",
            reason="processed",
            review_required=False,
            shadow_mode=False,
            wrote_to_kernel=True,
            run_id="extract:timeout-test",
        ),
        delay_seconds=0.05,
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            extraction_service=cast("ExtractionService", extraction_service),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    outcome = await service.process_document(document_id=document.id)

    assert outcome.status == "failed"
    assert outcome.reason == "extraction_stage_timeout"
    persisted_document = repository.get_by_id(document.id)
    assert persisted_document is not None
    assert persisted_document.extraction_status == DocumentExtractionStatus.FAILED
    assert (
        persisted_document.metadata.get("extraction_stage_failure_reason")
        == "extraction_stage_timeout"
    )


@pytest.mark.asyncio
async def test_process_pending_documents_recovers_stale_in_progress_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MED13_ENTITY_RECOGNITION_STALE_IN_PROGRESS_SECONDS", "30")
    stale_document = _build_document(include_raw_record=True).model_copy(
        update={
            "extraction_status": DocumentExtractionStatus.IN_PROGRESS,
            "updated_at": datetime.now(UTC) - timedelta(minutes=5),
            "extraction_agent_run_id": "stale-run-id",
        },
    )
    repository = StubSourceDocumentRepository([stale_document])
    contract = _build_contract(stale_document.id)
    agent = StubEntityRecognitionAgent(contract=contract)
    dictionary = StubDictionaryService()
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = EntityRecognitionService(
        dependencies=EntityRecognitionServiceDependencies(
            entity_recognition_agent=agent,
            source_document_repository=repository,
            ingestion_pipeline=ingestion,
            dictionary_service=cast("DictionaryPort", dictionary),
            governance_service=_build_governance_service(),
        ),
        default_shadow_mode=False,
    )

    summary = await service.process_pending_documents(
        limit=1,
        source_id=stale_document.source_id,
        research_space_id=stale_document.research_space_id,
    )

    assert len(repository.recovery_calls) == 1
    assert summary.processed == 1
    assert summary.extracted == 1
    persisted_document = repository.get_by_id(stale_document.id)
    assert persisted_document is not None
    assert persisted_document.extraction_status == DocumentExtractionStatus.EXTRACTED
    assert (
        persisted_document.metadata.get("extraction_stale_recovery_reason")
        == "in_progress_timeout_recovered_to_pending"
    )
