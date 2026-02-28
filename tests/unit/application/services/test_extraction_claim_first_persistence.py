"""Unit coverage for claim-first extraction relation persistence behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from src.application.agents.services.extraction_service import (
    ExtractionService,
    ExtractionServiceDependencies,
)
from src.application.services.kernel.dictionary_management_service import (
    DictionaryManagementService,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.entity_recognition import EntityRecognitionContract
from src.domain.agents.contracts.extraction import (
    ExtractedRelation,
    ExtractionContract,
)
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user import UserRole, UserStatus
from src.domain.entities.user_data_source import SourceType
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.dictionary import DictionaryDomainContextModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)
from src.type_definitions.ingestion import IngestResult

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.entities.kernel.dictionary import DictionarySearchResult


class _DeterministicHarness(DictionarySearchHarnessPort):
    """Deterministic dictionary search harness for tests."""

    def __init__(self, repository: SqlAlchemyDictionaryRepository) -> None:
        self._repository = repository

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        return self._repository.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )


class _FixedExtractionAgent(ExtractionAgentPort):
    """Returns one predefined extraction contract."""

    def __init__(self, contract: ExtractionContract) -> None:
        self._contract = contract

    async def extract(
        self,
        context: ExtractionContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionContract:
        del context, model_id
        return self._contract

    async def close(self) -> None:
        return None


class _NoopIngestionPipeline:
    """No-op ingestion pipeline used for extraction relation tests."""

    def run(self, records, research_space_id: str) -> IngestResult:
        del records, research_space_id
        return IngestResult(success=True, entities_created=0, observations_created=0)


def _build_document(
    *,
    source_id: str,
    research_space_id: str,
) -> SourceDocument:
    return SourceDocument(
        id=uuid4(),
        source_id=UUID(source_id),
        research_space_id=UUID(research_space_id),
        external_record_id="pubmed:test-claim-first",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.JSON,
        raw_storage_key="tests/pubmed/test.json",
        enrichment_status=EnrichmentStatus.ENRICHED,
        extraction_status=DocumentExtractionStatus.PENDING,
        metadata={
            "raw_record": {
                "pmid": "99999999",
                "title": "Claim-first extraction persistence test",
                "abstract": "Deterministic integration payload",
            },
        },
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_recognition_contract(document_id: str) -> EntityRecognitionContract:
    return EntityRecognitionContract(
        decision="generated",
        confidence_score=0.95,
        rationale="Deterministic recognition for claim-first persistence tests.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator=f"source_document:{document_id}",
                excerpt="Deterministic test payload",
                relevance=0.9,
            ),
        ],
        source_type="pubmed",
        document_id=document_id,
        primary_entity_type="PUBLICATION",
        field_candidates=[],
        recognized_entities=[],
        recognized_observations=[],
        pipeline_payloads=[],
        shadow_mode=False,
        agent_run_id="entity-recognition-test-run",
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_claim_first_extraction_persists_all_states(  # noqa: PLR0915
    db_session,
) -> None:
    db_session.add(
        DictionaryDomainContextModel(
            id="clinical",
            display_name="Clinical",
            description="Clinical domain for claim-first unit tests",
        ),
    )
    db_session.flush()

    user = UserModel(
        email=f"claim-first-{uuid4().hex}@example.com",
        username=f"claim-first-{uuid4().hex}",
        full_name="Claim First Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"claim-first-space-{uuid4().hex[:12]}",
        name="Claim First Test Space",
        description="Unit test space for claim-first extraction persistence.",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    source = UserDataSourceModel(
        id=str(uuid4()),
        owner_id=str(user.id),
        research_space_id=str(space.id),
        name="Claim First Source",
        description="Source for extraction persistence tests",
        source_type=SourceTypeEnum.PUBMED,
        configuration={"query": "MED13"},
        status=SourceStatusEnum.ACTIVE,
        ingestion_schedule={},
        quality_metrics={},
        tags=[],
        version="1.0",
    )
    db_session.add(source)
    db_session.flush()

    dictionary_repo = SqlAlchemyDictionaryRepository(db_session)
    dictionary_service = DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=_DeterministicHarness(dictionary_repo),
        embedding_provider=None,
    )
    dictionary_service.create_entity_type(
        entity_type="GENE",
        display_name="Gene",
        description="Gene entity type",
        domain_context="clinical",
        created_by="manual:test",
        source_ref="tests:claim-first",
    )
    dictionary_service.create_entity_type(
        entity_type="PHENOTYPE",
        display_name="Phenotype",
        description="Phenotype entity type",
        domain_context="clinical",
        created_by="manual:test",
        source_ref="tests:claim-first",
    )
    dictionary_service.create_relation_type(
        relation_type="ASSOCIATED_WITH",
        display_name="Associated with",
        description="Association relation type",
        domain_context="clinical",
        created_by="manual:test",
        source_ref="tests:claim-first",
    )
    dictionary_service.create_relation_type(
        relation_type="TARGETS",
        display_name="Targets",
        description="Targets relation type",
        domain_context="clinical",
        created_by="manual:test",
        source_ref="tests:claim-first",
    )
    dictionary_service.create_relation_constraint(
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        is_allowed=True,
        requires_evidence=True,
        created_by="manual:test",
        source_ref="tests:claim-first",
    )
    # Explicit forbidden constraint for this test matrix.
    dictionary_service.create_relation_constraint(
        source_type="GENE",
        relation_type="TARGETS",
        target_type="PHENOTYPE",
        is_allowed=False,
        requires_evidence=True,
        created_by="manual:test",
        source_ref="tests:claim-first",
    )

    entity_repo = SqlAlchemyKernelEntityRepository(db_session)
    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    _ = entity_repo.create(
        research_space_id=str(space.id),
        entity_type="GENE",
        display_label="MED13",
        metadata={},
    )
    _ = entity_repo.create(
        research_space_id=str(space.id),
        entity_type="PHENOTYPE",
        display_label="Cardiomyopathy",
        metadata={},
    )

    relations = [
        ExtractedRelation(
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Cardiomyopathy",
            confidence=0.92,
        ),
        ExtractedRelation(
            source_type="GENE",
            relation_type="TARGETS",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Cardiomyopathy",
            confidence=0.91,
        ),
        ExtractedRelation(
            source_type="GENE",
            relation_type="POTENTIATES",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Cardiomyopathy",
            confidence=0.88,
        ),
        ExtractedRelation(
            source_type=" ",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label="Cardiomyopathy",
            confidence=0.82,
        ),
        ExtractedRelation(
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label=" ",
            confidence=0.81,
        ),
        ExtractedRelation(
            source_type="GENE",
            relation_type="INTERACTS_WITH",
            target_type="GENE",
            source_label="MED13",
            target_label="MED13",
            confidence=0.87,
        ),
    ]
    extraction_contract = ExtractionContract(
        decision="generated",
        confidence_score=0.93,
        rationale="Exercise all claim-first validation states.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator="tests:claim-first",
                excerpt="Deterministic extracted relations",
                relevance=0.9,
            ),
        ],
        source_type="pubmed",
        document_id="claim-first-doc",
        observations=[],
        relations=relations,
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=False,
        agent_run_id="extraction-test-run",
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
            extraction_agent=_FixedExtractionAgent(extraction_contract),
            ingestion_pipeline=_NoopIngestionPipeline(),
            relation_repository=relation_repo,
            relation_claim_repository=claim_repo,
            entity_repository=entity_repo,
            dictionary_service=dictionary_service,
            review_queue_submitter=submit_review_item,
        ),
    )

    document = _build_document(
        source_id=str(source.id),
        research_space_id=str(space.id),
    )
    recognition_contract = _build_recognition_contract(str(document.id))

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition_contract,
        research_space_settings={"relation_governance_mode": "HUMAN_IN_LOOP"},
    )
    db_session.commit()

    assert outcome.status == "extracted"
    assert outcome.persisted_relations_count == 3
    assert outcome.pending_review_relations_count == 3

    claims = claim_repo.find_by_research_space(str(space.id), limit=20, offset=0)
    assert len(claims) == 6
    states = {claim.validation_state for claim in claims}
    assert states == {
        "ALLOWED",
        "FORBIDDEN",
        "UNDEFINED",
        "INVALID_COMPONENTS",
        "ENDPOINT_UNRESOLVED",
        "SELF_LOOP",
    }

    persistable_claims = [
        claim for claim in claims if claim.persistability == "PERSISTABLE"
    ]
    non_persistable_claims = [
        claim for claim in claims if claim.persistability == "NON_PERSISTABLE"
    ]
    assert len(persistable_claims) == 3
    assert len(non_persistable_claims) == 3
    assert all(claim.linked_relation_id is not None for claim in persistable_claims)
    assert all(claim.linked_relation_id is None for claim in non_persistable_claims)

    persisted_relations = relation_repo.find_by_research_space(
        str(space.id),
        limit=20,
        offset=0,
    )
    assert len(persisted_relations) == 3
    assert all(relation.curation_status == "DRAFT" for relation in persisted_relations)

    queued_relation_claims = [
        item for item in queued_items if item[0] == "relation_claim"
    ]
    queued_relations = [item for item in queued_items if item[0] == "relation"]
    assert len(queued_relation_claims) == 3
    assert len(queued_relations) == 3
    assert all(item[2] == str(space.id) for item in queued_relation_claims)
    assert any(item[3] == "high" for item in queued_relation_claims)
