"""Unit coverage for the operational claim projection readiness script."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from scripts import check_claim_projection_readiness as readiness_script

pytestmark = pytest.mark.graph


@dataclass(frozen=True)
class _IssueStub:
    count: int
    samples: tuple[object, ...] = ()


@dataclass(frozen=True)
class _ReportStub:
    ready: bool
    orphan_relations: _IssueStub
    missing_claim_participants: _IssueStub
    missing_claim_evidence: _IssueStub
    linked_relation_mismatches: _IssueStub
    invalid_projection_relations: _IssueStub


@dataclass(frozen=True)
class _RepairSummaryStub:
    participant_backfill: dict[str, object]
    materialized_claims: int
    detached_claims: int
    unresolved_claims: int
    dry_run: bool


class _ReadinessServiceStub:
    def __init__(
        self,
        *,
        report: _ReportStub,
        repair_summary: _RepairSummaryStub | None = None,
    ) -> None:
        self._report = report
        self._repair_summary = repair_summary
        self.repair_calls: list[bool] = []

    def repair_global(self, *, dry_run: bool) -> _RepairSummaryStub:
        self.repair_calls.append(dry_run)
        if self._repair_summary is None:
            msg = "repair_global should not have been called"
            raise AssertionError(msg)
        return self._repair_summary

    def audit(self, *, sample_limit: int = 10) -> _ReportStub:
        assert sample_limit == 10
        return self._report


class _SessionStub:
    committed: bool
    rolled_back: bool

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@contextmanager
def _session_factory() -> _SessionStub:
    yield _SessionStub()


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
    service = _ReadinessServiceStub(report=report)

    monkeypatch.setattr(readiness_script, "_build_service", lambda session: service)
    monkeypatch.setattr(
        readiness_script,
        "set_session_rls_context",
        lambda *args, **kwargs: None,
    )

    exit_code = readiness_script.run_readiness_check(
        _args(),
        session_factory=_session_factory,
    )

    assert exit_code == 1
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
    service = _ReadinessServiceStub(
        report=report,
        repair_summary=repair_summary,
    )

    monkeypatch.setattr(readiness_script, "_build_service", lambda session: service)
    monkeypatch.setattr(
        readiness_script,
        "set_session_rls_context",
        lambda *args, **kwargs: None,
    )

    exit_code = readiness_script.run_readiness_check(
        _args(repair=True, dry_run=False),
        session_factory=_session_factory,
    )

    assert exit_code == 0
    assert service.repair_calls == [False]
    output = capsys.readouterr().out
    assert "ready=True" in output
    assert "repair=dry_run=False materialized=1 detached=0 unresolved=0" in output
