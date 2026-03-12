"""Tests for claim-backed canonical relation invariant service."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.services.kernel.kernel_relation_projection_invariant_service import (
    KernelRelationProjectionInvariantService,
    OrphanCanonicalRelationError,
)

pytestmark = pytest.mark.graph


@dataclass
class _ProjectionRepoStub:
    orphan_relations: list[object]
    orphan_count: int
    has_projection: bool
    list_calls: list[dict[str, object]]
    count_calls: list[dict[str, object]]
    has_calls: list[dict[str, object]]

    def list_orphan_relations(
        self,
        *,
        research_space_id: str | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[object]:
        self.list_calls.append(
            {
                "research_space_id": research_space_id,
                "limit": limit,
                "offset": offset,
            },
        )
        return list(self.orphan_relations)

    def count_orphan_relations(self, *, research_space_id: str | None) -> int:
        self.count_calls.append({"research_space_id": research_space_id})
        return self.orphan_count

    def has_projection_for_relation(
        self,
        *,
        research_space_id: str,
        relation_id: str,
    ) -> bool:
        self.has_calls.append(
            {
                "research_space_id": research_space_id,
                "relation_id": relation_id,
            },
        )
        return self.has_projection


def test_lists_and_counts_orphan_relations() -> None:
    orphan_relation = SimpleNamespace(id=str(uuid4()))
    repo = _ProjectionRepoStub(
        orphan_relations=[orphan_relation],
        orphan_count=1,
        has_projection=True,
        list_calls=[],
        count_calls=[],
        has_calls=[],
    )
    service = KernelRelationProjectionInvariantService(repo)

    listed = service.list_orphan_relations(space_id="space-1", limit=10, offset=5)
    counted = service.count_orphan_relations(space_id="space-1")

    assert listed == [orphan_relation]
    assert counted == 1
    assert repo.list_calls == [
        {"research_space_id": "space-1", "limit": 10, "offset": 5},
    ]
    assert repo.count_calls == [{"research_space_id": "space-1"}]


def test_assert_no_orphan_relations_for_write_passes_when_lineage_exists() -> None:
    repo = _ProjectionRepoStub(
        orphan_relations=[],
        orphan_count=0,
        has_projection=True,
        list_calls=[],
        count_calls=[],
        has_calls=[],
    )
    service = KernelRelationProjectionInvariantService(repo)

    service.assert_no_orphan_relations_for_write(
        relation_id="relation-1",
        research_space_id="space-1",
    )

    assert repo.has_calls == [
        {"research_space_id": "space-1", "relation_id": "relation-1"},
    ]


def test_assert_no_orphan_relations_for_write_raises_without_lineage() -> None:
    repo = _ProjectionRepoStub(
        orphan_relations=[],
        orphan_count=0,
        has_projection=False,
        list_calls=[],
        count_calls=[],
        has_calls=[],
    )
    service = KernelRelationProjectionInvariantService(repo)

    with pytest.raises(OrphanCanonicalRelationError):
        service.assert_no_orphan_relations_for_write(
            relation_id="relation-1",
            research_space_id="space-1",
        )
