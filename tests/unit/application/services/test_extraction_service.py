"""Tests for ExtractionService orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from src.application.agents.services.extraction_service import (
    ExtractionService,
    ExtractionServiceDependencies,
)
from src.application.agents.services.governance_service import (
    GovernancePolicy,
    GovernanceService,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.entity_recognition import (
    EntityRecognitionContract,
    RecognizedObservationCandidate,
)
from src.domain.agents.contracts.extraction import (
    ExtractedObservation,
    ExtractedRelation,
    ExtractionContract,
    RejectedFact,
)
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user_data_source import SourceType
from src.type_definitions.ingestion import IngestResult, RawRecord
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.services.ingestion import IngestionProgressCallback


class StubExtractionAgent(ExtractionAgentPort):
    """Deterministic extraction agent stub."""

    def __init__(self, contract: ExtractionContract) -> None:
        self.contract = contract
        self.calls: list[ExtractionContext] = []

    async def extract(
        self,
        context: ExtractionContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionContract:
        _ = model_id
        self.calls.append(context)
        return self.contract

    async def close(self) -> None:
        return None


@dataclass
class StubIngestionPipeline:
    """Simple ingestion pipeline stub."""

    result: IngestResult

    def __post_init__(self) -> None:
        self.calls: list[
            tuple[list[RawRecord], str, IngestionProgressCallback | None]
        ] = []

    def run(
        self,
        records: list[RawRecord],
        research_space_id: str,
        *,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> IngestResult:
        self.calls.append((records, research_space_id, progress_callback))
        return self.result


@dataclass(frozen=True)
class _DictionaryEntityType:
    id: str
    is_active: bool = True
    review_status: str = "ACTIVE"


class StubDictionaryService:
    """Minimal dictionary double for extraction orchestration tests."""

    def __init__(self) -> None:
        self._entity_types: dict[str, _DictionaryEntityType] = {}

    def get_entity_type(
        self,
        entity_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> _DictionaryEntityType | None:
        normalized = entity_type_id.strip().upper()
        entity_type = self._entity_types.get(normalized)
        if entity_type is None:
            return None
        if include_inactive:
            return entity_type
        return entity_type if entity_type.is_active else None

    def create_entity_type(self, **kwargs: object) -> _DictionaryEntityType:
        normalized = str(kwargs["entity_type"]).strip().upper()
        created = _DictionaryEntityType(
            id=normalized,
            is_active=True,
            review_status="ACTIVE",
        )
        self._entity_types[normalized] = created
        return created

    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: str,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> _DictionaryEntityType:
        _ = reviewed_by
        _ = revocation_reason
        normalized = entity_type_id.strip().upper()
        existing = self._entity_types.get(normalized)
        if existing is None:
            msg = f"Unknown entity type: {normalized}"
            raise ValueError(msg)
        normalized_status = review_status.strip().upper()
        updated = _DictionaryEntityType(
            id=normalized,
            is_active=normalized_status == "ACTIVE",
            review_status=normalized_status,
        )
        self._entity_types[normalized] = updated
        return updated


def _build_dictionary_service() -> StubDictionaryService:
    return StubDictionaryService()


def _build_governance_service() -> GovernanceService:
    return GovernanceService(
        policy=GovernancePolicy(
            confidence_threshold=0.8,
            require_evidence=True,
        ),
    )


def _build_document(*, with_research_space: bool = True) -> SourceDocument:
    metadata = {
        "raw_record": to_json_value(
            {
                "clinvar_id": "1234",
                "clinical_significance": "pathogenic",
            },
        ),
    }
    return SourceDocument(
        id=uuid4(),
        research_space_id=uuid4() if with_research_space else None,
        source_id=uuid4(),
        external_record_id="clinvar:1234",
        source_type=SourceType.CLINVAR,
        document_format=DocumentFormat.CLINVAR_XML,
        raw_storage_key="clinvar/raw/1234.json",
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.EXTRACTED,
        metadata=metadata,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_recognition_contract(document_id: str) -> EntityRecognitionContract:
    return EntityRecognitionContract(
        decision="generated",
        confidence_score=0.95,
        rationale="Recognized clinical significance observation",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator=f"source_document:{document_id}",
                excerpt="clinical_significance field present",
                relevance=0.9,
            ),
        ],
        source_type="clinvar",
        document_id=document_id,
        primary_entity_type="VARIANT",
        field_candidates=["clinical_significance"],
        recognized_observations=[
            RecognizedObservationCandidate(
                field_name="clinical_significance",
                variable_id="VAR_CLINICAL_SIGNIFICANCE",
                value="pathogenic",
                confidence=0.9,
            ),
        ],
        pipeline_payloads=[],
        shadow_mode=False,
    )


def _build_extraction_contract(
    document_id: str,
    *,
    confidence_score: float = 0.92,
    relation_types: tuple[str, ...] = (),
) -> ExtractionContract:
    relations = [
        ExtractedRelation(
            source_type="VARIANT",
            relation_type=relation_type,
            target_type="PHENOTYPE",
            source_label="c.123A>G",
            target_label="Dilated cardiomyopathy",
            confidence=confidence_score,
        )
        for relation_type in relation_types
    ]
    return ExtractionContract(
        decision="generated",
        confidence_score=confidence_score,
        rationale="Validated mapped observation",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator=f"source_document:{document_id}",
                excerpt="Mapped to VAR_CLINICAL_SIGNIFICANCE",
                relevance=0.9,
            ),
        ],
        source_type="clinvar",
        document_id=document_id,
        observations=[
            ExtractedObservation(
                field_name="clinical_significance",
                variable_id="VAR_CLINICAL_SIGNIFICANCE",
                value="pathogenic",
                confidence=0.9,
            ),
        ],
        relations=relations,
        rejected_facts=[
            RejectedFact(
                fact_type="relation",
                reason="No validated relation candidate",
                payload={},
            ),
        ],
        pipeline_payloads=[{"clinical_significance": "pathogenic"}],
        shadow_mode=False,
    )


@pytest.mark.asyncio
async def test_extract_from_entity_recognition_writes_to_kernel() -> None:
    document = _build_document(with_research_space=True)
    recognition = _build_recognition_contract(str(document.id))
    extraction = _build_extraction_contract(str(document.id))
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = ExtractionService(
        dependencies=ExtractionServiceDependencies(
            extraction_agent=StubExtractionAgent(extraction),
            ingestion_pipeline=ingestion,
            dictionary_service=_build_dictionary_service(),
            governance_service=_build_governance_service(),
        ),
    )

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition,
        research_space_settings={},
    )

    assert outcome.status == "extracted"
    assert outcome.wrote_to_kernel is True
    assert outcome.observations_extracted == 1
    assert outcome.rejected_facts == 1
    assert ingestion.calls


@pytest.mark.asyncio
async def test_extract_from_entity_recognition_forwards_ingestion_progress_callback() -> (
    None
):
    document = _build_document(with_research_space=True)
    recognition = _build_recognition_contract(str(document.id))
    extraction = _build_extraction_contract(str(document.id))
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = ExtractionService(
        dependencies=ExtractionServiceDependencies(
            extraction_agent=StubExtractionAgent(extraction),
            ingestion_pipeline=ingestion,
            dictionary_service=_build_dictionary_service(),
            governance_service=_build_governance_service(),
        ),
    )
    callback_updates: list[object] = []

    def progress_callback(update: object) -> None:
        callback_updates.append(update)

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition,
        research_space_settings={},
        ingestion_progress_callback=progress_callback,
    )

    assert outcome.status == "extracted"
    assert ingestion.calls
    assert ingestion.calls[0][2] is progress_callback
    assert callback_updates == []


@pytest.mark.asyncio
async def test_extract_from_entity_recognition_respects_shadow_mode() -> None:
    document = _build_document(with_research_space=True)
    recognition = _build_recognition_contract(str(document.id))
    extraction = _build_extraction_contract(str(document.id))
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = ExtractionService(
        dependencies=ExtractionServiceDependencies(
            extraction_agent=StubExtractionAgent(extraction),
            ingestion_pipeline=ingestion,
            dictionary_service=_build_dictionary_service(),
            governance_service=_build_governance_service(),
        ),
    )

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition,
        research_space_settings={},
        shadow_mode=True,
    )

    assert outcome.status == "extracted"
    assert outcome.shadow_mode is True
    assert outcome.wrote_to_kernel is False
    assert ingestion.calls == []


@pytest.mark.asyncio
async def test_extract_from_entity_recognition_fails_without_research_space() -> None:
    document = _build_document(with_research_space=False)
    recognition = _build_recognition_contract(str(document.id))
    extraction = _build_extraction_contract(str(document.id))
    service = ExtractionService(
        dependencies=ExtractionServiceDependencies(
            extraction_agent=StubExtractionAgent(extraction),
            ingestion_pipeline=StubIngestionPipeline(
                IngestResult(success=True, entities_created=0, observations_created=0),
            ),
            dictionary_service=_build_dictionary_service(),
            governance_service=_build_governance_service(),
        ),
    )

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition,
        research_space_settings={},
    )

    assert outcome.status == "failed"
    assert outcome.reason == "missing_research_space_id"


@pytest.mark.asyncio
async def test_extract_from_entity_recognition_uses_relation_type_thresholds() -> None:
    document = _build_document(with_research_space=True)
    recognition = _build_recognition_contract(str(document.id))
    extraction = _build_extraction_contract(
        str(document.id),
        confidence_score=0.86,
        relation_types=("CAUSES",),
    )
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    service = ExtractionService(
        dependencies=ExtractionServiceDependencies(
            extraction_agent=StubExtractionAgent(extraction),
            ingestion_pipeline=ingestion,
            dictionary_service=_build_dictionary_service(),
            governance_service=_build_governance_service(),
        ),
    )

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition,
        research_space_settings={
            "review_threshold": 0.6,
            "relation_review_thresholds": {"CAUSES": 0.9},
        },
    )

    assert outcome.status == "extracted"
    assert outcome.wrote_to_kernel is True
    assert outcome.review_required is True
    assert outcome.reason == "processed"
    assert ingestion.calls


@pytest.mark.asyncio
async def test_extract_from_entity_recognition_enqueues_review_item() -> None:
    document = _build_document(with_research_space=True)
    recognition = _build_recognition_contract(str(document.id))
    extraction = _build_extraction_contract(
        str(document.id),
        confidence_score=0.86,
        relation_types=("CAUSES",),
    )
    ingestion = StubIngestionPipeline(
        IngestResult(success=True, entities_created=1, observations_created=1),
    )
    queued_items: list[tuple[str, str, str | None, str]] = []

    def submit_review_item(
        entity_type: str,
        entity_id: str,
        research_space_id: str | None,
        priority: str,
    ) -> None:
        queued_items.append((entity_type, entity_id, research_space_id, priority))

    service = ExtractionService(
        dependencies=ExtractionServiceDependencies(
            extraction_agent=StubExtractionAgent(extraction),
            ingestion_pipeline=ingestion,
            dictionary_service=_build_dictionary_service(),
            governance_service=_build_governance_service(),
            review_queue_submitter=submit_review_item,
        ),
    )

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition,
        research_space_settings={
            "review_threshold": 0.6,
            "relation_review_thresholds": {"CAUSES": 0.9},
        },
    )

    assert outcome.review_required is True
    assert queued_items == [
        (
            "extraction_document",
            str(document.id),
            str(document.research_space_id),
            "medium",
        ),
    ]
