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
        self.calls: list[tuple[list[RawRecord], str]] = []

    def run(self, records: list[RawRecord], research_space_id: str) -> IngestResult:
        self.calls.append((records, research_space_id))
        return self.result


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


def _build_extraction_contract(document_id: str) -> ExtractionContract:
    return ExtractionContract(
        decision="generated",
        confidence_score=0.92,
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
        relations=[],
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
