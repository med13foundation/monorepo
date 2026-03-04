"""Unit coverage for claim-first extraction relation persistence behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.application.agents.services.extraction_service import (
    ExtractionService,
    ExtractionServiceDependencies,
)
from src.application.services.kernel.concept_management_service import (
    ConceptManagementService,
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
from src.domain.agents.contracts.extraction_policy import (
    ExtractionPolicyContract,
    RelationTypeMappingProposal,
)
from src.domain.agents.ports.extraction_agent_port import ExtractionAgentPort
from src.domain.agents.ports.extraction_policy_agent_port import (
    ExtractionPolicyAgentPort,
)
from src.domain.entities.kernel.relations import (
    EvidenceSentenceGenerationRequest,
    EvidenceSentenceGenerationResult,
)
from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user import UserRole, UserStatus
from src.domain.entities.user_data_source import SourceType
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.domain.ports.evidence_sentence_harness_port import EvidenceSentenceHarnessPort
from src.infrastructure.llm.adapters.concept_decision_harness_adapter import (
    DeterministicConceptDecisionHarnessAdapter,
)
from src.infrastructure.repositories.kernel import (
    SqlAlchemyConceptRepository,
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.claim_evidence import ClaimEvidenceModel
from src.models.database.kernel.dictionary import DictionaryDomainContextModel
from src.models.database.kernel.relations import RelationEvidenceModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)
from src.type_definitions.ingestion import IngestResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.agents.contexts.extraction_policy_context import (
        ExtractionPolicyContext,
    )
    from src.domain.entities.kernel.dictionary import DictionarySearchResult
    from src.type_definitions.ingestion import RawRecord


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


class _FixedPolicyAgent(ExtractionPolicyAgentPort):
    """Returns one predefined extraction-policy contract."""

    def __init__(self, contract: ExtractionPolicyContract) -> None:
        self._contract = contract

    async def propose(
        self,
        context: ExtractionPolicyContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionPolicyContract:
        del context, model_id
        return self._contract

    async def close(self) -> None:
        return None


class _FixedEvidenceSentenceHarness(EvidenceSentenceHarnessPort):
    """Deterministic optional evidence-sentence harness for tests."""

    def __init__(self, result: EvidenceSentenceGenerationResult) -> None:
        self._result = result

    def generate(
        self,
        request: EvidenceSentenceGenerationRequest,
        *,
        model_id: str | None = None,
    ) -> EvidenceSentenceGenerationResult:
        del request, model_id
        return self._result


class _RaisingEvidenceSentenceHarness(EvidenceSentenceHarnessPort):
    """Harness stub that raises to validate fail-open persistence behavior."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def generate(
        self,
        request: EvidenceSentenceGenerationRequest,
        *,
        model_id: str | None = None,
    ) -> EvidenceSentenceGenerationResult:
        del request, model_id
        raise self._error


class _NoopIngestionPipeline:
    """No-op ingestion pipeline used for extraction relation tests."""

    def run(self, records: list[RawRecord], research_space_id: str) -> IngestResult:
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
                "abstract": (
                    "MED13 is associated with cardiomyopathy in deterministic "
                    "integration payloads. CNOT1 impairs DYRK1A signaling in "
                    "deterministic mapping payloads."
                ),
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


def _build_optional_missing_span_harness_fixture(
    *,
    db_session: Session,
    harness: EvidenceSentenceHarnessPort | None,
) -> tuple[
    ExtractionService,
    SqlAlchemyKernelRelationRepository,
    SqlAlchemyKernelRelationClaimRepository,
    UserDataSourceModel,
    ResearchSpaceModel,
]:
    domain_context_id = f"clinical_optional_{uuid4().hex[:12]}"
    optional_relation_type = f"ASSOCIATED_OPTIONAL_{uuid4().hex[:8].upper()}"
    db_session.add(
        DictionaryDomainContextModel(
            id=domain_context_id,
            display_name="Clinical",
            description="Clinical domain for optional evidence sentence harness tests",
        ),
    )
    db_session.flush()

    user = UserModel(
        email=f"optional-span-{uuid4().hex}@example.com",
        username=f"optional-span-{uuid4().hex}",
        full_name="Optional Span Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"optional-span-space-{uuid4().hex[:12]}",
        name="Optional Evidence Sentence Space",
        description="Unit test space for optional evidence sentence generation.",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    source = UserDataSourceModel(
        id=str(uuid4()),
        owner_id=str(user.id),
        research_space_id=str(space.id),
        name="Optional Evidence Source",
        description="Source for optional evidence sentence tests",
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
        domain_context=domain_context_id,
        created_by="manual:test",
        source_ref="tests:optional-span",
    )
    dictionary_service.create_entity_type(
        entity_type="PHENOTYPE",
        display_name="Phenotype",
        description="Phenotype entity type",
        domain_context=domain_context_id,
        created_by="manual:test",
        source_ref="tests:optional-span",
    )
    dictionary_service.create_relation_type(
        relation_type=optional_relation_type,
        display_name="Associated with",
        description="Association relation type",
        domain_context=domain_context_id,
        created_by="manual:test",
        source_ref="tests:optional-span",
    )
    dictionary_service.create_relation_constraint(
        source_type="GENE",
        relation_type=optional_relation_type,
        target_type="PHENOTYPE",
        is_allowed=True,
        requires_evidence=False,
        created_by="manual:test",
        source_ref="tests:optional-span",
    )

    entity_repo = SqlAlchemyKernelEntityRepository(db_session)
    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
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

    extraction_contract = ExtractionContract(
        decision="generated",
        confidence_score=0.89,
        rationale="Exercise optional evidence sentence harness behavior.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator="tests:optional-span",
                excerpt="Deterministic relation candidate without explicit span text.",
                relevance=0.86,
            ),
        ],
        source_type="pubmed",
        document_id="optional-span-doc",
        observations=[],
        relations=[
            ExtractedRelation(
                source_type="GENE",
                relation_type=optional_relation_type,
                target_type="PHENOTYPE",
                source_label="MED13",
                target_label="Cardiomyopathy",
                confidence=0.83,
            ),
        ],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=False,
        agent_run_id="optional-span-extraction-run",
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
            claim_evidence_repository=claim_evidence_repo,
            entity_repository=entity_repo,
            dictionary_service=dictionary_service,
            review_queue_submitter=submit_review_item,
            evidence_sentence_harness=harness,
        ),
    )
    return service, relation_repo, claim_repo, source, space


@pytest.mark.database
@pytest.mark.asyncio
async def test_claim_first_extraction_persists_all_states(  # noqa: PLR0915
    db_session: Session,
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
    concept_service = ConceptManagementService(
        concept_repo=SqlAlchemyConceptRepository(db_session),
        concept_harness=DeterministicConceptDecisionHarnessAdapter(),
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
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
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
            polarity="SUPPORT",
            claim_text="MED13 variants are associated with cardiomyopathy.",
            claim_section="results",
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
            claim_evidence_repository=claim_evidence_repo,
            entity_repository=entity_repo,
            dictionary_service=dictionary_service,
            concept_service=concept_service,
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
    assert outcome.persisted_relations_count == 1
    assert outcome.pending_review_relations_count == 1
    assert outcome.concept_members_created_count >= 2
    assert outcome.concept_aliases_created_count >= 2

    claims = claim_repo.find_by_research_space(str(space.id), limit=20, offset=0)
    assert len(claims) == 6
    assert any(claim.polarity == "SUPPORT" for claim in claims)
    assert sum(claim.polarity == "UNCERTAIN" for claim in claims) >= 1
    assert any(
        claim.claim_text == "MED13 variants are associated with cardiomyopathy."
        and claim.claim_section == "results"
        for claim in claims
    )
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
    assert (
        sum(claim.linked_relation_id is not None for claim in persistable_claims) == 1
    )
    assert all(claim.linked_relation_id is None for claim in non_persistable_claims)
    claim_evidence_rows = db_session.scalars(
        select(ClaimEvidenceModel).where(
            ClaimEvidenceModel.claim_id.in_([claim.id for claim in claims]),
        ),
    ).all()
    assert len(claim_evidence_rows) == len(claims)

    persisted_relations = relation_repo.find_by_research_space(
        str(space.id),
        limit=20,
        offset=0,
    )
    assert len(persisted_relations) == 1
    assert all(relation.curation_status == "DRAFT" for relation in persisted_relations)
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == persisted_relations[0].id,
        ),
    ).all()
    assert len(evidence_rows) == 1
    evidence_sentence = evidence_rows[0].evidence_sentence
    assert isinstance(evidence_sentence, str)
    normalized_evidence_sentence = evidence_sentence.casefold()
    assert "med13" in normalized_evidence_sentence
    assert "cardiomyopathy" in normalized_evidence_sentence

    queued_relation_claims = [
        item for item in queued_items if item[0] == "relation_claim"
    ]
    queued_relations = [item for item in queued_items if item[0] == "relation"]
    assert len(queued_relation_claims) == 5
    assert len(queued_relations) == 1
    assert all(item[2] == str(space.id) for item in queued_relation_claims)
    assert any(item[3] == "high" for item in queued_relation_claims)


@pytest.mark.database
@pytest.mark.asyncio
async def test_human_in_loop_canonicalizes_relation_type_from_policy_mapping(
    db_session: Session,
) -> None:
    db_session.add(
        DictionaryDomainContextModel(
            id="clinical_canonicalization",
            display_name="Clinical",
            description="Clinical domain for canonicalization unit tests",
        ),
    )
    db_session.flush()

    user = UserModel(
        email=f"canonicalization-{uuid4().hex}@example.com",
        username=f"canonicalization-{uuid4().hex}",
        full_name="Canonicalization Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"canonicalization-space-{uuid4().hex[:12]}",
        name="Canonicalization Test Space",
        description="Unit test space for relation canonicalization persistence.",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    source = UserDataSourceModel(
        id=str(uuid4()),
        owner_id=str(user.id),
        research_space_id=str(space.id),
        name="Canonicalization Source",
        description="Source for relation canonicalization tests",
        source_type=SourceTypeEnum.PUBMED,
        configuration={"query": "CNOT1"},
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
    concept_service = ConceptManagementService(
        concept_repo=SqlAlchemyConceptRepository(db_session),
        concept_harness=DeterministicConceptDecisionHarnessAdapter(),
    )
    dictionary_service.create_entity_type(
        entity_type="GENE",
        display_name="Gene",
        description="Gene entity type",
        domain_context="clinical_canonicalization",
        created_by="manual:test",
        source_ref="tests:canonicalization",
    )
    dictionary_service.create_relation_type(
        relation_type="GENETIC_INTERACTION_IMPAIRMENT",
        display_name="Genetic interaction impairment",
        description="A gene perturbation impairs interaction with another gene.",
        domain_context="clinical_canonicalization",
        created_by="manual:test",
        source_ref="tests:canonicalization",
    )

    entity_repo = SqlAlchemyKernelEntityRepository(db_session)
    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
    _ = entity_repo.create(
        research_space_id=str(space.id),
        entity_type="GENE",
        display_label="CNOT1",
        metadata={},
    )
    _ = entity_repo.create(
        research_space_id=str(space.id),
        entity_type="GENE",
        display_label="DYRK1A",
        metadata={},
    )

    extraction_contract = ExtractionContract(
        decision="generated",
        confidence_score=0.92,
        rationale="Exercise policy mapping canonicalization in HUMAN_IN_LOOP mode.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator="tests:canonicalization",
                excerpt="Deterministic mapped relation",
                relevance=0.9,
            ),
        ],
        source_type="pubmed",
        document_id="canonicalization-doc",
        observations=[],
        relations=[
            ExtractedRelation(
                source_type="GENE",
                relation_type="GENETIC_INTERACTION",
                target_type="GENE",
                source_label="CNOT1",
                target_label="DYRK1A",
                confidence=0.91,
            ),
        ],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=False,
        agent_run_id="canonicalization-extraction-run",
    )
    policy_contract = ExtractionPolicyContract(
        decision="generated",
        confidence_score=0.88,
        rationale="Map generic interaction into canonical impairment relation type.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator="tests:canonicalization:policy",
                excerpt="Observed relation type should map to canonical dictionary type.",
                relevance=0.8,
            ),
        ],
        source_type="pubmed",
        document_id="canonicalization-doc",
        unknown_patterns=[],
        relation_constraint_proposals=[],
        relation_type_mapping_proposals=[
            RelationTypeMappingProposal(
                source_type="GENE",
                observed_relation_type="GENETIC_INTERACTION",
                target_type="GENE",
                mapped_relation_type="GENETIC_INTERACTION_IMPAIRMENT",
                confidence=0.95,
                rationale="Prefer specific impairment interaction label.",
            ),
        ],
        agent_run_id="canonicalization-policy-run",
    )

    service = ExtractionService(
        dependencies=ExtractionServiceDependencies(
            extraction_agent=_FixedExtractionAgent(extraction_contract),
            extraction_policy_agent=_FixedPolicyAgent(policy_contract),
            ingestion_pipeline=_NoopIngestionPipeline(),
            relation_repository=relation_repo,
            relation_claim_repository=claim_repo,
            claim_evidence_repository=claim_evidence_repo,
            entity_repository=entity_repo,
            dictionary_service=dictionary_service,
            concept_service=concept_service,
            review_queue_submitter=lambda *_: None,
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
    assert outcome.persisted_relations_count == 0
    assert outcome.undefined_relations_count == 1

    persisted_relations = relation_repo.find_by_research_space(
        str(space.id),
        limit=10,
        offset=0,
    )
    assert len(persisted_relations) == 0

    claims = claim_repo.find_by_research_space(str(space.id), limit=10, offset=0)
    assert len(claims) == 1
    claim = claims[0]
    concept_refs = claim.metadata_payload.get("concept_refs")
    assert isinstance(concept_refs, dict)
    assert isinstance(concept_refs.get("concept_set_id"), str)
    assert isinstance(concept_refs.get("source_member_id"), str)
    assert isinstance(concept_refs.get("target_member_id"), str)
    assert claim.relation_type == "GENETIC_INTERACTION_IMPAIRMENT"
    canonicalization_metadata = claim.metadata_payload.get("canonicalization")
    assert isinstance(canonicalization_metadata, dict)
    assert canonicalization_metadata.get("strategy") == "policy_mapping_proposal"
    assert (
        canonicalization_metadata.get("observed_relation_type") == "GENETIC_INTERACTION"
    )
    assert (
        canonicalization_metadata.get("canonical_relation_type")
        == "GENETIC_INTERACTION_IMPAIRMENT"
    )


@pytest.mark.database
@pytest.mark.asyncio
async def test_optional_missing_span_uses_harness_sentence_when_available(
    db_session: Session,
) -> None:
    generated_sentence = (
        "MED13 may be contextually associated with cardiomyopathy based on the "
        "document-level extraction context."
    )
    harness = _FixedEvidenceSentenceHarness(
        EvidenceSentenceGenerationResult(
            outcome="generated",
            sentence=generated_sentence,
            source="artana_generated",
            confidence="medium",
            rationale="No direct span found; inferred from extraction context.",
            metadata={"run_id": "test-harness-success"},
        ),
    )
    service, relation_repo, claim_repo, source, space = (
        _build_optional_missing_span_harness_fixture(
            db_session=db_session,
            harness=harness,
        )
    )

    base_document = _build_document(
        source_id=str(source.id),
        research_space_id=str(space.id),
    )
    document = base_document.model_copy(
        update={
            "metadata": {
                "raw_record": {
                    "pmid": "88888888",
                    "title": "Optional evidence sentence harness success test",
                    "abstract": (
                        "MED13 was analyzed in a deterministic setup with no direct "
                        "target cooccurrence span in this abstract."
                    ),
                },
            },
        },
    )
    recognition_contract = _build_recognition_contract(str(document.id))

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition_contract,
        research_space_settings={"relation_governance_mode": "HUMAN_IN_LOOP"},
    )
    db_session.commit()

    assert outcome.status == "extracted"
    assert outcome.persisted_relations_count == 1

    persisted_relations = relation_repo.find_by_research_space(
        str(space.id),
        limit=10,
        offset=0,
    )
    assert len(persisted_relations) == 1
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == persisted_relations[0].id,
        ),
    ).all()
    assert len(evidence_rows) == 1
    evidence_row = evidence_rows[0]
    assert evidence_row.evidence_sentence == generated_sentence
    assert evidence_row.evidence_sentence_source == "artana_generated"
    assert evidence_row.evidence_sentence_confidence == "medium"
    assert (
        evidence_row.evidence_sentence_rationale
        == "No direct span found; inferred from extraction context."
    )

    claims = claim_repo.find_by_research_space(str(space.id), limit=10, offset=0)
    assert len(claims) == 1
    claim_evidence_rows = db_session.scalars(
        select(ClaimEvidenceModel).where(ClaimEvidenceModel.claim_id == claims[0].id),
    ).all()
    assert len(claim_evidence_rows) == 1
    assert claim_evidence_rows[0].sentence == generated_sentence
    assert claim_evidence_rows[0].sentence_source == "artana_generated"
    assert claim_evidence_rows[0].sentence_confidence == "medium"
    assert (
        claim_evidence_rows[0].sentence_rationale
        == "No direct span found; inferred from extraction context."
    )
    relation_evidence = claims[0].metadata_payload.get("relation_evidence")
    assert isinstance(relation_evidence, dict)
    assert relation_evidence.get("span_status") == "missing"
    assert relation_evidence.get("evidence_sentence_source") == "artana_generated"
    assert relation_evidence.get("evidence_sentence_confidence") == "medium"
    assert (
        relation_evidence.get("evidence_sentence_rationale")
        == "No direct span found; inferred from extraction context."
    )
    assert relation_evidence.get("evidence_sentence_failure_reason") is None


@pytest.mark.database
@pytest.mark.asyncio
async def test_optional_missing_span_persists_fail_open_when_harness_errors(
    db_session: Session,
) -> None:
    service, relation_repo, claim_repo, source, space = (
        _build_optional_missing_span_harness_fixture(
            db_session=db_session,
            harness=_RaisingEvidenceSentenceHarness(RuntimeError("timeout")),
        )
    )

    base_document = _build_document(
        source_id=str(source.id),
        research_space_id=str(space.id),
    )
    document = base_document.model_copy(
        update={
            "metadata": {
                "raw_record": {
                    "pmid": "77777777",
                    "title": "Optional evidence sentence harness fail-open test",
                    "abstract": (
                        "MED13 was analyzed in a deterministic setup. "
                        "No direct target cooccurrence span exists here."
                    ),
                },
            },
        },
    )
    recognition_contract = _build_recognition_contract(str(document.id))

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition_contract,
        research_space_settings={"relation_governance_mode": "HUMAN_IN_LOOP"},
    )
    db_session.commit()

    assert outcome.status == "extracted"
    assert outcome.persisted_relations_count == 1

    persisted_relations = relation_repo.find_by_research_space(
        str(space.id),
        limit=10,
        offset=0,
    )
    assert len(persisted_relations) == 1
    evidence_rows = db_session.scalars(
        select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == persisted_relations[0].id,
        ),
    ).all()
    assert len(evidence_rows) == 1
    evidence_row = evidence_rows[0]
    assert evidence_row.evidence_sentence is None
    assert evidence_row.evidence_sentence_source is None
    assert evidence_row.evidence_sentence_confidence is None
    assert evidence_row.evidence_sentence_rationale is None

    claims = claim_repo.find_by_research_space(str(space.id), limit=10, offset=0)
    assert len(claims) == 1
    claim_evidence_rows = db_session.scalars(
        select(ClaimEvidenceModel).where(ClaimEvidenceModel.claim_id == claims[0].id),
    ).all()
    assert len(claim_evidence_rows) == 1
    assert claim_evidence_rows[0].sentence is None
    assert claim_evidence_rows[0].sentence_source is None
    assert claim_evidence_rows[0].sentence_confidence is None
    assert claim_evidence_rows[0].sentence_rationale is None
    claim_evidence_metadata = claim_evidence_rows[0].metadata_payload
    assert isinstance(claim_evidence_metadata, dict)
    stored_failure_reason = claim_evidence_metadata.get(
        "evidence_sentence_failure_reason",
    )
    assert isinstance(stored_failure_reason, str)
    assert stored_failure_reason.startswith("evidence_sentence_harness_error:")
    relation_evidence = claims[0].metadata_payload.get("relation_evidence")
    assert isinstance(relation_evidence, dict)
    assert relation_evidence.get("span_status") == "missing"
    failure_reason = relation_evidence.get("evidence_sentence_failure_reason")
    assert isinstance(failure_reason, str)
    assert failure_reason.startswith("evidence_sentence_harness_error:")


@pytest.mark.database
@pytest.mark.asyncio
async def test_required_evidence_span_blocks_relation_persistence(  # noqa: PLR0915
    db_session: Session,
) -> None:
    db_session.add(
        DictionaryDomainContextModel(
            id="clinical_span_gate",
            display_name="Clinical",
            description="Clinical domain for relation evidence-span gating tests",
        ),
    )
    db_session.flush()

    user = UserModel(
        email=f"span-gate-{uuid4().hex}@example.com",
        username=f"span-gate-{uuid4().hex}",
        full_name="Evidence Span Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.flush()

    space = ResearchSpaceModel(
        slug=f"span-gate-space-{uuid4().hex[:12]}",
        name="Evidence Span Gate Test Space",
        description="Unit test space for relation evidence-span gate.",
        owner_id=user.id,
        status="active",
    )
    db_session.add(space)
    db_session.flush()

    source = UserDataSourceModel(
        id=str(uuid4()),
        owner_id=str(user.id),
        research_space_id=str(space.id),
        name="Evidence Span Source",
        description="Source for evidence-span persistence tests",
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
        domain_context="clinical_span_gate",
        created_by="manual:test",
        source_ref="tests:span-gate",
    )
    dictionary_service.create_entity_type(
        entity_type="PHENOTYPE",
        display_name="Phenotype",
        description="Phenotype entity type",
        domain_context="clinical_span_gate",
        created_by="manual:test",
        source_ref="tests:span-gate",
    )
    dictionary_service.create_relation_type(
        relation_type="ASSOCIATED_WITH",
        display_name="Associated with",
        description="Association relation type",
        domain_context="clinical_span_gate",
        created_by="manual:test",
        source_ref="tests:span-gate",
    )
    dictionary_service.create_relation_constraint(
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        is_allowed=True,
        requires_evidence=True,
        created_by="manual:test",
        source_ref="tests:span-gate",
    )

    entity_repo = SqlAlchemyKernelEntityRepository(db_session)
    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    claim_repo = SqlAlchemyKernelRelationClaimRepository(db_session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(db_session)
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

    extraction_contract = ExtractionContract(
        decision="generated",
        confidence_score=0.92,
        rationale="Exercise required evidence-span gate for allowed relation.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator="tests:span-gate",
                excerpt="Deterministic relation candidate without cooccurrence span",
                relevance=0.9,
            ),
        ],
        source_type="pubmed",
        document_id="span-gate-doc",
        observations=[],
        relations=[
            ExtractedRelation(
                source_type="GENE",
                relation_type="ASSOCIATED_WITH",
                target_type="PHENOTYPE",
                source_label="MED13",
                target_label="Cardiomyopathy",
                confidence=0.9,
            ),
        ],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=False,
        agent_run_id="span-gate-extraction-run",
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
            claim_evidence_repository=claim_evidence_repo,
            entity_repository=entity_repo,
            dictionary_service=dictionary_service,
            review_queue_submitter=submit_review_item,
        ),
    )

    base_document = _build_document(
        source_id=str(source.id),
        research_space_id=str(space.id),
    )
    document = base_document.model_copy(
        update={
            "metadata": {
                "raw_record": {
                    "pmid": "99999999",
                    "title": "Evidence span gate relation persistence test",
                    "abstract": (
                        "MED13 variants were analyzed in a deterministic setup. "
                        "No phenotype target mention is present in this abstract."
                    ),
                },
            },
        },
    )
    recognition_contract = _build_recognition_contract(str(document.id))

    outcome = await service.extract_from_entity_recognition(
        document=document,
        recognition_contract=recognition_contract,
        research_space_settings={"relation_governance_mode": "HUMAN_IN_LOOP"},
    )
    db_session.commit()

    assert outcome.status == "extracted"
    assert outcome.persisted_relations_count == 0
    assert "relation_evidence_span_missing" in outcome.rejected_relation_reasons
    assert (
        outcome.extraction_funnel.get("relation_candidates_evidence_span_missing") == 1
    )

    persisted_relations = relation_repo.find_by_research_space(
        str(space.id),
        limit=10,
        offset=0,
    )
    assert len(persisted_relations) == 0

    claims = claim_repo.find_by_research_space(str(space.id), limit=10, offset=0)
    assert len(claims) == 1
    claim = claims[0]
    claim_evidence_rows = db_session.scalars(
        select(ClaimEvidenceModel).where(ClaimEvidenceModel.claim_id == claim.id),
    ).all()
    assert len(claim_evidence_rows) == 1
    assert claim_evidence_rows[0].sentence is None
    relation_evidence = claim.metadata_payload.get("relation_evidence")
    assert isinstance(relation_evidence, dict)
    assert relation_evidence.get("span_required") is True
    assert relation_evidence.get("span_status") == "missing"
    assert isinstance(relation_evidence.get("span_failure_reason"), str)

    queued_relation_claims = [
        item for item in queued_items if item[0] == "relation_claim"
    ]
    queued_relations = [item for item in queued_items if item[0] == "relation"]
    assert len(queued_relation_claims) == 1
    assert len(queued_relations) == 0
    assert queued_relation_claims[0][3] == "high"
