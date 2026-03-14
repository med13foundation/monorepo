"""Unit tests for the entity-neighbors rebuild script."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pytest

from scripts import rebuild_graph_read_model_entity_neighbors as rebuild_script

pytestmark = pytest.mark.graph


@dataclass
class _SessionStub:
    committed: bool = False
    closed: bool = False

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class _ProjectorStub:
    rebuilt_rows: int
    calls: list[str | None]

    def rebuild(self, *, space_id: str | None = None) -> int:
        self.calls.append(space_id)
        return self.rebuilt_rows


def _args(
    *,
    space_id: str | None = None,
    json_output: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(space_id=space_id, json=json_output)


def test_run_rebuild_for_single_space(capsys) -> None:
    session = _SessionStub()
    projector = _ProjectorStub(rebuilt_rows=6, calls=[])

    exit_code = rebuild_script.run_rebuild(
        _args(space_id="space-1"),
        session_factory=lambda: session,
        projector_factory=lambda active_session: projector,
    )

    assert exit_code == 0
    assert projector.calls == ["space-1"]
    assert session.committed is True
    assert session.closed is True
    assert "model=entity_neighbors" in capsys.readouterr().out


def test_run_rebuild_globally_can_emit_json(capsys) -> None:
    session = _SessionStub()
    projector = _ProjectorStub(rebuilt_rows=9, calls=[])

    exit_code = rebuild_script.run_rebuild(
        _args(json_output=True),
        session_factory=lambda: session,
        projector_factory=lambda active_session: projector,
    )

    assert exit_code == 0
    assert projector.calls == [None]
    assert session.committed is True
    assert session.closed is True
    output = capsys.readouterr().out
    assert '"model_name": "entity_neighbors"' in output
    assert '"rebuilt_rows": 9' in output
