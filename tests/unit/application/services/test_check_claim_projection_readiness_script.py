"""Unit coverage for the operational claim projection readiness script."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pytest

from scripts import check_claim_projection_readiness as readiness_script

pytestmark = pytest.mark.graph


@dataclass(frozen=True)
class _IssueStub:
    count: int
    samples: tuple[object, ...] = ()

    def model_dump(self, *, mode: str = "python") -> dict[str, object]:
        del mode
        return {
            "count": self.count,
            "samples": list(self.samples),
        }


@dataclass(frozen=True)
class _ReportStub:
    ready: bool
    orphan_relations: _IssueStub
    missing_claim_participants: _IssueStub
    missing_claim_evidence: _IssueStub
    linked_relation_mismatches: _IssueStub
    invalid_projection_relations: _IssueStub

    def model_dump(self, *, mode: str = "python") -> dict[str, object]:
        del mode
        return {
            "ready": self.ready,
            "orphan_relations": self.orphan_relations.model_dump(),
            "missing_claim_participants": (
                self.missing_claim_participants.model_dump()
            ),
            "missing_claim_evidence": self.missing_claim_evidence.model_dump(),
            "linked_relation_mismatches": (
                self.linked_relation_mismatches.model_dump()
            ),
            "invalid_projection_relations": (
                self.invalid_projection_relations.model_dump()
            ),
        }


@dataclass(frozen=True)
class _RepairSummaryStub:
    participant_backfill: dict[str, object]
    materialized_claims: int
    detached_claims: int
    unresolved_claims: int
    dry_run: bool

    def model_dump(self, *, mode: str = "python") -> dict[str, object]:
        del mode
        return {
            "participant_backfill": dict(self.participant_backfill),
            "materialized_claims": self.materialized_claims,
            "detached_claims": self.detached_claims,
            "unresolved_claims": self.unresolved_claims,
            "dry_run": self.dry_run,
        }


class _ReadinessClientStub:
    def __init__(
        self,
        *,
        report: _ReportStub,
        repair_summary: _RepairSummaryStub | None = None,
    ) -> None:
        self._report = report
        self._repair_summary = repair_summary
        self.repair_calls: list[bool] = []
        self.sample_limits: list[int] = []
        self.closed = False

    def repair_projections(self, *, dry_run: bool) -> _RepairSummaryStub:
        self.repair_calls.append(dry_run)
        if self._repair_summary is None:
            msg = "repair_projections should not have been called"
            raise AssertionError(msg)
        return self._repair_summary

    def get_projection_readiness(self, *, sample_limit: int = 10) -> _ReportStub:
        self.sample_limits.append(sample_limit)
        return self._report

    def close(self) -> None:
        self.closed = True


def _args(*, repair: bool = False, dry_run: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        sample_limit=10,
        repair=repair,
        dry_run=dry_run,
        json=False,
    )


def test_run_readiness_check_returns_non_zero_when_not_ready(
    monkeypatch,
    capsys,
) -> None:
    report = _ReportStub(
        ready=False,
        orphan_relations=_IssueStub(count=1),
        missing_claim_participants=_IssueStub(count=0),
        missing_claim_evidence=_IssueStub(count=0),
        linked_relation_mismatches=_IssueStub(count=0),
        invalid_projection_relations=_IssueStub(count=0),
    )
    client = _ReadinessClientStub(report=report)
    monkeypatch.setattr(readiness_script, "_build_client", lambda args: client)

    exit_code = readiness_script.run_readiness_check(
        _args(),
    )

    assert exit_code == 1
    assert client.sample_limits == [10]
    assert client.closed is True
    output = capsys.readouterr().out
    assert "ready=False" in output
    assert "orphan_relations=1" in output


def test_run_readiness_check_repairs_and_returns_zero_when_ready(
    monkeypatch,
    capsys,
) -> None:
    report = _ReportStub(
        ready=True,
        orphan_relations=_IssueStub(count=0),
        missing_claim_participants=_IssueStub(count=0),
        missing_claim_evidence=_IssueStub(count=0),
        linked_relation_mismatches=_IssueStub(count=0),
        invalid_projection_relations=_IssueStub(count=0),
    )
    repair_summary = _RepairSummaryStub(
        participant_backfill={
            "scanned_claims": 1,
            "created_participants": 2,
            "skipped_existing": 0,
            "unresolved_endpoints": 0,
            "research_spaces": 1,
            "dry_run": False,
        },
        materialized_claims=1,
        detached_claims=0,
        unresolved_claims=0,
        dry_run=False,
    )
    client = _ReadinessClientStub(
        report=report,
        repair_summary=repair_summary,
    )

    monkeypatch.setattr(readiness_script, "_build_client", lambda args: client)

    exit_code = readiness_script.run_readiness_check(
        _args(repair=True, dry_run=False),
    )

    assert exit_code == 0
    assert client.repair_calls == [False]
    assert client.sample_limits == [10]
    assert client.closed is True
    output = capsys.readouterr().out
    assert "ready=True" in output
    assert "repair=dry_run=False materialized=1 detached=0 unresolved=0" in output
