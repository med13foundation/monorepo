"""Correctness-oriented performance coverage for graph queries and traversal."""

from __future__ import annotations

import time
from contextlib import contextmanager
from statistics import median
from uuid import uuid4

import pytest

from services.graph_api._relation_subgraph_helpers import (
    collect_candidate_relations,
)
from src.application.services.kernel.kernel_claim_evidence_service import (
    KernelClaimEvidenceService,
)
from src.application.services.kernel.kernel_claim_participant_service import (
    KernelClaimParticipantService,
)
from src.application.services.kernel.kernel_claim_relation_service import (
    KernelClaimRelationService,
)
from src.application.services.kernel.kernel_entity_mechanism_paths_projector import (
    KernelEntityMechanismPathsProjector,
)
from src.application.services.kernel.kernel_entity_neighbors_projector import (
    KernelEntityNeighborsProjector,
)
from src.application.services.kernel.kernel_reasoning_path_service import (
    KernelReasoningPathService,
)
from src.application.services.kernel.kernel_relation_claim_service import (
    KernelRelationClaimService,
)
from src.application.services.kernel.kernel_relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from src.application.services.kernel.kernel_relation_service import (
    KernelRelationService,
)
from src.database import session as session_module
from src.database.seeds.seeder import (
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from src.domain.entities.user import UserRole, UserStatus
from src.domain.repositories.kernel.reasoning_path_repository import (
    ReasoningPathStepWrite,
    ReasoningPathWrite,
    ReasoningPathWriteBundle,
)
from src.graph.core.read_model import NullGraphReadModelUpdateDispatcher
from src.graph.core.relation_autopromotion_policy import AutoPromotionPolicy
from src.graph.pack_registry import resolve_graph_domain_pack
from src.infrastructure.repositories.kernel import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelReasoningPathRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelRelationRepository,
)
from src.infrastructure.repositories.kernel.graph_query_repository import (
    SqlAlchemyGraphQueryRepository,
)
from src.infrastructure.repositories.kernel.kernel_claim_relation_repository import (
    SqlAlchemyKernelClaimRelationRepository,
)
from src.models.database.base import Base
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel
from src.type_definitions.graph_api_schemas.kernel_schemas import (
    KernelGraphSubgraphRequest,
)
from tests.db_reset import reset_database

pytestmark = [pytest.mark.graph, pytest.mark.performance]


@contextmanager
def _postgres_session(postgres_required):  # noqa: ARG001
    reset_database(session_module.engine, Base.metadata)
    session = session_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        reset_database(session_module.engine, Base.metadata)


def _seed_user_and_space(session) -> ResearchSpaceModel:
    user = UserModel(
        email=f"graph-perf-{uuid4().hex}@example.com",
        username=f"graph-perf-{uuid4().hex[:12]}",
        full_name="Graph Performance Tester",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    session.add(user)
    session.flush()
    space = ResearchSpaceModel(
        slug=f"graph-perf-{uuid4().hex[:12]}",
        name="Graph Performance Space",
        description="Graph performance test space",
        owner_id=user.id,
        status="active",
    )
    session.add(space)
    session.flush()
    return space


def _build_relation_repository(session) -> SqlAlchemyKernelRelationRepository:
    return SqlAlchemyKernelRelationRepository(
        session,
        auto_promotion_policy=AutoPromotionPolicy(),
    )


def _build_projection_materializer(
    session,
) -> KernelRelationProjectionMaterializationService:
    return KernelRelationProjectionMaterializationService(
        relation_repo=_build_relation_repository(session),
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
        entity_repo=SqlAlchemyKernelEntityRepository(
            session,
            phi_encryption_service=None,
            enable_phi_encryption=False,
        ),
        dictionary_repo=SqlAlchemyDictionaryRepository(
            session,
            builtin_domain_contexts=resolve_graph_domain_pack().dictionary_domain_contexts,
        ),
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
        read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
    )


def _seed_claim_backed_relations(
    session,
    *,
    space_id: str,
    relation_count: int,
) -> tuple[str, list[str]]:
    entity_repo = SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
    evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
    materializer = _build_projection_materializer(session)

    source_entity = entity_repo.create(
        research_space_id=space_id,
        entity_type="GENE",
        display_label="MED13",
        metadata={},
    )
    target_ids: list[str] = []
    for index in range(relation_count):
        target = entity_repo.create(
            research_space_id=space_id,
            entity_type="PHENOTYPE",
            display_label=f"Phenotype {index}",
            metadata={"index": index},
        )
        claim = claim_repo.create(
            research_space_id=space_id,
            source_document_id=None,
            agent_run_id=f"graph-perf-{index}",
            source_type="GENE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label=f"Phenotype {index}",
            confidence=0.8,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text="Performance support claim.",
            claim_section="results",
            linked_relation_id=None,
            metadata={},
        )
        participant_repo.create(
            claim_id=str(claim.id),
            research_space_id=space_id,
            role="SUBJECT",
            label="MED13",
            entity_id=str(source_entity.id),
            position=0,
            qualifiers={},
        )
        participant_repo.create(
            claim_id=str(claim.id),
            research_space_id=space_id,
            role="OBJECT",
            label=f"Phenotype {index}",
            entity_id=str(target.id),
            position=1,
            qualifiers={},
        )
        evidence_repo.create(
            claim_id=str(claim.id),
            source_document_id=None,
            agent_run_id=f"graph-perf-{index}",
            sentence=f"MED13 is associated with phenotype {index}.",
            sentence_source="verbatim_span",
            sentence_confidence="high",
            sentence_rationale=None,
            figure_reference=None,
            table_reference=None,
            confidence=0.8,
            metadata={
                "origin": "performance_test",
                "evidence_summary": f"Performance evidence {index}",
                "evidence_tier": "LITERATURE",
            },
        )
        materialized = materializer.materialize_support_claim(
            claim_id=str(claim.id),
            research_space_id=space_id,
            projection_origin="CLAIM_RESOLUTION",
        )
        assert materialized.relation is not None
        target_ids.append(str(target.id))
    session.commit()
    return str(source_entity.id), target_ids


def _measure_samples(fn, *, samples: int = 7) -> tuple[list[float], object]:
    durations: list[float] = []
    result = None
    for _ in range(samples):
        start = time.perf_counter()
        result = fn()
        durations.append(time.perf_counter() - start)
    return durations, result


def _seed_reasoning_path_fixture(
    session,
    *,
    space_id: str,
) -> tuple[str, str]:
    entity_repo = SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
    evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
    claim_relation_repo = SqlAlchemyKernelClaimRelationRepository(session)
    reasoning_repo = SqlAlchemyKernelReasoningPathRepository(session)

    start = entity_repo.create(
        research_space_id=space_id,
        entity_type="GENE",
        display_label="MED13",
        metadata={},
    )
    middle = entity_repo.create(
        research_space_id=space_id,
        entity_type="PHENOTYPE",
        display_label="Mediator dysfunction",
        metadata={},
    )
    end = entity_repo.create(
        research_space_id=space_id,
        entity_type="PHENOTYPE",
        display_label="Speech delay",
        metadata={},
    )

    claim_a = claim_repo.create(
        research_space_id=space_id,
        source_document_id=None,
        agent_run_id="graph-perf-path-a",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Mediator dysfunction",
        confidence=0.83,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 perturbs mediator function.",
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    claim_b = claim_repo.create(
        research_space_id=space_id,
        source_document_id=None,
        agent_run_id="graph-perf-path-b",
        source_type="PHENOTYPE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="Mediator dysfunction",
        target_label="Speech delay",
        confidence=0.81,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="Mediator dysfunction is associated with speech delay.",
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    for claim_id, entity_id, role, position in (
        (str(claim_a.id), str(start.id), "SUBJECT", 0),
        (str(claim_a.id), str(middle.id), "OBJECT", 1),
        (str(claim_b.id), str(middle.id), "SUBJECT", 0),
        (str(claim_b.id), str(end.id), "OBJECT", 1),
    ):
        participant_repo.create(
            claim_id=claim_id,
            research_space_id=space_id,
            role=role,
            label=None,
            entity_id=entity_id,
            position=position,
            qualifiers={},
        )
    for claim_id, agent_run_id in (
        (str(claim_a.id), "graph-perf-path-a"),
        (str(claim_b.id), "graph-perf-path-b"),
    ):
        evidence_repo.create(
            claim_id=claim_id,
            source_document_id=None,
            agent_run_id=agent_run_id,
            sentence="Performance reasoning evidence.",
            sentence_source="verbatim_span",
            sentence_confidence="high",
            sentence_rationale=None,
            figure_reference=None,
            table_reference=None,
            confidence=0.8,
            metadata={
                "evidence_summary": "Performance evidence",
                "evidence_tier": "LITERATURE",
            },
        )
    claim_relation = claim_relation_repo.create(
        research_space_id=space_id,
        source_claim_id=str(claim_a.id),
        target_claim_id=str(claim_b.id),
        relation_type="CAUSES",
        agent_run_id="graph-perf-path-edge",
        source_document_id=None,
        confidence=0.77,
        review_status="ACCEPTED",
        evidence_summary="Performance chain",
        metadata={},
    )

    path_id = reasoning_repo.replace_for_space(
        research_space_id=space_id,
        bundles=[
            ReasoningPathWriteBundle(
                path=ReasoningPathWrite(
                    research_space_id=space_id,
                    path_kind="MECHANISM",
                    status="ACTIVE",
                    start_entity_id=str(start.id),
                    end_entity_id=str(end.id),
                    root_claim_id=str(claim_a.id),
                    path_length=1,
                    confidence=0.77,
                    path_signature_hash="graph-performance-path-signature",
                    generated_by="graph-performance-test",
                    metadata={
                        "supporting_claim_ids": [str(claim_a.id), str(claim_b.id)],
                    },
                ),
                steps=(
                    ReasoningPathStepWrite(
                        step_index=0,
                        source_claim_id=str(claim_a.id),
                        target_claim_id=str(claim_b.id),
                        claim_relation_id=str(claim_relation.id),
                        canonical_relation_id=None,
                        metadata={},
                    ),
                ),
            ),
        ],
        replace_existing=True,
    )[0].id
    session.commit()
    return str(path_id), str(start.id)


def _seed_reasoning_path_candidates_fixture(
    session,
    *,
    space_id: str,
    path_count: int,
) -> str:
    entity_repo = SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    claim_relation_repo = SqlAlchemyKernelClaimRelationRepository(session)
    reasoning_repo = SqlAlchemyKernelReasoningPathRepository(session)

    seed_entity = entity_repo.create(
        research_space_id=space_id,
        entity_type="GENE",
        display_label="MED13",
        metadata={},
    )
    bundles: list[ReasoningPathWriteBundle] = []
    for index in range(path_count):
        end_entity = entity_repo.create(
            research_space_id=space_id,
            entity_type="PHENOTYPE",
            display_label=f"Mechanism endpoint {index}",
            metadata={"index": index},
        )
        root_claim = claim_repo.create(
            research_space_id=space_id,
            source_document_id=None,
            agent_run_id=f"graph-perf-mechanism-root-{index}",
            source_type="GENE",
            relation_type="CAUSES",
            target_type="PHENOTYPE",
            source_label="MED13",
            target_label=f"Mediator {index}",
            confidence=0.84,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text="Performance mechanism root claim.",
            claim_section="results",
            linked_relation_id=None,
            metadata={},
        )
        final_claim = claim_repo.create(
            research_space_id=space_id,
            source_document_id=None,
            agent_run_id=f"graph-perf-mechanism-final-{index}",
            source_type="PHENOTYPE",
            relation_type="ASSOCIATED_WITH",
            target_type="PHENOTYPE",
            source_label=f"Mediator {index}",
            target_label=f"Mechanism endpoint {index}",
            confidence=0.8,
            validation_state="ALLOWED",
            validation_reason=None,
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text="Performance mechanism terminal claim.",
            claim_section="results",
            linked_relation_id=None,
            metadata={},
        )
        claim_relation = claim_relation_repo.create(
            research_space_id=space_id,
            source_claim_id=str(root_claim.id),
            target_claim_id=str(final_claim.id),
            relation_type="CAUSES",
            agent_run_id=f"graph-perf-mechanism-edge-{index}",
            source_document_id=None,
            confidence=0.75,
            review_status="ACCEPTED",
            evidence_summary="Mechanism benchmark chain",
            metadata={},
        )
        bundles.append(
            ReasoningPathWriteBundle(
                path=ReasoningPathWrite(
                    research_space_id=space_id,
                    path_kind="MECHANISM",
                    status="ACTIVE",
                    start_entity_id=str(seed_entity.id),
                    end_entity_id=str(end_entity.id),
                    root_claim_id=str(root_claim.id),
                    path_length=1,
                    confidence=0.75,
                    path_signature_hash=f"graph-performance-mechanism-{index:04d}".ljust(
                        32,
                        "0",
                    ),
                    generated_by="graph-performance-test",
                    metadata={
                        "terminal_relation_type": "ASSOCIATED_WITH",
                        "supporting_claim_ids": [
                            str(root_claim.id),
                            str(final_claim.id),
                        ],
                    },
                ),
                steps=(
                    ReasoningPathStepWrite(
                        step_index=0,
                        source_claim_id=str(root_claim.id),
                        target_claim_id=str(final_claim.id),
                        claim_relation_id=str(claim_relation.id),
                        canonical_relation_id=None,
                        metadata={},
                    ),
                ),
            ),
        )

    reasoning_repo.replace_for_space(
        research_space_id=space_id,
        bundles=bundles,
        replace_existing=True,
    )
    session.commit()
    return str(seed_entity.id)


def test_graph_neighborhood_query_completes_within_budget(postgres_required) -> None:
    with _postgres_session(postgres_required) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        space = _seed_user_and_space(session)
        source_id, _ = _seed_claim_backed_relations(
            session,
            space_id=str(space.id),
            relation_count=150,
        )
        relation_service = KernelRelationService(
            _build_relation_repository(session),
            SqlAlchemyKernelEntityRepository(
                session,
                phi_encryption_service=None,
                enable_phi_encryption=False,
            ),
        )

        start = time.perf_counter()
        relations = relation_service.get_neighborhood_in_space(
            str(space.id),
            source_id,
            depth=1,
            limit=200,
        )
        duration = time.perf_counter() - start

        assert len(relations) == 150
        assert duration < 2.0


def test_entity_neighbors_read_model_benchmark_improves_neighborhood_latency(
    postgres_required,
) -> None:
    with _postgres_session(postgres_required) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        space = _seed_user_and_space(session)
        source_id, _ = _seed_claim_backed_relations(
            session,
            space_id=str(space.id),
            relation_count=600,
        )
        relation_service = KernelRelationService(
            _build_relation_repository(session),
            SqlAlchemyKernelEntityRepository(
                session,
                phi_encryption_service=None,
                enable_phi_encryption=False,
            ),
        )

        def _query_neighborhood():
            session.expire_all()
            return relation_service.get_neighborhood_in_space(
                str(space.id),
                source_id,
                depth=1,
                limit=700,
            )

        warmup_relations = _query_neighborhood()
        assert len(warmup_relations) == 600

        fallback_samples, fallback_relations = _measure_samples(_query_neighborhood)
        assert len(fallback_relations) == 600

        rebuilt_rows = KernelEntityNeighborsProjector(session).rebuild(
            space_id=str(space.id),
        )
        session.commit()
        assert rebuilt_rows > 0

        indexed_samples, indexed_relations = _measure_samples(_query_neighborhood)
        assert len(indexed_relations) == 600

        fallback_median = median(fallback_samples)
        indexed_median = median(indexed_samples)
        speedup = (
            fallback_median / indexed_median if indexed_median > 0 else float("inf")
        )

        print(  # noqa: T201
            "entity_neighbors_benchmark "
            f"fallback_ms={fallback_median * 1000:.2f} "
            f"indexed_ms={indexed_median * 1000:.2f} "
            f"speedup={speedup:.2f}x",
        )

        assert indexed_median < fallback_median


def test_graph_subgraph_collection_completes_within_budget(postgres_required) -> None:
    with _postgres_session(postgres_required) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        space = _seed_user_and_space(session)
        source_id, _ = _seed_claim_backed_relations(
            session,
            space_id=str(space.id),
            relation_count=120,
        )
        relation_service = KernelRelationService(
            _build_relation_repository(session),
            SqlAlchemyKernelEntityRepository(
                session,
                phi_encryption_service=None,
                enable_phi_encryption=False,
            ),
        )
        request = KernelGraphSubgraphRequest(
            mode="seeded",
            seed_entity_ids=[source_id],
            depth=1,
            top_k=100,
            max_nodes=150,
            max_edges=150,
        )

        start = time.perf_counter()
        relations = collect_candidate_relations(
            mode="seeded",
            space_id=str(space.id),
            request=request,
            relation_service=relation_service,
            relation_types=None,
            curation_statuses=None,
        )
        duration = time.perf_counter() - start

        assert len(relations) == 100
        assert duration < 2.0


def test_relation_evidence_drilldown_completes_within_budget(postgres_required) -> None:
    with _postgres_session(postgres_required) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        space = _seed_user_and_space(session)
        source_id, _ = _seed_claim_backed_relations(
            session,
            space_id=str(space.id),
            relation_count=120,
        )
        graph_query_repository = SqlAlchemyGraphQueryRepository(
            session,
            relation_repository=_build_relation_repository(session),
        )
        relation_id = str(
            _build_relation_repository(session)
            .find_neighborhood(
                source_id,
                depth=1,
                limit=1,
            )[0]
            .id,
        )

        start = time.perf_counter()
        evidence = graph_query_repository.graph_query_relation_evidence(
            research_space_id=str(space.id),
            relation_id=relation_id,
            limit=20,
        )
        duration = time.perf_counter() - start

        print(f"relation_evidence_drilldown_ms={duration * 1000:.2f}")  # noqa: T201

        assert evidence
        assert duration < 1.0


def test_reasoning_path_detail_traversal_completes_within_budget(
    postgres_required,
) -> None:
    with _postgres_session(postgres_required) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        space = _seed_user_and_space(session)
        path_id, _ = _seed_reasoning_path_fixture(session, space_id=str(space.id))
        service = KernelReasoningPathService(
            reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
            relation_claim_service=KernelRelationClaimService(
                SqlAlchemyKernelRelationClaimRepository(session),
                read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
            ),
            claim_participant_service=KernelClaimParticipantService(
                SqlAlchemyKernelClaimParticipantRepository(session),
            ),
            claim_evidence_service=KernelClaimEvidenceService(
                SqlAlchemyKernelClaimEvidenceRepository(session),
            ),
            claim_relation_service=KernelClaimRelationService(
                SqlAlchemyKernelClaimRelationRepository(session),
            ),
            relation_service=KernelRelationService(
                _build_relation_repository(session),
                SqlAlchemyKernelEntityRepository(
                    session,
                    phi_encryption_service=None,
                    enable_phi_encryption=False,
                ),
            ),
            read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
            session=session,
        )

        start = time.perf_counter()
        detail = service.get_path(path_id, str(space.id))
        duration = time.perf_counter() - start

        assert detail is not None
        assert len(detail.steps) == 1
        assert len(detail.claims) == 2
        assert len(detail.evidence) == 2
        assert duration < 1.0


def test_entity_mechanism_paths_benchmark_improves_reasoning_seed_read_latency(
    postgres_required,
) -> None:
    with _postgres_session(postgres_required) as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        space = _seed_user_and_space(session)
        seed_entity_id = _seed_reasoning_path_candidates_fixture(
            session,
            space_id=str(space.id),
            path_count=120,
        )
        entity_repository = SqlAlchemyKernelEntityRepository(
            session,
            phi_encryption_service=None,
            enable_phi_encryption=False,
        )
        service = KernelReasoningPathService(
            reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
            relation_claim_service=KernelRelationClaimService(
                SqlAlchemyKernelRelationClaimRepository(session),
                read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
            ),
            claim_participant_service=KernelClaimParticipantService(
                SqlAlchemyKernelClaimParticipantRepository(session),
            ),
            claim_evidence_service=KernelClaimEvidenceService(
                SqlAlchemyKernelClaimEvidenceRepository(session),
            ),
            claim_relation_service=KernelClaimRelationService(
                SqlAlchemyKernelClaimRelationRepository(session),
            ),
            relation_service=KernelRelationService(
                _build_relation_repository(session),
                entity_repository,
            ),
            read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
            session=session,
        )

        def _legacy_reasoning_seed_read():
            session.expire_all()
            candidates = []
            path_list = service.list_paths(
                research_space_id=str(space.id),
                start_entity_id=seed_entity_id,
                status="ACTIVE",
                path_kind="MECHANISM",
                limit=200,
                offset=0,
            )
            for path in path_list.paths:
                detail = service.get_path(str(path.id), str(space.id))
                if detail is None:
                    continue
                start_entity = entity_repository.get_by_id(str(path.start_entity_id))
                end_entity = entity_repository.get_by_id(str(path.end_entity_id))
                if start_entity is None or end_entity is None:
                    continue
                candidates.append(
                    (
                        str(path.id),
                        str(path.start_entity_id),
                        str(path.end_entity_id),
                    ),
                )
            return candidates

        warmup_candidates = _legacy_reasoning_seed_read()
        assert len(warmup_candidates) == 120

        legacy_samples, legacy_candidates = _measure_samples(
            _legacy_reasoning_seed_read,
        )
        assert len(legacy_candidates) == 120

        rebuilt_rows = KernelEntityMechanismPathsProjector(session).rebuild(
            space_id=str(space.id),
        )
        session.commit()
        assert rebuilt_rows == 120

        def _indexed_reasoning_seed_read():
            session.expire_all()
            return service.list_mechanism_candidates(
                research_space_id=str(space.id),
                start_entity_id=seed_entity_id,
                limit=200,
                offset=0,
            )

        indexed_samples, indexed_candidates = _measure_samples(
            _indexed_reasoning_seed_read,
        )
        assert len(indexed_candidates) == 120

        legacy_median = median(legacy_samples)
        indexed_median = median(indexed_samples)
        speedup = legacy_median / indexed_median if indexed_median > 0 else float("inf")

        print(  # noqa: T201
            "entity_mechanism_paths_benchmark "
            f"legacy_ms={legacy_median * 1000:.2f} "
            f"indexed_ms={indexed_median * 1000:.2f} "
            f"speedup={speedup:.2f}x",
        )

        assert indexed_median < legacy_median
