"""Unit coverage for the operational reasoning-path rebuild script."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from scripts import rebuild_reasoning_paths as rebuild_script

pytestmark = pytest.mark.graph


@dataclass(frozen=True)
class _SummaryStub:
    research_space_id: str
    eligible_claims: int
    accepted_claim_relations: int
    rebuilt_paths: int
    max_depth: int


class _ReasoningPathServiceStub:
    def __init__(
        self,
        *,
        space_summaries: list[_SummaryStub] | None = None,
        global_summaries: list[_SummaryStub] | None = None,
    ) -> None:
        self._space_summaries = space_summaries or []
        self._global_summaries = global_summaries or []
        self.space_calls: list[dict[str, object]] = []
        self.global_calls: list[dict[str, object]] = []

    def rebuild_for_space(
        self,
        research_space_id: str,
        *,
        max_depth: int,
        replace_existing: bool,
    ) -> _SummaryStub:
        self.space_calls.append(
            {
                "research_space_id": research_space_id,
                "max_depth": max_depth,
                "replace_existing": replace_existing,
            },
        )
        return self._space_summaries[0]

    def rebuild_global(
        self,
        *,
        max_depth: int,
    ) -> list[_SummaryStub]:
        self.global_calls.append({"max_depth": max_depth})
        return list(self._global_summaries)


class _SessionStub:
    committed: bool

    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True


@contextmanager
def _session_factory() -> _SessionStub:
    yield _SessionStub()


def _args(
    *,
    space_id: str | None = None,
    max_depth: int = 4,
    json_output: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        space_id=space_id,
        max_depth=max_depth,
        json=json_output,
    )


def test_run_rebuild_for_single_space_clamps_depth_and_commits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _ReasoningPathServiceStub(
        space_summaries=[
            _SummaryStub(
                research_space_id="space-1",
                eligible_claims=3,
                accepted_claim_relations=2,
                rebuilt_paths=1,
                max_depth=4,
            ),
        ],
    )
    monkeypatch.setattr(rebuild_script, "_build_service", lambda session: service)
    monkeypatch.setattr(
        rebuild_script,
        "set_session_rls_context",
        lambda *args, **kwargs: None,
    )

    exit_code = rebuild_script.run_rebuild(
        _args(space_id="space-1", max_depth=9),
        session_factory=_session_factory,
    )

    assert exit_code == 0
    assert service.space_calls == [
        {
            "research_space_id": "space-1",
            "max_depth": 4,
            "replace_existing": True,
        },
    ]
    output = capsys.readouterr().out
    assert "space=space-1" in output
    assert "rebuilt_paths=1" in output


def test_run_rebuild_globally_can_emit_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _ReasoningPathServiceStub(
        global_summaries=[
            _SummaryStub(
                research_space_id="space-a",
                eligible_claims=2,
                accepted_claim_relations=1,
                rebuilt_paths=1,
                max_depth=2,
            ),
            _SummaryStub(
                research_space_id="space-b",
                eligible_claims=0,
                accepted_claim_relations=0,
                rebuilt_paths=0,
                max_depth=2,
            ),
        ],
    )
    monkeypatch.setattr(rebuild_script, "_build_service", lambda session: service)
    monkeypatch.setattr(
        rebuild_script,
        "set_session_rls_context",
        lambda *args, **kwargs: None,
    )

    exit_code = rebuild_script.run_rebuild(
        _args(max_depth=2, json_output=True),
        session_factory=_session_factory,
    )

    assert exit_code == 0
    assert service.global_calls == [{"max_depth": 2}]
    output = capsys.readouterr().out
    assert '"research_space_id": "space-a"' in output
    assert '"research_space_id": "space-b"' in output
