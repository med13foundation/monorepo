from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from src.database.session import get_session
from src.domain.entities.user import User, UserRole, UserStatus
from src.routes.admin_routes import dictionary as dictionary_routes
from src.routes.auth import get_current_active_user
from src.routes.research_spaces import research_spaces_router
from src.routes.research_spaces.dependencies import get_membership_service
from src.routes.research_spaces.kernel_dependencies import (
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_invariant_service,
    get_kernel_relation_projection_source_service,
    get_kernel_relation_service,
)


class _SessionStub:
    def __init__(self, *, commit_error: IntegrityError | None = None) -> None:
        self.bind = None
        self._commit_error = commit_error
        self.rollback_called = False

    def commit(self) -> None:
        if self._commit_error is not None:
            raise self._commit_error

    def rollback(self) -> None:
        self.rollback_called = True


class _DictionaryServiceStub:
    def set_entity_type_review_status(self, *_args, **_kwargs) -> object:
        return object()

    def set_relation_type_review_status(self, *_args, **_kwargs) -> object:
        return object()


class _RelationServiceStub:
    def create_relation(self, *_args, **_kwargs) -> object:
        return type(
            "_Relation",
            (),
            {"id": uuid4(), "relation_type": "ASSOCIATED_WITH"},
        )()


class _EntityServiceStub:
    def get_entity(self, entity_id: str) -> object:
        return type(
            "_Entity",
            (),
            {
                "id": entity_id,
                "entity_type": "GENE",
                "display_label": "Entity",
            },
        )()


class _RelationClaimServiceStub:
    def create_claim(self, *_args, **_kwargs) -> object:
        return type("_Claim", (), {"id": uuid4()})()


class _ClaimParticipantServiceStub:
    def create_participant(self, *_args, **_kwargs) -> object:
        return object()


class _RelationProjectionSourceServiceStub:
    def create_projection_source(self, *_args, **_kwargs) -> object:
        return object()


class _FailingRelationProjectionSourceServiceStub:
    def create_projection_source(self, *_args, **_kwargs) -> object:
        msg = "projection lineage write failed"
        raise RuntimeError(msg)


class _RelationProjectionInvariantServiceStub:
    def assert_no_orphan_relations_for_write(self, *_args, **_kwargs) -> None:
        return None


def _admin_user() -> User:
    return User(
        email="admin@example.com",
        username="admin",
        full_name="Admin User",
        hashed_password="hashed-password",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )


def test_entity_type_review_status_maps_integrity_error_to_conflict() -> None:
    service = _DictionaryServiceStub()
    session = _SessionStub(
        commit_error=IntegrityError(
            "UPDATE dictionary_entity_types",
            {},
            Exception("in use by graph"),
        ),
    )
    app = FastAPI()
    app.include_router(dictionary_routes.router)
    app.dependency_overrides[dictionary_routes.require_admin_user] = _admin_user
    app.dependency_overrides[dictionary_routes.get_dictionary_service] = lambda: service
    app.dependency_overrides[dictionary_routes.get_admin_db_session] = lambda: session
    client = TestClient(app)

    response = client.patch(
        "/dictionary/entity-types/GENE/review-status",
        json={"review_status": "REVOKED", "revocation_reason": "retire"},
    )

    assert response.status_code == 409
    assert "conflicts with active graph references" in response.json()["detail"]
    assert session.rollback_called is True


def test_relation_type_review_status_maps_integrity_error_to_conflict() -> None:
    service = _DictionaryServiceStub()
    session = _SessionStub(
        commit_error=IntegrityError(
            "UPDATE dictionary_relation_types",
            {},
            Exception("in use by graph"),
        ),
    )
    app = FastAPI()
    app.include_router(dictionary_routes.router)
    app.dependency_overrides[dictionary_routes.require_admin_user] = _admin_user
    app.dependency_overrides[dictionary_routes.get_dictionary_service] = lambda: service
    app.dependency_overrides[dictionary_routes.get_admin_db_session] = lambda: session
    client = TestClient(app)

    response = client.patch(
        "/dictionary/relation-types/ASSOCIATED_WITH/review-status",
        json={"review_status": "REVOKED", "revocation_reason": "retire"},
    )

    assert response.status_code == 409
    assert "conflicts with active graph references" in response.json()["detail"]
    assert session.rollback_called is True


def test_create_relation_maps_integrity_error_to_conflict() -> None:
    relation_service = _RelationServiceStub()
    entity_service = _EntityServiceStub()
    claim_service = _RelationClaimServiceStub()
    participant_service = _ClaimParticipantServiceStub()
    projection_service = _RelationProjectionSourceServiceStub()
    invariant_service = _RelationProjectionInvariantServiceStub()
    session = _SessionStub(
        commit_error=IntegrityError(
            "INSERT INTO relations",
            {},
            Exception("requires evidence"),
        ),
    )
    app = FastAPI()
    app.include_router(research_spaces_router)
    app.dependency_overrides[get_current_active_user] = _admin_user
    app.dependency_overrides[get_membership_service] = lambda: object()
    app.dependency_overrides[get_kernel_relation_service] = lambda: relation_service
    app.dependency_overrides[get_kernel_entity_service] = lambda: entity_service
    app.dependency_overrides[get_kernel_relation_claim_service] = lambda: claim_service
    app.dependency_overrides[get_kernel_claim_participant_service] = (
        lambda: participant_service
    )
    app.dependency_overrides[get_kernel_relation_projection_invariant_service] = (
        lambda: invariant_service
    )
    app.dependency_overrides[get_kernel_relation_projection_source_service] = (
        lambda: projection_service
    )
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    response = client.post(
        f"/research-spaces/{uuid4()}/relations",
        json={
            "source_id": str(uuid4()),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(uuid4()),
            "confidence": 0.9,
            "evidence_summary": "evidence",
            "evidence_tier": "LITERATURE",
            "provenance_id": None,
        },
    )

    assert response.status_code == 409
    assert "Relation write conflicts" in response.json()["detail"]
    assert session.rollback_called is True


def test_create_relation_projection_failure_rolls_back_and_returns_500() -> None:
    relation_service = _RelationServiceStub()
    entity_service = _EntityServiceStub()
    claim_service = _RelationClaimServiceStub()
    participant_service = _ClaimParticipantServiceStub()
    projection_service = _FailingRelationProjectionSourceServiceStub()
    invariant_service = _RelationProjectionInvariantServiceStub()
    session = _SessionStub()
    app = FastAPI()
    app.include_router(research_spaces_router)
    app.dependency_overrides[get_current_active_user] = _admin_user
    app.dependency_overrides[get_membership_service] = lambda: object()
    app.dependency_overrides[get_kernel_relation_service] = lambda: relation_service
    app.dependency_overrides[get_kernel_entity_service] = lambda: entity_service
    app.dependency_overrides[get_kernel_relation_claim_service] = lambda: claim_service
    app.dependency_overrides[get_kernel_claim_participant_service] = (
        lambda: participant_service
    )
    app.dependency_overrides[get_kernel_relation_projection_invariant_service] = (
        lambda: invariant_service
    )
    app.dependency_overrides[get_kernel_relation_projection_source_service] = (
        lambda: projection_service
    )
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    response = client.post(
        f"/research-spaces/{uuid4()}/relations",
        json={
            "source_id": str(uuid4()),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(uuid4()),
            "confidence": 0.9,
            "evidence_summary": "evidence",
            "evidence_tier": "LITERATURE",
            "provenance_id": None,
        },
    )

    assert response.status_code == 500
    assert "Failed to create relation" in response.json()["detail"]
    assert session.rollback_called is True
