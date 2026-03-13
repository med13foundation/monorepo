"""Unit coverage for the operational reasoning-path rebuild script."""

from __future__ import annotations

import argparse
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

    def model_dump(self, *, mode: str = "python") -> dict[str, object]:
        del mode
        return {
            "research_space_id": self.research_space_id,
            "eligible_claims": self.eligible_claims,
            "accepted_claim_relations": self.accepted_claim_relations,
            "rebuilt_paths": self.rebuilt_paths,
            "max_depth": self.max_depth,
        }


class _ReasoningPathRebuildResponseStub:
    def __init__(self, summaries: list[_SummaryStub]) -> None:
        self._summaries = summaries

    def model_dump(self, *, mode: str = "python") -> dict[str, object]:
        del mode
        return {
            "summaries": [summary.model_dump() for summary in self._summaries],
        }


class _ReasoningPathClientStub:
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
        self.closed = False

    def rebuild_reasoning_paths(
        self,
        *,
        space_id: str | None = None,
        max_depth: int,
        replace_existing: bool,
    ) -> _ReasoningPathRebuildResponseStub:
        if space_id is not None:
            self.space_calls.append(
                {
                    "research_space_id": space_id,
                    "max_depth": max_depth,
                    "replace_existing": replace_existing,
                },
            )
            return _ReasoningPathRebuildResponseStub([self._space_summaries[0]])

        self.global_calls.append(
            {
                "max_depth": max_depth,
                "replace_existing": replace_existing,
            },
        )
        return _ReasoningPathRebuildResponseStub(list(self._global_summaries))

    def close(self) -> None:
        self.closed = True


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
    client = _ReasoningPathClientStub(
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
    monkeypatch.setattr(rebuild_script, "_build_client", lambda args: client)

    exit_code = rebuild_script.run_rebuild(
        _args(space_id="space-1", max_depth=9),
    )

    assert exit_code == 0
    assert client.space_calls == [
        {
            "research_space_id": "space-1",
            "max_depth": 4,
            "replace_existing": True,
        },
    ]
    assert client.closed is True
    output = capsys.readouterr().out
    assert "space=space-1" in output
    assert "rebuilt_paths=1" in output


def test_run_rebuild_globally_can_emit_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _ReasoningPathClientStub(
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
    monkeypatch.setattr(rebuild_script, "_build_client", lambda args: client)

    exit_code = rebuild_script.run_rebuild(
        _args(max_depth=2, json_output=True),
    )

    assert exit_code == 0
    assert client.global_calls == [{"max_depth": 2, "replace_existing": True}]
    assert client.closed is True
    output = capsys.readouterr().out
    assert '"research_space_id": "space-a"' in output
    assert '"research_space_id": "space-b"' in output
