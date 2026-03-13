"""Integration tests for the standalone graph API service."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from services.graph_api import database as graph_database
from services.graph_api.app import create_app
from services.graph_api.dependencies import (
    get_graph_connection_service,
    get_hypothesis_generation_service_provider,
    get_kernel_entity_similarity_service,
    get_kernel_relation_suggestion_service,
)
from src.application.agents.services.graph_connection_service import (
    GraphConnectionOutcome,
)
from src.application.services.kernel.kernel_entity_similarity_service import (
    EntityEmbeddingRefreshSummary,
)
from src.application.services.kernel.kernel_relation_claim_service import (
    KernelRelationClaimService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from src.database.seeds.seeder import (
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from src.domain.entities.kernel.embeddings import (
    KernelEntitySimilarityResult,
    KernelEntitySimilarityScoreBreakdown,
    KernelRelationSuggestionConstraintCheck,
    KernelRelationSuggestionResult,
    KernelRelationSuggestionScoreBreakdown,
)
from src.domain.entities.user import UserRole
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.infrastructure.security.jwt_provider import JWTProvider
from src.models.database.base import Base
from src.models.database.kernel.dictionary import (
    DictionaryDomainContextModel,
    TransformRegistryModel,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.provenance import ProvenanceModel
from src.models.database.kernel.space_memberships import (
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
)
from src.models.database.kernel.spaces import GraphSpaceModel, GraphSpaceStatusEnum
from src.models.database.research_space import (
    ResearchSpaceModel,
)
from src.models.database.source_document import (
    DocumentExtractionStatusEnum,
    DocumentFormatEnum,
    EnrichmentStatusEnum,
    SourceDocumentModel,
)
from src.models.database.user import UserModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)
from tests.db_reset import reset_database

pytestmark = pytest.mark.graph


def _auth_headers(
    *,
    user_id: UUID,
    email: str,
    role: UserRole,
    graph_admin: bool = False,
) -> dict[str, str]:
    secret = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    provider = JWTProvider(secret_key=secret)
    token = provider.create_access_token(
        user_id=user_id,
        role=role.value,
        extra_claims={"graph_admin": graph_admin},
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-TEST-USER-ID": str(user_id),
        "X-TEST-USER-EMAIL": email,
        "X-TEST-USER-ROLE": role.value,
        "X-TEST-GRAPH-ADMIN": "true" if graph_admin else "false",
    }


def _build_projection_materializer(
    session,
) -> KernelRelationProjectionMaterializationService:
    return KernelRelationProjectionMaterializationService(
        relation_repo=SqlAlchemyKernelRelationRepository(session),
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
        entity_repo=SqlAlchemyKernelEntityRepository(
            session,
            phi_encryption_service=None,
            enable_phi_encryption=False,
        ),
        dictionary_repo=SqlAlchemyDictionaryRepository(session),
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def _create_claim_backed_projection(
    session,
    *,
    space_id: UUID,
    source_id: UUID,
    target_id: UUID,
    source_document_id: UUID | None = None,
    source_document_ref: str | None = None,
) -> tuple[UUID, UUID]:
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
    materializer = _build_projection_materializer(session)

    claim = claim_repo.create(
        research_space_id=str(space_id),
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id="graph-service-test",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 is associated with developmental delay.",
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    claim_id = str(claim.id)
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="SUBJECT",
        label="MED13",
        entity_id=str(source_id),
        position=0,
        qualifiers={},
    )
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="OBJECT",
        label="Developmental delay",
        entity_id=str(target_id),
        position=1,
        qualifiers={},
    )
    claim_evidence_repo.create(
        claim_id=claim_id,
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id="graph-service-test",
        sentence="MED13 is associated with developmental delay.",
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.88,
        metadata={
            "evidence_summary": "Curated claim-backed support evidence",
            "evidence_tier": "LITERATURE",
        },
    )
    relation = materializer.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=str(space_id),
        projection_origin="CLAIM_RESOLUTION",
    ).relation
    assert relation is not None
    session.commit()
    return UUID(claim_id), UUID(str(relation.id))


def _ensure_test_variable_definition(session) -> None:
    dictionary_repository = SqlAlchemyDictionaryRepository(session)
    if session.get(DictionaryDomainContextModel, "general") is None:
        session.add(
            DictionaryDomainContextModel(
                id="general",
                display_name="General",
                description="Graph service test domain context",
            ),
        )
        session.flush()
    if dictionary_repository.get_variable("VAR_TEST_NOTE") is not None:
        return
    dictionary_repository.create_variable(
        variable_id="VAR_TEST_NOTE",
        canonical_name="test_note",
        display_name="Test Note",
        data_type="STRING",
        domain_context="general",
        sensitivity="INTERNAL",
        constraints={},
        description="Graph service observation test variable",
        created_by="manual:graph-service-test",
        source_ref="test:graph-service",
    )
    session.flush()


def _create_provenance_record(
    session,
    *,
    space_id: UUID,
    source_type: str = "PUBMED",
) -> UUID:
    provenance_id = uuid4()
    session.add(
        ProvenanceModel(
            id=provenance_id,
            research_space_id=space_id,
            source_type=source_type,
            source_ref="pmid:123456",
            extraction_run_id="graph-service-provenance-test",
            mapping_method="manual",
            mapping_confidence=0.94,
            agent_model="gpt-5",
            raw_input={"title": "Graph provenance fixture"},
        ),
    )
    session.commit()
    return provenance_id


def _create_source_document_reference(
    session,
    *,
    owner_id: UUID,
    space_id: UUID,
) -> UUID:
    source_id = uuid4()
    document_id = uuid4()
    if session.get(UserModel, owner_id) is None:
        session.add(
            UserModel(
                id=owner_id,
                email=f"graph-doc-owner-{owner_id.hex[:12]}@example.com",
                username=f"graph-doc-owner-{owner_id.hex[:12]}",
                full_name="Graph Document Owner",
                hashed_password="hashed_password",
                role=UserRole.RESEARCHER,
                status="active",
            ),
        )
    if session.get(ResearchSpaceModel, space_id) is None:
        session.add(
            ResearchSpaceModel(
                id=space_id,
                slug=f"graph-doc-space-{space_id.hex[:12]}",
                name="Graph Document Space",
                description="Platform source-document fixture for graph-service tests",
                owner_id=owner_id,
                status="active",
            ),
        )
        session.flush()
    session.add(
        UserDataSourceModel(
            id=str(source_id),
            owner_id=str(owner_id),
            research_space_id=str(space_id),
            name="PubMed Import",
            description="Graph service source document fixture",
            source_type=SourceTypeEnum.PUBMED,
            template_id=None,
            configuration={},
            status=SourceStatusEnum.ACTIVE,
            ingestion_schedule={},
            quality_metrics={},
            last_ingested_at=None,
            tags=[],
            version="1.0",
        ),
    )
    session.flush()
    session.add(
        SourceDocumentModel(
            id=str(document_id),
            research_space_id=str(space_id),
            source_id=str(source_id),
            ingestion_job_id=None,
            external_record_id="PMID:123456",
            source_type=SourceTypeEnum.PUBMED.value,
            document_format=DocumentFormatEnum.TEXT.value,
            raw_storage_key=None,
            enriched_storage_key=None,
            content_hash=None,
            content_length_chars=1024,
            enrichment_status=EnrichmentStatusEnum.ENRICHED.value,
            enrichment_method=None,
            enrichment_agent_run_id=None,
            extraction_status=DocumentExtractionStatusEnum.EXTRACTED.value,
            extraction_agent_run_id="graph-service-paper-view",
            metadata_payload={"title": "MED13 and cardiomyopathy"},
        ),
    )
    session.commit()
    return document_id


def _create_graph_space_registry_entry(
    session,
    *,
    space_id: UUID,
    owner_id: UUID,
    slug: str,
    name: str,
    description: str,
    settings: dict[str, object] | None = None,
) -> None:
    session.add(
        GraphSpaceModel(
            id=space_id,
            slug=slug,
            name=name,
            description=description,
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings=settings or {},
        ),
    )


def _create_claim(
    session,
    *,
    space_id: UUID,
    source_id: UUID,
    target_id: UUID,
    source_document_id: UUID | None = None,
    source_document_ref: str | None = None,
    claim_status: str = "OPEN",
    polarity: str = "SUPPORT",
    relation_type: str = "ASSOCIATED_WITH",
    claim_text: str = "MED13 is associated with developmental delay.",
    agent_run_id: str = "graph-service-test",
) -> UUID:
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
    claim = claim_repo.create(
        research_space_id=str(space_id),
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id=agent_run_id,
        source_type="GENE",
        relation_type=relation_type,
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status=claim_status,
        polarity=polarity,
        claim_text=claim_text,
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    claim_id = str(claim.id)
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="SUBJECT",
        label="MED13",
        entity_id=str(source_id),
        position=0,
        qualifiers={},
    )
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="OBJECT",
        label="Developmental delay",
        entity_id=str(target_id),
        position=1,
        qualifiers={},
    )
    claim_evidence_repo.create(
        claim_id=claim_id,
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id=agent_run_id,
        sentence=claim_text,
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.88,
        metadata={
            "evidence_summary": "Curated claim-backed support evidence",
            "evidence_tier": "LITERATURE",
        },
    )
    session.commit()
    return UUID(claim_id)


def _create_claim_without_participants(
    session,
    *,
    space_id: UUID,
    source_id: UUID,
    target_id: UUID,
    claim_text: str,
) -> UUID:
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    claim = claim_repo.create(
        research_space_id=str(space_id),
        source_document_id=None,
        agent_run_id="graph-service-backfill-test",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text=claim_text,
        claim_section="results",
        linked_relation_id=None,
        metadata={
            "source_entity_id": str(source_id),
            "target_entity_id": str(target_id),
        },
    )
    session.commit()
    return UUID(str(claim.id))


def _create_hypothesis_claim(
    session,
    *,
    space_id: UUID,
    claim_text: str,
    metadata: dict[str, object] | None = None,
):
    claim_service = KernelRelationClaimService(
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
    )
    claim = claim_service.create_hypothesis_claim(
        research_space_id=str(space_id),
        source_type="HYPOTHESIS",
        relation_type="PROPOSES",
        target_type="HYPOTHESIS",
        source_label="Manual hypothesis",
        target_label=None,
        confidence=0.5,
        validation_state="UNDEFINED",
        validation_reason="test_hypothesis",
        persistability="NON_PERSISTABLE",
        claim_text=claim_text,
        metadata=metadata or {"origin": "manual"},
        claim_status="OPEN",
    )
    session.commit()
    return claim


@dataclass(frozen=True)
class _FakeHypothesisGenerationResult:
    run_id: str
    requested_seed_count: int
    used_seed_count: int
    candidates_seen: int
    created_count: int
    deduped_count: int
    errors: tuple[str, ...]
    hypotheses: tuple[object, ...]


class _StubGraphConnectionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def discover_connections_for_seed(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        source_id: str | None = None,
        source_type: str = "clinvar",
        research_space_settings: dict[str, object] | None = None,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
        fallback_relations: tuple[object, ...] | None = None,
    ) -> GraphConnectionOutcome:
        del research_space_settings
        self.calls.append(
            {
                "research_space_id": research_space_id,
                "seed_entity_id": seed_entity_id,
                "source_id": source_id,
                "source_type": source_type,
                "model_id": model_id,
                "relation_types": relation_types,
                "max_depth": max_depth,
                "shadow_mode": shadow_mode,
                "pipeline_run_id": pipeline_run_id,
                "fallback_relations_count": len(fallback_relations or ()),
            },
        )
        return GraphConnectionOutcome(
            seed_entity_id=seed_entity_id,
            research_space_id=research_space_id,
            status="discovered",
            reason="processed",
            review_required=False,
            shadow_mode=bool(shadow_mode),
            wrote_to_graph=True,
            run_id="graph-connection-run",
            proposed_relations_count=3,
            persisted_relations_count=2,
            rejected_candidates_count=1,
            errors=(),
        )

    async def close(self) -> None:
        return None


class _StubKernelRelationSuggestionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def suggest_relations(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_entity_ids: list[str],
        limit_per_source: int,
        min_score: float,
        allowed_relation_types: list[str] | None = None,
        target_entity_types: list[str] | None = None,
        exclude_existing_relations: bool = True,
    ) -> list[KernelRelationSuggestionResult]:
        self.calls.append(
            {
                "research_space_id": research_space_id,
                "source_entity_ids": source_entity_ids,
                "limit_per_source": limit_per_source,
                "min_score": min_score,
                "allowed_relation_types": allowed_relation_types,
                "target_entity_types": target_entity_types,
                "exclude_existing_relations": exclude_existing_relations,
            },
        )
        source_entity_id = UUID(source_entity_ids[0])
        target_entity_id = uuid4()
        return [
            KernelRelationSuggestionResult(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type="ASSOCIATED_WITH",
                final_score=0.91,
                score_breakdown=KernelRelationSuggestionScoreBreakdown(
                    vector_score=0.87,
                    graph_overlap_score=0.54,
                    relation_prior_score=0.72,
                ),
                constraint_check=KernelRelationSuggestionConstraintCheck(
                    passed=True,
                    source_entity_type="GENE",
                    relation_type="ASSOCIATED_WITH",
                    target_entity_type="PHENOTYPE",
                ),
            ),
        ]


class _StubKernelEntitySimilarityService:
    def __init__(self) -> None:
        self.get_calls: list[dict[str, object]] = []
        self.refresh_calls: list[dict[str, object]] = []

    def get_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> list[KernelEntitySimilarityResult]:
        self.get_calls.append(
            {
                "research_space_id": research_space_id,
                "entity_id": entity_id,
                "limit": limit,
                "min_similarity": min_similarity,
                "target_entity_types": target_entity_types,
            },
        )
        return [
            KernelEntitySimilarityResult(
                entity_id=uuid4(),
                entity_type="GENE",
                display_label="MED13-like gene",
                similarity_score=0.89,
                score_breakdown=KernelEntitySimilarityScoreBreakdown(
                    vector_score=0.93,
                    graph_overlap_score=0.54,
                ),
            ),
        ]

    def refresh_embeddings(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        limit: int = 500,
        model_name: str | None = None,
        embedding_version: int | None = None,
    ) -> EntityEmbeddingRefreshSummary:
        self.refresh_calls.append(
            {
                "research_space_id": research_space_id,
                "entity_ids": entity_ids,
                "limit": limit,
                "model_name": model_name,
                "embedding_version": embedding_version,
            },
        )
        return EntityEmbeddingRefreshSummary(
            requested=len(entity_ids or []),
            processed=len(entity_ids or []),
            refreshed=len(entity_ids or []),
            unchanged=0,
            missing_entities=[],
        )


@pytest.fixture(scope="function")
def graph_client() -> TestClient:
    reset_database(graph_database.engine, Base.metadata)
    with TestClient(create_app()) as client:
        yield client
    reset_database(graph_database.engine, Base.metadata)


def _seed_space_with_projection() -> dict[str, object]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()
    space_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()

    with graph_database.SessionLocal() as session:
        _create_graph_space_registry_entry(
            session,
            space_id=space_id,
            owner_id=user_id,
            slug=f"graph-space-{suffix}",
            name="Graph Space",
            description="Standalone graph service test space",
        )
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        _ensure_test_variable_definition(session)
        session.add_all(
            [
                EntityModel(
                    id=source_id,
                    research_space_id=space_id,
                    entity_type="GENE",
                    display_label="MED13",
                    metadata_payload={},
                ),
                EntityModel(
                    id=target_id,
                    research_space_id=space_id,
                    entity_type="PHENOTYPE",
                    display_label="Developmental delay",
                    metadata_payload={},
                ),
            ],
        )
        _ensure_test_variable_definition(session)
        session.commit()
        _, relation_id = _create_claim_backed_projection(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
        )

    return {
        "headers": _auth_headers(
            user_id=user_id,
            email=f"graph-owner-{suffix}@example.com",
            role=UserRole.RESEARCHER,
        ),
        "owner_id": user_id,
        "space_id": space_id,
        "source_id": source_id,
        "target_id": target_id,
        "relation_id": relation_id,
    }


def _seed_space_with_open_claims(*, claim_count: int = 1) -> dict[str, object]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()
    space_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    claim_ids: list[UUID] = []

    with graph_database.SessionLocal() as session:
        if session.get(DictionaryDomainContextModel, "general") is None:
            session.add(
                DictionaryDomainContextModel(
                    id="general",
                    display_name="General",
                    description="Graph service test domain context",
                ),
            )
            session.flush()
        _create_graph_space_registry_entry(
            session,
            space_id=space_id,
            owner_id=user_id,
            slug=f"graph-claims-{suffix}",
            name="Graph Claims Space",
            description="Standalone graph service claim test space",
        )
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        session.add_all(
            [
                EntityModel(
                    id=source_id,
                    research_space_id=space_id,
                    entity_type="GENE",
                    display_label="MED13",
                    metadata_payload={},
                ),
                EntityModel(
                    id=target_id,
                    research_space_id=space_id,
                    entity_type="PHENOTYPE",
                    display_label="Developmental delay",
                    metadata_payload={},
                ),
            ],
        )
        session.commit()
        claim_ids.extend(
            _create_claim(
                session,
                space_id=space_id,
                source_id=source_id,
                target_id=target_id,
                claim_text=(
                    "MED13 is associated with developmental delay."
                    if index == 0
                    else "Independent evidence also links MED13 to developmental delay."
                ),
                agent_run_id=f"graph-service-claim-{index}",
            )
            for index in range(claim_count)
        )

    return {
        "headers": _auth_headers(
            user_id=user_id,
            email=f"graph-curator-{suffix}@example.com",
            role=UserRole.RESEARCHER,
        ),
        "owner_id": user_id,
        "space_id": space_id,
        "source_id": source_id,
        "target_id": target_id,
        "claim_ids": claim_ids,
    }


def _add_space_member(
    *,
    space_id: UUID,
    role: GraphSpaceMembershipRoleEnum,
) -> dict[str, object]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()

    with graph_database.SessionLocal() as session:
        session.add(
            GraphSpaceMembershipModel(
                id=uuid4(),
                space_id=space_id,
                user_id=user_id,
                role=role,
                is_active=True,
            ),
        )
        session.commit()

    return {
        "user_id": user_id,
        "headers": _auth_headers(
            user_id=user_id,
            email=f"graph-member-{suffix}@example.com",
            role=UserRole.RESEARCHER,
        ),
    }


def _seed_space_with_unresolved_claim() -> dict[str, object]:
    fixture = _seed_space_with_open_claims(claim_count=0)
    with graph_database.SessionLocal() as session:
        claim_id = _create_claim_without_participants(
            session,
            space_id=fixture["space_id"],
            source_id=fixture["source_id"],
            target_id=fixture["target_id"],
            claim_text="Metadata-only claim for participant backfill.",
        )
    fixture["claim_ids"] = [claim_id]
    return fixture


def _create_admin_headers() -> dict[str, str]:
    admin_id = uuid4()
    admin_email = f"graph-admin-{uuid4().hex[:12]}@example.com"
    return _auth_headers(
        user_id=admin_id,
        email=admin_email,
        role=UserRole.VIEWER,
        graph_admin=True,
    )


def test_graph_service_health_endpoint(graph_client: TestClient) -> None:
    response = graph_client.get("/health")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == "0.1.0"


def test_graph_service_admin_space_registry_routes(graph_client: TestClient) -> None:
    admin_headers = _create_admin_headers()
    space_id = uuid4()
    owner_id = uuid4()

    create_response = graph_client.put(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
        json={
            "slug": "graph-registry-space",
            "name": "Graph Registry Space",
            "description": "Service-owned graph space registry entry",
            "owner_id": str(owner_id),
            "status": "active",
            "settings": {"review_threshold": 0.73},
        },
    )
    assert create_response.status_code == 200, create_response.text
    created_payload = create_response.json()
    assert created_payload["id"] == str(space_id)
    assert created_payload["slug"] == "graph-registry-space"
    assert created_payload["owner_id"] == str(owner_id)
    assert created_payload["settings"]["review_threshold"] == 0.73

    get_response = graph_client.get(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["name"] == "Graph Registry Space"

    list_response = graph_client.get(
        "/v1/admin/spaces",
        headers=admin_headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["spaces"][0]["id"] == str(space_id)

    update_response = graph_client.put(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
        json={
            "slug": "graph-registry-space",
            "name": "Graph Registry Space Updated",
            "description": "Updated service-owned graph space registry entry",
            "owner_id": str(owner_id),
            "status": "suspended",
            "settings": {"review_threshold": 0.91},
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated_payload = update_response.json()
    assert updated_payload["name"] == "Graph Registry Space Updated"
    assert updated_payload["status"] == "suspended"
    assert updated_payload["settings"]["review_threshold"] == 0.91


def test_graph_service_admin_routes_require_graph_admin_claim(
    graph_client: TestClient,
) -> None:
    user_id = uuid4()
    user_email = f"platform-admin-only-{uuid4().hex[:12]}@example.com"

    response = graph_client.get(
        "/v1/admin/spaces",
        headers=_auth_headers(
            user_id=user_id,
            email=user_email,
            role=UserRole.ADMIN,
            graph_admin=False,
        ),
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == (
        "Graph service admin access is required for this operation"
    )


def test_graph_service_admin_space_membership_routes(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    admin_headers = _create_admin_headers()
    member_id = uuid4()

    create_response = graph_client.put(
        f"/v1/admin/spaces/{fixture['space_id']}/memberships/{member_id}",
        headers=admin_headers,
        json={
            "role": "curator",
            "is_active": True,
        },
    )
    assert create_response.status_code == 200, create_response.text
    created_payload = create_response.json()
    assert created_payload["space_id"] == str(fixture["space_id"])
    assert created_payload["user_id"] == str(member_id)
    assert created_payload["role"] == "curator"
    assert created_payload["is_active"] is True

    list_response = graph_client.get(
        f"/v1/admin/spaces/{fixture['space_id']}/memberships",
        headers=admin_headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["memberships"][0]["user_id"] == str(member_id)

    update_response = graph_client.put(
        f"/v1/admin/spaces/{fixture['space_id']}/memberships/{member_id}",
        headers=admin_headers,
        json={
            "role": "viewer",
            "is_active": False,
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated_payload = update_response.json()
    assert updated_payload["role"] == "viewer"
    assert updated_payload["is_active"] is False


def test_graph_service_admin_space_sync_route(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    fixture = _seed_space_with_projection()
    synced_member_id = uuid4()

    response = graph_client.post(
        f"/v1/admin/spaces/{fixture['space_id']}/sync",
        headers=admin_headers,
        json={
            "slug": "graph-sync-space",
            "name": "Graph Sync Space",
            "description": "Atomic graph sync",
            "owner_id": str(fixture["owner_id"]),
            "status": "active",
            "settings": {"review_threshold": 0.88},
            "memberships": [
                {
                    "user_id": str(synced_member_id),
                    "role": "researcher",
                    "is_active": True,
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["space"]["id"] == str(fixture["space_id"])
    assert payload["space"]["slug"] == "graph-sync-space"
    assert payload["space"]["settings"]["review_threshold"] == 0.88
    assert payload["space"]["sync_source"] == "platform_control_plane"
    assert payload["space"]["sync_fingerprint"] is not None
    assert payload["space"]["last_synced_at"] is not None
    assert payload["total_memberships"] == 1
    assert payload["applied"] is True
    assert payload["memberships"][0]["user_id"] == str(synced_member_id)
    assert payload["memberships"][0]["role"] == "researcher"


def test_graph_service_admin_space_sync_route_is_idempotent_for_same_fingerprint(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    fixture = _seed_space_with_projection()
    payload = {
        "slug": "graph-sync-space",
        "name": "Graph Sync Space",
        "description": "Atomic graph sync",
        "owner_id": str(fixture["owner_id"]),
        "status": "active",
        "settings": {"review_threshold": 0.88},
        "sync_fingerprint": "same-sync-fingerprint",
        "memberships": [],
    }

    first_response = graph_client.post(
        f"/v1/admin/spaces/{fixture['space_id']}/sync",
        headers=admin_headers,
        json=payload,
    )
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["applied"] is True

    second_response = graph_client.post(
        f"/v1/admin/spaces/{fixture['space_id']}/sync",
        headers=admin_headers,
        json=payload,
    )
    assert second_response.status_code == 200, second_response.text
    second_payload = second_response.json()
    assert second_payload["applied"] is False
    assert second_payload["space"]["sync_fingerprint"] == "same-sync-fingerprint"


def test_graph_service_relation_reads(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    relation_id = fixture["relation_id"]

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=headers,
    )
    assert relations_response.status_code == 200, relations_response.text
    relations_payload = relations_response.json()
    assert relations_payload["total"] == 1
    assert relations_payload["relations"][0]["id"] == str(relation_id)

    subgraph_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/subgraph",
        headers=headers,
        json={
            "mode": "seeded",
            "seed_entity_ids": [str(source_id)],
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
        },
    )
    assert subgraph_response.status_code == 200, subgraph_response.text
    subgraph_payload = subgraph_response.json()
    assert len(subgraph_payload["nodes"]) == 2
    assert len(subgraph_payload["edges"]) == 1

    neighborhood_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/neighborhood/{source_id}",
        headers=headers,
        params={"depth": 1},
    )
    assert neighborhood_response.status_code == 200, neighborhood_response.text
    neighborhood_payload = neighborhood_response.json()
    assert len(neighborhood_payload["nodes"]) == 2
    assert len(neighborhood_payload["edges"]) == 1

    export_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/export",
        headers=headers,
    )
    assert export_response.status_code == 200, export_response.text
    export_payload = export_response.json()
    assert len(export_payload["nodes"]) == 2
    assert len(export_payload["edges"]) == 1

    document_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/document",
        headers=headers,
        json={
            "mode": "seeded",
            "seed_entity_ids": [str(source_id)],
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 10,
            "evidence_limit_per_claim": 2,
        },
    )
    assert document_response.status_code == 200, document_response.text
    document_payload = document_response.json()
    assert document_payload["meta"]["counts"]["entity_nodes"] == 2
    assert document_payload["meta"]["counts"]["claim_nodes"] >= 1
    assert document_payload["meta"]["counts"]["evidence_nodes"] >= 1
    assert any(node["kind"] == "CLAIM" for node in document_payload["nodes"])
    assert any(node["kind"] == "EVIDENCE" for node in document_payload["nodes"])
    assert any(
        edge["kind"] == "CANONICAL_RELATION" for edge in document_payload["edges"]
    )


def test_graph_service_relation_reads_support_external_document_refs(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    external_document_ref = "https://example.org/papers/med13-cardiomyopathy"

    with graph_database.SessionLocal() as session:
        _create_claim_backed_projection(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
            source_document_ref=external_document_ref,
        )

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=headers,
    )
    assert relations_response.status_code == 200, relations_response.text
    relations_payload = relations_response.json()
    assert relations_payload["total"] >= 1
    assert any(
        any(
            link["url"] == external_document_ref and link["source"] == "external_ref"
            for link in relation["paper_links"]
        )
        for relation in relations_payload["relations"]
    )

    document_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/document",
        headers=headers,
        json={
            "mode": "seeded",
            "seed_entity_ids": [str(source_id)],
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 10,
            "evidence_limit_per_claim": 5,
        },
    )
    assert document_response.status_code == 200, document_response.text
    document_payload = document_response.json()
    evidence_nodes = [
        node for node in document_payload["nodes"] if node["kind"] == "EVIDENCE"
    ]
    assert any(
        node["metadata"].get("source_document_ref") == external_document_ref
        for node in evidence_nodes
    )


def test_graph_service_creates_and_curates_manual_relations(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    admin_headers = _create_admin_headers()
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": str(source_id),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(target_id),
            "confidence": 0.77,
            "evidence_summary": "Manual curator relation",
            "evidence_sentence": "MED13 is associated with developmental delay.",
            "evidence_sentence_source": "verbatim_span",
            "evidence_sentence_confidence": "high",
            "evidence_tier": "COMPUTATIONAL",
        },
    )
    assert create_response.status_code == 201, create_response.text
    relation_payload = create_response.json()
    relation_id = relation_payload["id"]
    assert relation_payload["relation_type"] == "ASSOCIATED_WITH"
    assert relation_payload["source_id"] == str(source_id)
    assert relation_payload["target_id"] == str(target_id)

    update_response = graph_client.put(
        f"/v1/spaces/{space_id}/relations/{relation_id}",
        headers=fixture["headers"],
        json={"curation_status": "APPROVED"},
    )
    assert update_response.status_code == 200, update_response.text
    updated_payload = update_response.json()
    assert updated_payload["id"] == relation_id
    assert updated_payload["curation_status"] == "APPROVED"

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=fixture["headers"],
    )
    assert list_response.status_code == 200, list_response.text
    statuses = {
        relation["id"]: relation["curation_status"]
        for relation in list_response.json()["relations"]
    }
    assert statuses[relation_id] == "APPROVED"


def test_graph_service_lists_and_gets_provenance(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    with graph_database.SessionLocal() as session:
        provenance_id = _create_provenance_record(
            session,
            space_id=space_id,
            source_type="PUBMED",
        )

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/provenance",
        headers=headers,
        params={"source_type": "PUBMED", "offset": 0, "limit": 50},
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["provenance"][0]["id"] == str(provenance_id)
    assert list_payload["provenance"][0]["source_type"] == "PUBMED"

    record_response = graph_client.get(
        f"/v1/spaces/{space_id}/provenance/{provenance_id}",
        headers=headers,
    )
    assert record_response.status_code == 200, record_response.text
    record_payload = record_response.json()
    assert record_payload["id"] == str(provenance_id)
    assert record_payload["source_ref"] == "pmid:123456"
    assert record_payload["raw_input"]["title"] == "Graph provenance fixture"


def test_graph_service_graph_search(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    relation_id = fixture["relation_id"]

    response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/search",
        headers=headers,
        json={
            "question": "MED13",
            "top_k": 5,
            "max_depth": 2,
            "include_evidence_chains": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["executed_path"] == "deterministic"
    assert payload["total_results"] >= 1
    source_results = [
        result for result in payload["results"] if result["entity_id"] == str(source_id)
    ]
    assert source_results
    assert str(relation_id) in source_results[0]["matching_relation_ids"]


def test_graph_service_graph_connection_discovery(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    service = _StubGraphConnectionService()
    graph_client.app.dependency_overrides[get_graph_connection_service] = (
        lambda: service
    )

    try:
        batch_response = graph_client.post(
            f"/v1/spaces/{space_id}/graph/connections/discover",
            headers=headers,
            json={
                "seed_entity_ids": [str(source_id), str(target_id)],
                "source_id": str(uuid4()),
                "source_type": "pubmed",
                "max_depth": 3,
                "shadow_mode": True,
                "pipeline_run_id": "pipeline-run-001",
                "fallback_relations": [
                    {
                        "source_id": str(source_id),
                        "relation_type": "ASSOCIATED_WITH",
                        "target_id": str(target_id),
                        "confidence": 0.55,
                        "evidence_summary": "Fallback relation",
                        "supporting_provenance_ids": [],
                        "supporting_document_count": 0,
                        "reasoning": "Fallback reasoning",
                    },
                ],
            },
        )
        assert batch_response.status_code == 200, batch_response.text
        batch_payload = batch_response.json()
        assert batch_payload["requested"] == 2
        assert batch_payload["persisted_relations_count"] == 4

        single_response = graph_client.post(
            f"/v1/spaces/{space_id}/entities/{source_id}/connections",
            headers=headers,
            json={
                "source_id": str(uuid4()),
                "source_type": "clinvar",
                "max_depth": 2,
                "pipeline_run_id": "pipeline-run-002",
            },
        )
        assert single_response.status_code == 200, single_response.text
        single_payload = single_response.json()
        assert single_payload["seed_entity_id"] == str(source_id)
        assert single_payload["status"] == "discovered"
    finally:
        graph_client.app.dependency_overrides.pop(get_graph_connection_service, None)

    assert len(service.calls) == 3
    assert service.calls[0]["research_space_id"] == str(space_id)
    assert service.calls[0]["source_type"] == "pubmed"
    assert service.calls[0]["pipeline_run_id"] == "pipeline-run-001"
    assert service.calls[0]["fallback_relations_count"] == 1
    assert service.calls[2]["seed_entity_id"] == str(source_id)


def test_graph_service_relation_suggestions(
    graph_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    service = _StubKernelRelationSuggestionService()
    monkeypatch.setenv("MED13_ENABLE_RELATION_SUGGESTIONS", "1")
    graph_client.app.dependency_overrides[get_kernel_relation_suggestion_service] = (
        lambda: service
    )

    try:
        response = graph_client.post(
            f"/v1/spaces/{space_id}/graph/relation-suggestions",
            headers=headers,
            json={
                "source_entity_ids": [str(source_id)],
                "limit_per_source": 5,
                "min_score": 0.7,
                "allowed_relation_types": ["ASSOCIATED_WITH"],
                "target_entity_types": ["PHENOTYPE"],
                "exclude_existing_relations": True,
            },
        )
    finally:
        graph_client.app.dependency_overrides.pop(
            get_kernel_relation_suggestion_service,
            None,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit_per_source"] == 5
    assert payload["suggestions"][0]["source_entity_id"] == str(source_id)
    assert payload["suggestions"][0]["relation_type"] == "ASSOCIATED_WITH"
    assert payload["suggestions"][0]["constraint_check"]["target_entity_type"] == (
        "PHENOTYPE"
    )
    assert service.calls == [
        {
            "research_space_id": str(space_id),
            "source_entity_ids": [str(source_id)],
            "limit_per_source": 5,
            "min_score": 0.7,
            "allowed_relation_types": ["ASSOCIATED_WITH"],
            "target_entity_types": ["PHENOTYPE"],
            "exclude_existing_relations": True,
        },
    ]


def test_graph_service_entity_and_observation_crud(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        params={"type": "GENE"},
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["entities"][0]["id"] == str(source_id)

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13L",
            "metadata": {"source": "graph-service-test"},
            "identifiers": {"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
        },
    )
    assert create_response.status_code == 201, create_response.text
    created_payload = create_response.json()
    created_entity_id = created_payload["entity"]["id"]
    assert created_payload["created"] is True

    get_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["display_label"] == "MED13L"

    update_response = graph_client.put(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
        json={
            "display_label": "MED13 Like",
            "metadata": {"source": "updated"},
            "identifiers": {"ensembl": "ENSG00000123066"},
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["display_label"] == "MED13 Like"
    assert update_response.json()["metadata"]["source"] == "updated"

    observation_create = graph_client.post(
        f"/v1/spaces/{space_id}/observations",
        headers=headers,
        json={
            "subject_id": str(source_id),
            "variable_id": "VAR_TEST_NOTE",
            "value": "hello graph service",
            "unit": None,
            "observed_at": None,
            "provenance_id": None,
            "confidence": 1.0,
        },
    )
    assert observation_create.status_code == 201, observation_create.text
    observation_payload = observation_create.json()
    observation_id = observation_payload["id"]
    assert observation_payload["value_text"] == "hello graph service"

    observation_list = graph_client.get(
        f"/v1/spaces/{space_id}/observations",
        headers=headers,
        params={"subject_id": str(source_id)},
    )
    assert observation_list.status_code == 200, observation_list.text
    assert observation_list.json()["total"] == 1

    observation_get = graph_client.get(
        f"/v1/spaces/{space_id}/observations/{observation_id}",
        headers=headers,
    )
    assert observation_get.status_code == 200, observation_get.text
    assert observation_get.json()["id"] == observation_id

    delete_response = graph_client.delete(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text

    missing_get = graph_client.get(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
    )
    assert missing_get.status_code == 404, missing_get.text


def test_graph_service_entity_similarity_and_refresh(
    graph_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    service = _StubKernelEntitySimilarityService()
    monkeypatch.setenv("MED13_ENABLE_ENTITY_EMBEDDINGS", "1")
    graph_client.app.dependency_overrides[get_kernel_entity_similarity_service] = (
        lambda: service
    )

    try:
        refresh_response = graph_client.post(
            f"/v1/spaces/{space_id}/entities/embeddings/refresh",
            headers=headers,
            json={
                "entity_ids": [str(source_id)],
                "limit": 25,
                "model_name": "test-embedding-model",
                "embedding_version": 2,
            },
        )
        similar_response = graph_client.get(
            f"/v1/spaces/{space_id}/entities/{source_id}/similar",
            headers=headers,
            params={
                "limit": 5,
                "min_similarity": 0.72,
                "target_entity_types": "GENE",
            },
        )
    finally:
        graph_client.app.dependency_overrides.pop(
            get_kernel_entity_similarity_service,
            None,
        )

    assert refresh_response.status_code == 200, refresh_response.text
    refresh_payload = refresh_response.json()
    assert refresh_payload["requested"] == 1
    assert refresh_payload["refreshed"] == 1

    assert similar_response.status_code == 200, similar_response.text
    similar_payload = similar_response.json()
    assert similar_payload["total"] == 1
    assert similar_payload["results"][0]["entity_type"] == "GENE"

    assert service.refresh_calls == [
        {
            "research_space_id": str(space_id),
            "entity_ids": [str(source_id)],
            "limit": 25,
            "model_name": "test-embedding-model",
            "embedding_version": 2,
        },
    ]
    assert service.get_calls == [
        {
            "research_space_id": str(space_id),
            "entity_id": str(source_id),
            "limit": 5,
            "min_similarity": 0.72,
            "target_entity_types": ["GENE"],
        },
    ]


def test_graph_service_reasoning_paths_empty_list(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()

    response = graph_client.get(
        f"/v1/spaces/{fixture['space_id']}/reasoning-paths",
        headers=fixture["headers"],
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 0
    assert payload["paths"] == []


def test_graph_service_claim_reads_and_triage_materialization(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims()
    space_id = fixture["space_id"]
    claim_id = fixture["claim_ids"][0]
    source_id = fixture["source_id"]
    headers = fixture["headers"]

    claims_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=headers,
        params={"claim_status": "OPEN"},
    )
    assert claims_response.status_code == 200, claims_response.text
    claims_payload = claims_response.json()
    assert claims_payload["total"] == 1
    assert claims_payload["claims"][0]["id"] == str(claim_id)

    by_entity_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/by-entity/{source_id}",
        headers=headers,
    )
    assert by_entity_response.status_code == 200, by_entity_response.text
    assert by_entity_response.json()["total"] == 1

    participants_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/participants",
        headers=headers,
    )
    assert participants_response.status_code == 200, participants_response.text
    participants_payload = participants_response.json()
    assert participants_payload["total"] == 2

    evidence_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/evidence",
        headers=headers,
    )
    assert evidence_response.status_code == 200, evidence_response.text
    evidence_payload = evidence_response.json()
    assert evidence_payload["total"] == 1
    assert evidence_payload["evidence"][0]["sentence_source"] == "verbatim_span"

    triage_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id}",
        headers=headers,
        json={"claim_status": "RESOLVED"},
    )
    assert triage_response.status_code == 200, triage_response.text
    triage_payload = triage_response.json()
    assert triage_payload["claim_status"] == "RESOLVED"
    assert triage_payload["linked_relation_id"] is not None

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=headers,
    )
    assert relations_response.status_code == 200, relations_response.text
    assert relations_response.json()["total"] == 1

    conflicts_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations/conflicts",
        headers=headers,
    )
    assert conflicts_response.status_code == 200, conflicts_response.text
    assert conflicts_response.json()["total"] == 0


def test_graph_service_claim_evidence_exposes_external_document_refs(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims()
    space_id = fixture["space_id"]
    headers = fixture["headers"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    external_document_ref = "https://example.org/papers/claim-evidence"

    with graph_database.SessionLocal() as session:
        claim_id = _create_claim(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
            source_document_ref=external_document_ref,
            claim_status="OPEN",
            agent_run_id="graph-service-external-ref",
        )

    evidence_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/evidence",
        headers=headers,
    )
    assert evidence_response.status_code == 200, evidence_response.text
    evidence_payload = evidence_response.json()
    assert evidence_payload["total"] == 1
    evidence_row = evidence_payload["evidence"][0]
    assert evidence_row["source_document_id"] is None
    assert evidence_row["source_document_ref"] == external_document_ref
    assert evidence_row["paper_links"][0]["url"] == external_document_ref
    assert evidence_row["paper_links"][0]["source"] == "external_ref"


def test_graph_service_claim_relation_write_and_review(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=2)
    space_id = fixture["space_id"]
    claim_id_a = fixture["claim_ids"][0]
    claim_id_b = fixture["claim_ids"][1]
    headers = fixture["headers"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": str(claim_id_a),
            "target_claim_id": str(claim_id_b),
            "relation_type": "SUPPORTS",
            "confidence": 0.74,
            "review_status": "PROPOSED",
            "evidence_summary": "Second claim supports the first one.",
            "metadata": {},
        },
    )
    assert create_response.status_code == 200, create_response.text
    relation_payload = create_response.json()
    relation_id = relation_payload["id"]
    assert relation_payload["relation_type"] == "SUPPORTS"
    assert relation_payload["review_status"] == "PROPOSED"

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["claim_relations"][0]["id"] == relation_id

    update_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claim-relations/{relation_id}",
        headers=headers,
        json={"review_status": "ACCEPTED"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["review_status"] == "ACCEPTED"


def test_graph_service_graph_views_and_mechanism_chain(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=2)
    space_id = fixture["space_id"]
    claim_id_a = fixture["claim_ids"][0]
    claim_id_b = fixture["claim_ids"][1]
    headers = fixture["headers"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": str(claim_id_a),
            "target_claim_id": str(claim_id_b),
            "relation_type": "CAUSES",
            "confidence": 0.81,
            "review_status": "ACCEPTED",
            "evidence_summary": "Mechanistic chain test edge.",
            "metadata": {},
        },
    )
    assert create_response.status_code == 200, create_response.text

    view_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/views/claim/{claim_id_a}",
        headers=headers,
    )
    assert view_response.status_code == 200, view_response.text
    view_payload = view_response.json()
    assert view_payload["view_type"] == "claim"
    assert view_payload["claim"]["id"] == str(claim_id_a)
    assert view_payload["counts"]["claims"] >= 1

    chain_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id_a}/mechanism-chain",
        headers=headers,
        params={"max_depth": 3},
    )
    assert chain_response.status_code == 200, chain_response.text
    chain_payload = chain_response.json()
    assert chain_payload["root_claim"]["id"] == str(claim_id_a)
    assert chain_payload["counts"]["claim_relations"] == 1
    assert chain_payload["counts"]["claims"] >= 2


def test_graph_service_paper_graph_view_uses_document_reference_port(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    owner_id = fixture["owner_id"]
    headers = fixture["headers"]

    with graph_database.SessionLocal() as session:
        source_document_id = _create_source_document_reference(
            session,
            owner_id=owner_id,
            space_id=space_id,
        )
        claim_id, relation_id = _create_claim_backed_projection(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
            source_document_id=source_document_id,
        )

    view_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/views/paper/{source_document_id}",
        headers=headers,
        params={"claim_limit": 25},
    )
    assert view_response.status_code == 200, view_response.text
    payload = view_response.json()
    assert payload["view_type"] == "paper"
    assert payload["paper"]["id"] == str(source_document_id)
    assert payload["paper"]["source_type"] == "pubmed"
    assert payload["counts"]["claims"] >= 1
    assert any(claim["id"] == str(claim_id) for claim in payload["claims"])
    assert any(
        relation["id"] == str(relation_id)
        for relation in payload["canonical_relations"]
    )


def test_graph_service_participant_backfill_and_coverage(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_unresolved_claim()
    space_id = fixture["space_id"]
    claim_id = fixture["claim_ids"][0]
    headers = fixture["headers"]

    coverage_before = graph_client.get(
        f"/v1/spaces/{space_id}/claim-participants/coverage",
        headers=headers,
    )
    assert coverage_before.status_code == 200, coverage_before.text
    before_payload = coverage_before.json()
    assert before_payload["total_claims"] == 1
    assert before_payload["claims_with_any_participants"] == 0

    backfill_response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-participants/backfill",
        headers=headers,
        json={"dry_run": False, "limit": 50, "offset": 0},
    )
    assert backfill_response.status_code == 200, backfill_response.text
    backfill_payload = backfill_response.json()
    assert UUID(backfill_payload["operation_run_id"])
    assert backfill_payload["created_participants"] == 2

    operation_history = graph_client.get(
        "/v1/admin/operations/runs",
        headers=_create_admin_headers(),
        params={"operation_type": "claim_participant_backfill"},
    )
    assert operation_history.status_code == 200, operation_history.text
    history_payload = operation_history.json()
    assert history_payload["total"] >= 1
    assert any(
        run["id"] == backfill_payload["operation_run_id"]
        and run["status"] == "succeeded"
        for run in history_payload["runs"]
    )

    coverage_after = graph_client.get(
        f"/v1/spaces/{space_id}/claim-participants/coverage",
        headers=headers,
    )
    assert coverage_after.status_code == 200, coverage_after.text
    after_payload = coverage_after.json()
    assert after_payload["claims_with_any_participants"] == 1
    assert after_payload["claims_with_subject"] == 1
    assert after_payload["claims_with_object"] == 1

    participants_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/participants",
        headers=headers,
    )
    assert participants_response.status_code == 200, participants_response.text
    assert participants_response.json()["total"] == 2


def test_graph_service_admin_readiness_and_rebuild_operations(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=2)
    admin_headers = _create_admin_headers()
    space_id = fixture["space_id"]
    claim_id_a = fixture["claim_ids"][0]
    claim_id_b = fixture["claim_ids"][1]

    resolve_a = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id_a}",
        headers=fixture["headers"],
        json={"claim_status": "RESOLVED"},
    )
    assert resolve_a.status_code == 200, resolve_a.text
    resolve_b = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id_b}",
        headers=fixture["headers"],
        json={"claim_status": "RESOLVED"},
    )
    assert resolve_b.status_code == 200, resolve_b.text

    create_relation = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=fixture["headers"],
        json={
            "source_claim_id": str(claim_id_a),
            "target_claim_id": str(claim_id_b),
            "relation_type": "SUPPORTS",
            "confidence": 0.79,
            "review_status": "ACCEPTED",
            "evidence_summary": "Accepted chain for rebuild.",
            "metadata": {},
        },
    )
    assert create_relation.status_code == 200, create_relation.text

    readiness_response = graph_client.get(
        "/v1/admin/projections/readiness",
        headers=admin_headers,
    )
    assert readiness_response.status_code == 200, readiness_response.text
    readiness_payload = readiness_response.json()
    assert readiness_payload["ready"] is True

    repair_response = graph_client.post(
        "/v1/admin/projections/repair",
        headers=admin_headers,
        json={"dry_run": True, "batch_limit": 100},
    )
    assert repair_response.status_code == 200, repair_response.text
    repair_payload = repair_response.json()
    assert UUID(repair_payload["operation_run_id"])

    rebuild_response = graph_client.post(
        "/v1/admin/reasoning-paths/rebuild",
        headers=admin_headers,
        json={
            "space_id": str(space_id),
            "max_depth": 4,
            "replace_existing": True,
        },
    )
    assert rebuild_response.status_code == 200, rebuild_response.text
    rebuild_payload = rebuild_response.json()
    assert UUID(rebuild_payload["operation_run_id"])
    assert len(rebuild_payload["summaries"]) == 1
    assert rebuild_payload["summaries"][0]["rebuilt_paths"] >= 1

    operations_response = graph_client.get(
        "/v1/admin/operations/runs",
        headers=admin_headers,
        params={"limit": 10, "offset": 0},
    )
    assert operations_response.status_code == 200, operations_response.text
    operations_payload = operations_response.json()
    operation_ids = {run["id"] for run in operations_payload["runs"]}
    assert rebuild_payload["operation_run_id"] in operation_ids
    assert repair_payload["operation_run_id"] in operation_ids
    readiness_run = next(
        run
        for run in operations_payload["runs"]
        if run["operation_type"] == "projection_readiness_audit"
    )
    operation_detail = graph_client.get(
        f"/v1/admin/operations/runs/{readiness_run['id']}",
        headers=admin_headers,
    )
    assert operation_detail.status_code == 200, operation_detail.text
    assert operation_detail.json()["status"] == "succeeded"

    paths_response = graph_client.get(
        f"/v1/spaces/{space_id}/reasoning-paths",
        headers=fixture["headers"],
    )
    assert paths_response.status_code == 200, paths_response.text
    assert paths_response.json()["total"] >= 1


def test_graph_service_hypothesis_list_and_manual_create(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=0)
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    headers = fixture["headers"]

    empty_response = graph_client.get(
        f"/v1/spaces/{space_id}/hypotheses",
        headers=headers,
    )
    assert empty_response.status_code == 200, empty_response.text
    assert empty_response.json()["total"] == 0

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "MED13 may modulate developmental pathways.",
            "rationale": "Observed from converging literature signals.",
            "seed_entity_ids": [str(source_id)],
            "source_type": "manual",
        },
    )
    assert create_response.status_code == 200, create_response.text
    created_payload = create_response.json()
    assert created_payload["polarity"] == "HYPOTHESIS"
    assert created_payload["origin"] == "manual"
    assert created_payload["seed_entity_ids"] == [str(source_id)]

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/hypotheses",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["hypotheses"][0]["claim_id"] == created_payload["claim_id"]


def test_graph_service_generate_hypotheses_with_override(
    graph_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=0)
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    headers = fixture["headers"]

    with graph_database.SessionLocal() as session:
        generated_claim = _create_hypothesis_claim(
            session,
            space_id=space_id,
            claim_text="Graph-generated MED13 hypothesis.",
            metadata={
                "origin": "graph_agent",
                "seed_entity_ids": [str(source_id)],
                "supporting_claim_ids": [],
            },
        )

    class _FakeHypothesisGenerationService:
        async def generate_hypotheses(
            self,
            **_: object,
        ) -> _FakeHypothesisGenerationResult:
            return _FakeHypothesisGenerationResult(
                run_id="graph-service-test-run",
                requested_seed_count=1,
                used_seed_count=1,
                candidates_seen=3,
                created_count=1,
                deduped_count=0,
                errors=(),
                hypotheses=(generated_claim,),
            )

    graph_client.app.dependency_overrides[
        get_hypothesis_generation_service_provider
    ] = lambda: (lambda: _FakeHypothesisGenerationService())
    monkeypatch.setenv("MED13_ENABLE_HYPOTHESIS_GENERATION", "1")

    try:
        response = graph_client.post(
            f"/v1/spaces/{space_id}/hypotheses/generate",
            headers=headers,
            json={
                "seed_entity_ids": [str(source_id)],
                "source_type": "pubmed",
                "max_depth": 2,
                "max_hypotheses": 5,
            },
        )
    finally:
        graph_client.app.dependency_overrides.pop(
            get_hypothesis_generation_service_provider,
            None,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == "graph-service-test-run"
    assert payload["created_count"] == 1
    assert payload["hypotheses"][0]["origin"] == "graph_agent"
    assert payload["hypotheses"][0]["seed_entity_ids"] == [str(source_id)]


def test_graph_service_enforces_space_membership(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    outsider_id = uuid4()
    outsider_email = f"outsider-{uuid4().hex[:12]}@example.com"

    response = graph_client.get(
        f"/v1/spaces/{fixture['space_id']}/relations",
        headers=_auth_headers(
            user_id=outsider_id,
            email=outsider_email,
            role=UserRole.RESEARCHER,
        ),
    )
    assert response.status_code == 403, response.text


def test_graph_service_enforces_member_role_hierarchy(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    viewer_member = _add_space_member(
        space_id=fixture["space_id"],
        role=GraphSpaceMembershipRoleEnum.VIEWER,
    )

    read_response = graph_client.get(
        f"/v1/spaces/{fixture['space_id']}/relations",
        headers=viewer_member["headers"],
    )
    assert read_response.status_code == 200, read_response.text

    write_response = graph_client.post(
        f"/v1/spaces/{fixture['space_id']}/entities",
        headers=viewer_member["headers"],
        json={
            "entity_type": "GENE",
            "display_label": "VIEWER SHOULD FAIL",
            "metadata": {"source": "graph-service-test"},
            "identifiers": {"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
        },
    )
    assert write_response.status_code == 403, write_response.text


def test_graph_service_dictionary_governance_routes(
    graph_client: TestClient,
) -> None:
    _seed_space_with_open_claims(claim_count=0)
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:8].upper()
    source_entity_type_id = f"GS_SRC_{suffix}"
    target_entity_type_id = f"GS_TGT_{suffix}"
    relation_type_id = f"GS_REL_{suffix}"
    variable_id = f"gs_var_{suffix.lower()}"

    source_entity_response = graph_client.post(
        "/v1/dictionary/entity-types",
        headers=admin_headers,
        json={
            "id": source_entity_type_id,
            "display_name": f"Source Entity {suffix}",
            "description": "Source entity type for graph governance service tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    )
    assert source_entity_response.status_code == 201, source_entity_response.text
    assert source_entity_response.json()["id"] == source_entity_type_id

    target_entity_response = graph_client.post(
        "/v1/dictionary/entity-types",
        headers=admin_headers,
        json={
            "id": target_entity_type_id,
            "display_name": f"Target Entity {suffix}",
            "description": "Target entity type for graph governance service tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    )
    assert target_entity_response.status_code == 201, target_entity_response.text

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Relates To {suffix}",
            "description": "Relation type for graph governance service tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    synonym_response = graph_client.post(
        "/v1/dictionary/relation-synonyms",
        headers=admin_headers,
        json={
            "relation_type_id": relation_type_id,
            "synonym": f"links_{suffix.lower()}",
            "source": "manual",
            "source_ref": "graph-service-test",
        },
    )
    assert synonym_response.status_code == 201, synonym_response.text
    synonym_id = synonym_response.json()["id"]

    resolved_synonym_response = graph_client.get(
        "/v1/dictionary/relation-synonyms/resolve",
        headers=admin_headers,
        params={"synonym": f"links_{suffix.lower()}"},
    )
    assert resolved_synonym_response.status_code == 200, resolved_synonym_response.text
    assert resolved_synonym_response.json()["id"] == relation_type_id

    relation_constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        json={
            "source_type": source_entity_type_id,
            "relation_type": relation_type_id,
            "target_type": target_entity_type_id,
            "is_allowed": True,
            "requires_evidence": True,
            "source_ref": "graph-service-test",
        },
    )
    assert (
        relation_constraint_response.status_code == 201
    ), relation_constraint_response.text
    assert relation_constraint_response.json()["relation_type"] == relation_type_id

    variable_response = graph_client.post(
        "/v1/dictionary/variables",
        headers=admin_headers,
        json={
            "id": variable_id,
            "canonical_name": f"graph_variable_{suffix.lower()}",
            "display_name": f"Graph Variable {suffix}",
            "data_type": "CODED",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "preferred_unit": None,
            "constraints": {},
            "description": "Variable for graph governance service tests.",
            "source_ref": "graph-service-test",
        },
    )
    assert variable_response.status_code == 201, variable_response.text
    assert variable_response.json()["id"] == variable_id

    review_status_response = graph_client.patch(
        f"/v1/dictionary/variables/{variable_id}/review-status",
        headers=admin_headers,
        json={"review_status": "PENDING_REVIEW"},
    )
    assert review_status_response.status_code == 200, review_status_response.text
    assert review_status_response.json()["review_status"] == "PENDING_REVIEW"

    revoke_variable_id = f"gs_var_revoke_{suffix.lower()}"
    revoke_variable_response = graph_client.post(
        "/v1/dictionary/variables",
        headers=admin_headers,
        json={
            "id": revoke_variable_id,
            "canonical_name": f"graph_variable_revoke_{suffix.lower()}",
            "display_name": f"Graph Variable Revoke {suffix}",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Variable revoke target for graph governance tests.",
            "source_ref": "graph-service-test",
        },
    )
    assert revoke_variable_response.status_code == 201, revoke_variable_response.text

    merge_variable_source_id = f"gs_var_merge_src_{suffix.lower()}"
    merge_variable_target_id = f"gs_var_merge_tgt_{suffix.lower()}"
    for variable_payload in (
        {
            "id": merge_variable_source_id,
            "canonical_name": f"graph_variable_merge_src_{suffix.lower()}",
            "display_name": f"Graph Variable Merge Source {suffix}",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Variable merge source for graph governance tests.",
            "source_ref": "graph-service-test",
        },
        {
            "id": merge_variable_target_id,
            "canonical_name": f"graph_variable_merge_tgt_{suffix.lower()}",
            "display_name": f"Graph Variable Merge Target {suffix}",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Variable merge target for graph governance tests.",
            "source_ref": "graph-service-test",
        },
    ):
        create_response = graph_client.post(
            "/v1/dictionary/variables",
            headers=admin_headers,
            json=variable_payload,
        )
        assert create_response.status_code == 201, create_response.text

    revoke_entity_type_id = f"GS_REVOKE_ENTITY_{suffix}"
    revoke_entity_response = graph_client.post(
        "/v1/dictionary/entity-types",
        headers=admin_headers,
        json={
            "id": revoke_entity_type_id,
            "display_name": f"Revoke Entity {suffix}",
            "description": "Entity type revoke target for graph governance tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    )
    assert revoke_entity_response.status_code == 201, revoke_entity_response.text

    merge_entity_source_id = f"GS_MERGE_ENTITY_SRC_{suffix}"
    merge_entity_target_id = f"GS_MERGE_ENTITY_TGT_{suffix}"
    for entity_payload in (
        {
            "id": merge_entity_source_id,
            "display_name": f"Merge Entity Source {suffix}",
            "description": "Entity type merge source for graph governance tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
        {
            "id": merge_entity_target_id,
            "display_name": f"Merge Entity Target {suffix}",
            "description": "Entity type merge target for graph governance tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    ):
        create_response = graph_client.post(
            "/v1/dictionary/entity-types",
            headers=admin_headers,
            json=entity_payload,
        )
        assert create_response.status_code == 201, create_response.text

    revoke_relation_type_id = f"GS_REVOKE_REL_{suffix}"
    revoke_relation_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": revoke_relation_type_id,
            "display_name": f"Revoke Relation {suffix}",
            "description": "Relation type revoke target for graph governance tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Revoke Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
    )
    assert revoke_relation_response.status_code == 201, revoke_relation_response.text

    merge_relation_source_id = f"GS_MERGE_REL_SRC_{suffix}"
    merge_relation_target_id = f"GS_MERGE_REL_TGT_{suffix}"
    for relation_payload in (
        {
            "id": merge_relation_source_id,
            "display_name": f"Merge Relation Source {suffix}",
            "description": "Relation type merge source for graph governance tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Merge Source Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
        {
            "id": merge_relation_target_id,
            "display_name": f"Merge Relation Target {suffix}",
            "description": "Relation type merge target for graph governance tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Merge Target Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
    ):
        create_response = graph_client.post(
            "/v1/dictionary/relation-types",
            headers=admin_headers,
            json=relation_payload,
        )
        assert create_response.status_code == 201, create_response.text

    value_set_response = graph_client.post(
        "/v1/dictionary/value-sets",
        headers=admin_headers,
        json={
            "id": f"vs_{suffix.lower()}",
            "variable_id": variable_id,
            "name": f"Graph Value Set {suffix}",
            "description": "Value set for graph governance service tests.",
            "external_ref": None,
            "is_extensible": True,
            "source_ref": "graph-service-test",
        },
    )
    assert value_set_response.status_code == 201, value_set_response.text
    value_set_id = value_set_response.json()["id"]

    item_response = graph_client.post(
        f"/v1/dictionary/value-sets/{value_set_id}/items",
        headers=admin_headers,
        json={
            "code": f"code_{suffix.lower()}",
            "display_label": f"Display {suffix}",
            "synonyms": [f"syn_{suffix.lower()}"],
            "external_ref": None,
            "sort_order": 1,
            "is_active": True,
            "source_ref": "graph-service-test",
        },
    )
    assert item_response.status_code == 201, item_response.text
    value_set_item_id = item_response.json()["id"]

    set_item_active_response = graph_client.patch(
        f"/v1/dictionary/value-set-items/{value_set_item_id}/active",
        headers=admin_headers,
        json={"is_active": False, "revocation_reason": "graph-service-test"},
    )
    assert set_item_active_response.status_code == 200, set_item_active_response.text
    assert set_item_active_response.json()["is_active"] is False

    constraints_list_response = graph_client.get(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        params={"relation_type": relation_type_id},
    )
    assert constraints_list_response.status_code == 200, constraints_list_response.text
    assert constraints_list_response.json()["total"] == 1

    search_response = graph_client.get(
        "/v1/dictionary/search",
        headers=admin_headers,
        params=[("terms", source_entity_type_id)],
    )
    assert search_response.status_code == 200, search_response.text
    assert search_response.json()["total"] >= 1

    by_domain_response = graph_client.get(
        "/v1/dictionary/search/by-domain/general",
        headers=admin_headers,
        params={"limit": 25},
    )
    assert by_domain_response.status_code == 200, by_domain_response.text
    assert by_domain_response.json()["total"] >= 1

    policies_response = graph_client.get(
        "/v1/dictionary/resolution-policies",
        headers=admin_headers,
    )
    assert policies_response.status_code == 200, policies_response.text
    assert policies_response.json()["total"] >= 1

    entity_type_lookup = graph_client.get(
        f"/v1/dictionary/entity-types/{source_entity_type_id}",
        headers=admin_headers,
    )
    assert entity_type_lookup.status_code == 200, entity_type_lookup.text

    relation_type_lookup = graph_client.get(
        f"/v1/dictionary/relation-types/{relation_type_id}",
        headers=admin_headers,
    )
    assert relation_type_lookup.status_code == 200, relation_type_lookup.text

    synonyms_list_response = graph_client.get(
        "/v1/dictionary/relation-synonyms",
        headers=admin_headers,
        params={"relation_type_id": relation_type_id},
    )
    assert synonyms_list_response.status_code == 200, synonyms_list_response.text
    assert synonyms_list_response.json()["total"] == 1
    assert synonyms_list_response.json()["relation_synonyms"][0]["id"] == synonym_id

    revoke_synonym_response = graph_client.post(
        f"/v1/dictionary/relation-synonyms/{synonym_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_synonym_response.status_code == 200, revoke_synonym_response.text
    assert revoke_synonym_response.json()["review_status"] == "REVOKED"
    assert revoke_synonym_response.json()["is_active"] is False

    revoke_variable_result = graph_client.post(
        f"/v1/dictionary/variables/{revoke_variable_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_variable_result.status_code == 200, revoke_variable_result.text
    assert revoke_variable_result.json()["review_status"] == "REVOKED"
    assert revoke_variable_result.json()["is_active"] is False

    merge_variable_result = graph_client.post(
        f"/v1/dictionary/variables/{merge_variable_source_id}/merge",
        headers=admin_headers,
        json={
            "target_id": merge_variable_target_id,
            "reason": "graph-service-test",
        },
    )
    assert merge_variable_result.status_code == 200, merge_variable_result.text
    assert merge_variable_result.json()["review_status"] == "REVOKED"
    assert merge_variable_result.json()["superseded_by"] == merge_variable_target_id

    revoke_entity_result = graph_client.post(
        f"/v1/dictionary/entity-types/{revoke_entity_type_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_entity_result.status_code == 200, revoke_entity_result.text
    assert revoke_entity_result.json()["review_status"] == "REVOKED"
    assert revoke_entity_result.json()["is_active"] is False

    merge_entity_result = graph_client.post(
        f"/v1/dictionary/entity-types/{merge_entity_source_id}/merge",
        headers=admin_headers,
        json={
            "target_id": merge_entity_target_id,
            "reason": "graph-service-test",
        },
    )
    assert merge_entity_result.status_code == 200, merge_entity_result.text
    assert merge_entity_result.json()["review_status"] == "REVOKED"
    assert merge_entity_result.json()["superseded_by"] == merge_entity_target_id

    revoke_relation_result = graph_client.post(
        f"/v1/dictionary/relation-types/{revoke_relation_type_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_relation_result.status_code == 200, revoke_relation_result.text
    assert revoke_relation_result.json()["review_status"] == "REVOKED"
    assert revoke_relation_result.json()["is_active"] is False

    merge_relation_result = graph_client.post(
        f"/v1/dictionary/relation-types/{merge_relation_source_id}/merge",
        headers=admin_headers,
        json={
            "target_id": merge_relation_target_id,
            "reason": "graph-service-test",
        },
    )
    assert merge_relation_result.status_code == 200, merge_relation_result.text
    assert merge_relation_result.json()["review_status"] == "REVOKED"
    assert merge_relation_result.json()["superseded_by"] == merge_relation_target_id

    changelog_response = graph_client.get(
        "/v1/dictionary/changelog",
        headers=admin_headers,
        params={"record_id": merge_variable_source_id},
    )
    assert changelog_response.status_code == 200, changelog_response.text
    changelog_actions = {
        str(entry["action"]) for entry in changelog_response.json()["changelog_entries"]
    }
    assert "MERGE" in changelog_actions

    reembed_response = graph_client.post(
        "/v1/dictionary/reembed",
        headers=admin_headers,
        json={
            "limit_per_dimension": 10,
            "source_ref": "graph-service-test:reembed",
        },
    )
    assert reembed_response.status_code == 200, reembed_response.text
    assert reembed_response.json()["updated_records"] >= 3

    with graph_database.SessionLocal() as session:
        session.add(
            TransformRegistryModel(
                id=f"TR_GRAPH_{suffix}",
                input_unit="mg",
                output_unit="g",
                category="UNIT_CONVERSION",
                implementation_ref="func:std_lib.convert.mg_to_g",
                status="ACTIVE",
                is_deterministic=True,
                is_production_allowed=False,
                test_input=2500,
                expected_output=2.5,
                description="Graph-service transform parity test",
                created_by="seed",
            ),
        )
        session.commit()

    transforms_list_response = graph_client.get(
        "/v1/dictionary/transforms",
        headers=admin_headers,
    )
    assert transforms_list_response.status_code == 200, transforms_list_response.text
    listed_transform_ids = {
        item["id"] for item in transforms_list_response.json()["transforms"]
    }
    assert f"TR_GRAPH_{suffix}" in listed_transform_ids

    verify_transform_response = graph_client.post(
        f"/v1/dictionary/transforms/TR_GRAPH_{suffix}/verify",
        headers=admin_headers,
    )
    assert verify_transform_response.status_code == 200, verify_transform_response.text
    assert verify_transform_response.json()["transform_id"] == f"TR_GRAPH_{suffix}"
    assert verify_transform_response.json()["passed"] is True

    promote_transform_response = graph_client.patch(
        f"/v1/dictionary/transforms/TR_GRAPH_{suffix}/promote",
        headers=admin_headers,
    )
    assert (
        promote_transform_response.status_code == 200
    ), promote_transform_response.text
    assert promote_transform_response.json()["id"] == f"TR_GRAPH_{suffix}"
    assert promote_transform_response.json()["is_production_allowed"] is True


def test_graph_service_dictionary_routes_require_admin(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=0)

    response = graph_client.get(
        "/v1/dictionary/entity-types",
        headers=fixture["headers"],
    )
    assert response.status_code == 403, response.text


def test_graph_service_concept_governance_routes(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=0)
    space_id = fixture["space_id"]
    headers = fixture["headers"]

    concept_set_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/sets",
        headers=headers,
        json={
            "name": "Mechanism Concepts",
            "slug": "mechanism-concepts",
            "domain_context": "general",
            "description": "Concept set for graph service tests.",
            "source_ref": "graph-service-test",
        },
    )
    assert concept_set_response.status_code == 201, concept_set_response.text
    concept_set_id = concept_set_response.json()["id"]

    concept_sets_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/sets",
        headers=headers,
    )
    assert concept_sets_response.status_code == 200, concept_sets_response.text
    assert concept_sets_response.json()["total"] == 1

    concept_member_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/members",
        headers=headers,
        json={
            "concept_set_id": concept_set_id,
            "domain_context": "general",
            "canonical_label": "Transcriptional dysregulation",
            "normalized_label": "transcriptional dysregulation",
            "sense_key": "mechanism",
            "dictionary_dimension": None,
            "dictionary_entry_id": None,
            "is_provisional": True,
            "metadata_payload": {"kind": "mechanism"},
            "source_ref": "graph-service-test",
        },
    )
    assert concept_member_response.status_code == 201, concept_member_response.text
    concept_member_id = concept_member_response.json()["id"]

    concept_members_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/members",
        headers=headers,
        params={"concept_set_id": concept_set_id},
    )
    assert concept_members_response.status_code == 200, concept_members_response.text
    assert concept_members_response.json()["total"] == 1

    concept_alias_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/aliases",
        headers=headers,
        json={
            "concept_member_id": concept_member_id,
            "domain_context": "general",
            "alias_label": "tx dysregulation",
            "alias_normalized": "tx dysregulation",
            "source": "manual",
            "source_ref": "graph-service-test",
        },
    )
    assert concept_alias_response.status_code == 201, concept_alias_response.text

    aliases_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/aliases",
        headers=headers,
        params={"concept_member_id": concept_member_id},
    )
    assert aliases_response.status_code == 200, aliases_response.text
    assert aliases_response.json()["total"] == 1

    upsert_policy_response = graph_client.put(
        f"/v1/spaces/{space_id}/concepts/policy",
        headers=headers,
        json={
            "mode": "BALANCED",
            "minimum_edge_confidence": 0.7,
            "minimum_distinct_documents": 2,
            "allow_generic_relations": False,
            "max_edges_per_document": 4,
            "policy_payload": {"strategy": "service-test"},
            "source_ref": "graph-service-test",
        },
    )
    assert upsert_policy_response.status_code == 200, upsert_policy_response.text
    assert upsert_policy_response.json()["mode"] == "BALANCED"

    policy_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/policy",
        headers=headers,
    )
    assert policy_response.status_code == 200, policy_response.text
    assert policy_response.json()["mode"] == "BALANCED"

    decision_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/decisions/propose",
        headers=headers,
        json={
            "decision_type": "MAP",
            "decision_payload": {"action": "map"},
            "evidence_payload": {"source": "manual"},
            "confidence": 0.91,
            "rationale": "This concept should be reviewed and mapped later.",
            "concept_set_id": concept_set_id,
            "concept_member_id": concept_member_id,
            "concept_link_id": None,
        },
    )
    assert decision_response.status_code == 201, decision_response.text
    decision_id = decision_response.json()["id"]

    decision_status_response = graph_client.patch(
        f"/v1/spaces/{space_id}/concepts/decisions/{decision_id}/status",
        headers=headers,
        json={"decision_status": "APPROVED"},
    )
    assert decision_status_response.status_code == 200, decision_status_response.text
    assert decision_status_response.json()["decision_status"] == "APPROVED"

    decisions_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/decisions",
        headers=headers,
        params={"decision_status": "APPROVED"},
    )
    assert decisions_response.status_code == 200, decisions_response.text
    assert decisions_response.json()["total"] == 1
