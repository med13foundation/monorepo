"""Unit coverage for semantic concept member reuse before provisional creation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

from src.application.agents.services._extraction_relation_concept_helpers import (
    _ensure_concept_member,
)
from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.domain.entities.kernel.concepts import (
    ConceptAlias,
    ConceptDecision,
    ConceptMember,
)
from src.domain.ports.concept_port import ConceptPort

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext


def _build_member(
    *,
    canonical_label: str,
    normalized_label: str,
    sense_key: str,
    concept_set_id: str,
    research_space_id: str,
) -> ConceptMember:
    now = datetime.now(UTC)
    return ConceptMember(
        id=str(uuid4()),
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
        domain_context="general",
        dictionary_dimension="entity_types",
        dictionary_entry_id="PROTEIN_COMPLEX",
        canonical_label=canonical_label,
        normalized_label=normalized_label,
        sense_key=sense_key,
        is_provisional=False,
        metadata_payload={},
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        is_active=True,
        valid_from=now,
        valid_to=None,
        superseded_by=None,
        created_at=now,
        updated_at=now,
    )


def _build_alias(
    *,
    concept_member_id: str,
    alias_label: str,
    alias_normalized: str,
    research_space_id: str,
) -> ConceptAlias:
    now = datetime.now(UTC)
    return ConceptAlias(
        id=1,
        concept_member_id=concept_member_id,
        research_space_id=research_space_id,
        domain_context="general",
        alias_label=alias_label,
        alias_normalized=alias_normalized,
        source="pubmed",
        created_by="seed",
        source_ref=None,
        review_status="ACTIVE",
        reviewed_by=None,
        reviewed_at=None,
        revocation_reason=None,
        is_active=True,
        valid_from=now,
        valid_to=None,
        superseded_by=None,
        created_at=now,
        updated_at=now,
    )


def _build_decision() -> ConceptDecision:
    now = datetime.now(UTC)
    return ConceptDecision(
        id=str(uuid4()),
        research_space_id=str(uuid4()),
        concept_set_id=None,
        concept_member_id=None,
        concept_link_id=None,
        decision_type="MAP",
        decision_status="PROPOSED",
        proposed_by="agent:test",
        decided_by=None,
        confidence=0.82,
        rationale="Semantic match requires review.",
        evidence_payload={},
        decision_payload={},
        harness_outcome=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


class _MatchedConceptJudge(MappingJudgePort):
    def __init__(self, *, selected_member_id: str) -> None:
        self.selected_member_id = selected_member_id

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        del model_id
        selected = next(
            candidate
            for candidate in context.candidates
            if candidate.variable_id == self.selected_member_id
        )
        return MappingJudgeContract(
            confidence_score=0.91,
            rationale="Existing concept member already captures this label.",
            evidence=[],
            decision="matched",
            selected_variable_id=selected.variable_id,
            candidate_count=len(context.candidates),
            selection_rationale="Reuse the existing concept member.",
            selected_candidate=selected,
            agent_run_id="mapping_judge:concept-merge",
        )

    def close(self) -> None:
        return


class _AmbiguousConceptJudge(MappingJudgePort):
    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        del context, model_id
        return MappingJudgeContract(
            confidence_score=0.51,
            rationale="The candidates are close enough to require researcher review.",
            evidence=[],
            decision="ambiguous",
            selected_variable_id=None,
            candidate_count=2,
            selection_rationale="Do not auto-merge this concept label.",
            selected_candidate=None,
            agent_run_id="mapping_judge:concept-merge",
        )

    def close(self) -> None:
        return


def test_ensure_concept_member_reuses_existing_alias_owner() -> None:
    research_space_id = str(uuid4())
    concept_set_id = str(uuid4())
    member = _build_member(
        canonical_label="Mediator kinase module",
        normalized_label="mediator kinase module",
        sense_key="PROTEIN_COMPLEX",
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
    )
    concept_service = Mock(spec=ConceptPort)
    concept_service.list_concept_members.return_value = []
    concept_service.resolve_member_by_alias.return_value = member
    concept_service.list_concept_aliases.return_value = [
        _build_alias(
            concept_member_id=member.id,
            alias_label="CDK8 kinase module",
            alias_normalized="cdk8 kinase module",
            research_space_id=research_space_id,
        ),
    ]

    result = _ensure_concept_member(
        concept_service=concept_service,
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
        domain_context="general",
        candidate_label="CDK8 kinase module",
        sense_key="PROTEIN_COMPLEX",
        source_ref="source_document:test",
        alias_source="pubmed",
        research_space_settings={},
        member_cache={},
        alias_cache=set(),
        alias_scope_cache={},
        mapping_judge_agent=None,
    )

    assert result.concept_refs == {"concept_member_id": member.id}
    assert result.members_created_count == 0
    assert result.aliases_created_count == 0
    assert result.decisions_proposed_count == 0
    concept_service.create_concept_member.assert_not_called()
    concept_service.create_concept_alias.assert_not_called()


def test_ensure_concept_member_uses_judge_to_reuse_semantic_candidate() -> None:
    research_space_id = str(uuid4())
    concept_set_id = str(uuid4())
    member = _build_member(
        canonical_label="Mediator kinase module",
        normalized_label="mediator kinase module",
        sense_key="PROTEIN_COMPLEX",
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
    )
    concept_service = Mock(spec=ConceptPort)
    concept_service.list_concept_members.return_value = [member]
    concept_service.resolve_member_by_alias.return_value = None
    concept_service.list_concept_aliases.return_value = []
    concept_service.create_concept_alias.return_value = _build_alias(
        concept_member_id=member.id,
        alias_label="Mediator kinase complex",
        alias_normalized="mediator kinase complex",
        research_space_id=research_space_id,
    )

    result = _ensure_concept_member(
        concept_service=concept_service,
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
        domain_context="general",
        candidate_label="Mediator kinase complex",
        sense_key="PROTEIN_COMPLEX",
        source_ref="source_document:test",
        alias_source="pubmed",
        research_space_settings={},
        member_cache={},
        alias_cache=set(),
        alias_scope_cache={},
        mapping_judge_agent=_MatchedConceptJudge(selected_member_id=member.id),
    )

    assert result.concept_refs == {"concept_member_id": member.id}
    assert result.members_created_count == 0
    assert result.aliases_created_count == 1
    assert result.decisions_proposed_count == 0
    concept_service.create_concept_member.assert_not_called()
    concept_service.propose_decision.assert_not_called()


def test_ensure_concept_member_proposes_review_before_provisional_create() -> None:
    research_space_id = str(uuid4())
    concept_set_id = str(uuid4())
    existing_member = _build_member(
        canonical_label="Mediator kinase module",
        normalized_label="mediator kinase module",
        sense_key="PROTEIN_COMPLEX",
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
    )
    provisional_member = _build_member(
        canonical_label="Mediator kinase assembly",
        normalized_label="mediator kinase assembly",
        sense_key="PROTEIN_COMPLEX",
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
    )
    concept_service = Mock(spec=ConceptPort)
    concept_service.list_concept_members.return_value = [existing_member]
    concept_service.resolve_member_by_alias.return_value = None
    concept_service.list_concept_aliases.return_value = []
    concept_service.propose_decision.return_value = _build_decision()
    concept_service.create_concept_member.return_value = provisional_member
    concept_service.create_concept_alias.return_value = _build_alias(
        concept_member_id=provisional_member.id,
        alias_label="Mediator kinase assembly",
        alias_normalized="mediator kinase assembly",
        research_space_id=research_space_id,
    )

    result = _ensure_concept_member(
        concept_service=concept_service,
        concept_set_id=concept_set_id,
        research_space_id=research_space_id,
        domain_context="general",
        candidate_label="Mediator kinase assembly",
        sense_key="PROTEIN_COMPLEX",
        source_ref="source_document:test",
        alias_source="pubmed",
        research_space_settings={},
        member_cache={},
        alias_cache=set(),
        alias_scope_cache={},
        mapping_judge_agent=_AmbiguousConceptJudge(),
    )

    assert result.concept_refs is not None
    assert result.concept_refs["concept_member_id"] == provisional_member.id
    assert result.concept_refs["decision_ids"] == [
        concept_service.propose_decision.return_value.id,
    ]
    assert result.members_created_count == 1
    assert result.aliases_created_count == 1
    assert result.decisions_proposed_count == 1
    concept_service.create_concept_member.assert_called_once()
    concept_service.propose_decision.assert_called_once()
