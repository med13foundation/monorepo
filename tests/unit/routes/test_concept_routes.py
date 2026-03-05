"""Regression tests for research-space concept routes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database.session import get_session
from src.domain.entities.kernel.concepts import (
    ConceptAlias,
    ConceptDecision,
    ConceptMember,
)
from src.domain.entities.user import User, UserRole, UserStatus
from src.routes.auth import get_current_active_user
from src.routes.research_spaces import research_spaces_router
from src.routes.research_spaces.dependencies import get_membership_service
from src.routes.research_spaces.kernel_dependencies import get_concept_service

_RESEARCHER_ID = UUID("11111111-1111-1111-1111-111111111111")


class _SessionStub:
    def __init__(self) -> None:
        self.bind = None


class _MembershipServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    def is_user_member(self, space_id: UUID, user_id: UUID) -> bool:
        self.calls.append((space_id, user_id))
        return True


class _ConceptServiceStub:
    def __init__(
        self,
        *,
        members: list[ConceptMember],
        aliases: list[ConceptAlias],
        decisions: list[ConceptDecision],
    ) -> None:
        self._members = members
        self._aliases = aliases
        self._decisions = decisions
        self.member_calls: list[dict[str, object]] = []
        self.alias_calls: list[dict[str, object]] = []
        self.decision_calls: list[dict[str, object]] = []

    def list_concept_members(
        self,
        *,
        research_space_id: str,
        concept_set_id: str | None,
        include_inactive: bool,
        offset: int,
        limit: int,
    ) -> list[ConceptMember]:
        self.member_calls.append(
            {
                "research_space_id": research_space_id,
                "concept_set_id": concept_set_id,
                "include_inactive": include_inactive,
                "offset": offset,
                "limit": limit,
            },
        )
        return self._members

    def list_concept_aliases(
        self,
        *,
        research_space_id: str,
        concept_member_id: str | None,
        include_inactive: bool,
        offset: int,
        limit: int,
    ) -> list[ConceptAlias]:
        self.alias_calls.append(
            {
                "research_space_id": research_space_id,
                "concept_member_id": concept_member_id,
                "include_inactive": include_inactive,
                "offset": offset,
                "limit": limit,
            },
        )
        return self._aliases

    def list_decisions(
        self,
        *,
        research_space_id: str,
        decision_status: str | None,
        offset: int,
        limit: int,
    ) -> list[ConceptDecision]:
        self.decision_calls.append(
            {
                "research_space_id": research_space_id,
                "decision_status": decision_status,
                "offset": offset,
                "limit": limit,
            },
        )
        return self._decisions


def _active_researcher() -> User:
    return User(
        id=_RESEARCHER_ID,
        email="researcher@example.com",
        username="researcher",
        full_name="Researcher User",
        hashed_password="hashed-password",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )


def _build_member(*, space_id: UUID, concept_set_id: UUID) -> ConceptMember:
    now = datetime.now(UTC)
    return ConceptMember(
        id=str(uuid4()),
        concept_set_id=str(concept_set_id),
        research_space_id=str(space_id),
        domain_context="biomedical",
        dictionary_dimension="entity_type",
        dictionary_entry_id="GENE",
        canonical_label="MED13",
        normalized_label="MED13",
        sense_key="gene",
        is_provisional=False,
        metadata_payload={"source": "unit-test"},
        created_by="manual:test",
        source_ref="unit:test",
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        is_active=True,
        valid_from=None,
        valid_to=None,
        superseded_by=None,
        created_at=now,
        updated_at=now,
    )


def _build_alias(*, space_id: UUID, member_id: str) -> ConceptAlias:
    now = datetime.now(UTC)
    return ConceptAlias(
        id=1,
        concept_member_id=member_id,
        research_space_id=str(space_id),
        domain_context="biomedical",
        alias_label="mediator complex subunit 13",
        alias_normalized="MEDIATOR COMPLEX SUBUNIT 13",
        source="manual",
        created_by="manual:test",
        source_ref="unit:test",
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        is_active=True,
        valid_from=None,
        valid_to=None,
        superseded_by=None,
        created_at=now,
        updated_at=now,
    )


def _build_decision(
    *,
    space_id: UUID,
    member_id: str,
    concept_set_id: UUID,
) -> ConceptDecision:
    now = datetime.now(UTC)
    return ConceptDecision(
        id=str(uuid4()),
        research_space_id=str(space_id),
        concept_set_id=str(concept_set_id),
        concept_member_id=member_id,
        concept_link_id=None,
        decision_type="MAP",
        decision_status="NEEDS_REVIEW",
        proposed_by="agent:test",
        decided_by=None,
        confidence=0.82,
        rationale="Evidence suggests mapping.",
        evidence_payload={"paper_count": 2},
        decision_payload={"target": "GENE:MED13"},
        harness_outcome="PASS",
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def _build_client(
    *,
    concept_service: _ConceptServiceStub,
    membership_service: _MembershipServiceStub,
    session: _SessionStub,
) -> TestClient:
    app = FastAPI()
    app.include_router(research_spaces_router)
    app.dependency_overrides[get_current_active_user] = _active_researcher
    app.dependency_overrides[get_membership_service] = lambda: membership_service
    app.dependency_overrides[get_concept_service] = lambda: concept_service
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_list_concept_members_applies_filters_and_returns_payload() -> None:
    space_id = uuid4()
    concept_set_id = uuid4()
    member = _build_member(space_id=space_id, concept_set_id=concept_set_id)
    membership = _MembershipServiceStub()
    concept_service = _ConceptServiceStub(
        members=[member],
        aliases=[],
        decisions=[],
    )
    client = _build_client(
        concept_service=concept_service,
        membership_service=membership,
        session=_SessionStub(),
    )

    response = client.get(
        f"/research-spaces/{space_id}/concepts/members",
        params={
            "concept_set_id": str(concept_set_id),
            "include_inactive": "true",
            "offset": 5,
            "limit": 20,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["concept_members"][0]["id"] == member.id
    assert concept_service.member_calls == [
        {
            "research_space_id": str(space_id),
            "concept_set_id": str(concept_set_id),
            "include_inactive": True,
            "offset": 5,
            "limit": 20,
        },
    ]
    assert membership.calls == [(space_id, _RESEARCHER_ID)]


def test_list_concept_aliases_applies_filters_and_returns_payload() -> None:
    space_id = uuid4()
    concept_set_id = uuid4()
    member = _build_member(space_id=space_id, concept_set_id=concept_set_id)
    alias = _build_alias(space_id=space_id, member_id=member.id)
    membership = _MembershipServiceStub()
    concept_service = _ConceptServiceStub(
        members=[],
        aliases=[alias],
        decisions=[],
    )
    client = _build_client(
        concept_service=concept_service,
        membership_service=membership,
        session=_SessionStub(),
    )

    response = client.get(
        f"/research-spaces/{space_id}/concepts/aliases",
        params={
            "concept_member_id": member.id,
            "include_inactive": "false",
            "offset": 1,
            "limit": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["concept_aliases"][0]["id"] == alias.id
    assert concept_service.alias_calls == [
        {
            "research_space_id": str(space_id),
            "concept_member_id": member.id,
            "include_inactive": False,
            "offset": 1,
            "limit": 10,
        },
    ]
    assert membership.calls == [(space_id, _RESEARCHER_ID)]


def test_list_concept_decisions_applies_filters_and_returns_payload() -> None:
    space_id = uuid4()
    concept_set_id = uuid4()
    member = _build_member(space_id=space_id, concept_set_id=concept_set_id)
    decision = _build_decision(
        space_id=space_id,
        member_id=member.id,
        concept_set_id=concept_set_id,
    )
    membership = _MembershipServiceStub()
    concept_service = _ConceptServiceStub(
        members=[],
        aliases=[],
        decisions=[decision],
    )
    client = _build_client(
        concept_service=concept_service,
        membership_service=membership,
        session=_SessionStub(),
    )

    response = client.get(
        f"/research-spaces/{space_id}/concepts/decisions",
        params={
            "decision_status": "NEEDS_REVIEW",
            "offset": 2,
            "limit": 15,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["concept_decisions"][0]["id"] == decision.id
    assert concept_service.decision_calls == [
        {
            "research_space_id": str(space_id),
            "decision_status": "NEEDS_REVIEW",
            "offset": 2,
            "limit": 15,
        },
    ]
    assert membership.calls == [(space_id, _RESEARCHER_ID)]
