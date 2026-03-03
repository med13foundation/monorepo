"""Unit coverage for endpoint entity-shape guard behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.agents.services._relation_endpoint_entity_resolution_helpers import (
    _RelationEndpointEntityResolutionHelpers,
)
from src.application.agents.services._relation_endpoint_label_resolution_helpers import (
    evaluate_entity_shape,
)
from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
    from src.type_definitions.common import JSONObject


@dataclass(frozen=True)
class _DictionaryEntityType:
    id: str
    is_active: bool = True
    review_status: str = "ACTIVE"


@dataclass(frozen=True)
class _CreatedEntity:
    id: str
    entity_type: str
    display_label: str


class _StubDictionary:
    def get_entity_type(
        self,
        entity_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> _DictionaryEntityType | None:
        del include_inactive
        return _DictionaryEntityType(id=entity_type_id.strip().upper())

    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: str,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> _DictionaryEntityType:
        del reviewed_by, revocation_reason
        normalized = entity_type_id.strip().upper()
        return _DictionaryEntityType(
            id=normalized,
            is_active=review_status.strip().upper() == "ACTIVE",
            review_status=review_status.strip().upper(),
        )

    def create_entity_type(self, **kwargs: object) -> _DictionaryEntityType:
        entity_type = str(kwargs["entity_type"]).strip().upper()
        return _DictionaryEntityType(id=entity_type)


class _StubEntityRepository:
    def __init__(self) -> None:
        self.created_labels: list[str] = []
        self.identifiers: list[tuple[str, str, str]] = []

    def find_by_identifier(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str,
    ) -> None:
        del namespace, identifier_value, research_space_id

    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 10,
    ) -> list[_CreatedEntity]:
        del research_space_id, query, entity_type, limit
        return []

    def create(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
        metadata: JSONObject,
    ) -> _CreatedEntity:
        del research_space_id, metadata
        self.created_labels.append(display_label)
        return _CreatedEntity(
            id=f"entity-{len(self.created_labels)}",
            entity_type=entity_type,
            display_label=display_label,
        )

    def add_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str,
    ) -> None:
        del sensitivity
        self.identifiers.append((entity_id, namespace, identifier_value))


class _AcceptingShapeJudge(MappingJudgePort):
    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        del model_id
        selected = context.candidates[0]
        return MappingJudgeContract(
            confidence_score=0.93,
            rationale="Borderline endpoint label is a valid concept mention.",
            evidence=[],
            decision="matched",
            selected_variable_id=selected.variable_id,
            candidate_count=len(context.candidates),
            selection_rationale="Accept as endpoint entity label.",
            selected_candidate=selected,
            agent_run_id="mapping_judge:test-run",
        )

    def close(self) -> None:
        return


class _EndpointResolverHarness(_RelationEndpointEntityResolutionHelpers):
    def __init__(
        self,
        *,
        entities: _StubEntityRepository,
        dictionary: _StubDictionary,
        shape_judge: MappingJudgePort | None = None,
    ) -> None:
        self._entities = entities
        self._dictionary = dictionary
        self._endpoint_shape_judge = shape_judge


def test_evaluate_entity_shape_hard_rejects_sentence_label() -> None:
    decision = evaluate_entity_shape(
        entity_type="DISEASE",
        label=(
            "This study demonstrates that aspirin improves outcomes in patients "
            "with myocardial infarction."
        ),
    )

    assert decision.outcome == "REJECT"
    assert decision.reason_code == "shape_hard_reject"
    assert "sentence_discourse_marker" in decision.signals


def test_evaluate_entity_shape_accepts_variant_symbol() -> None:
    decision = evaluate_entity_shape(
        entity_type="VARIANT",
        label="c.123A>G",
    )

    assert decision.outcome == "ACCEPT"
    assert decision.reason_code == "shape_allowlisted_symbol"


def test_borderline_endpoint_without_agent_is_rejected() -> None:
    entities = _StubEntityRepository()
    resolver = _EndpointResolverHarness(
        entities=entities,
        dictionary=_StubDictionary(),
        shape_judge=None,
    )

    result = resolver._resolve_relation_endpoint_entity_id(
        research_space_id="space-1",
        entity_type="DISEASE",
        label=(
            "Expression profile associated with outcomes in patients with chronic "
            "heart failure after six month treatment response analysis 2024"
        ),
        publication_entity_id=None,
        endpoint_name="target",
    )

    assert result.entity_id is None
    assert result.failure_reason == "relation_endpoint_shape_rejected"
    assert isinstance(result.failure_metadata, dict)
    assert result.failure_metadata.get("shape_rejection_subreason") == (
        "borderline_no_agent"
    )
    assert entities.created_labels == []


def test_borderline_endpoint_agent_accepts_and_entity_is_created() -> None:
    entities = _StubEntityRepository()
    resolver = _EndpointResolverHarness(
        entities=entities,
        dictionary=_StubDictionary(),
        shape_judge=_AcceptingShapeJudge(),
    )

    result = resolver._resolve_relation_endpoint_entity_id(
        research_space_id="space-1",
        entity_type="DISEASE",
        label=(
            "Expression profile associated with outcomes in patients with chronic "
            "heart failure after six month treatment response analysis 2024"
        ),
        publication_entity_id=None,
        endpoint_name="target",
    )

    assert result.entity_id == "entity-1"
    assert result.failure_reason is None
    assert entities.created_labels == [
        (
            "Expression profile associated with outcomes in patients with chronic "
            "heart failure after six month treatment response analysis 2024"
        ),
    ]
