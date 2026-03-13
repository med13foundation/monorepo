"""Unit coverage for the graph-space reconciliation script."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from uuid import uuid4

import pytest

from scripts import sync_graph_spaces as sync_script

pytestmark = pytest.mark.graph


@dataclass(frozen=True)
class _SummaryStub:
    total_spaces: int
    synced_space_ids: tuple[object, ...]
    statuses: tuple[str, ...]
    batch_size: int


class _SyncServiceStub:
    def __init__(self, summary: _SummaryStub) -> None:
        self.summary = summary
        self.calls: list[dict[str, object]] = []

    def sync_spaces(
        self,
        *,
        space_id,
        statuses,
        batch_size,
    ) -> _SummaryStub:
        self.calls.append(
            {
                "space_id": space_id,
                "statuses": statuses,
                "batch_size": batch_size,
            },
        )
        return self.summary


def _args(
    *,
    space_id: str | None = None,
    status: list[str] | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        space_id=space_id,
        status=status,
        batch_size=25,
        json=False,
    )


def test_run_sync_prints_bulk_summary(monkeypatch, capsys) -> None:
    summary = _SummaryStub(
        total_spaces=2,
        synced_space_ids=(uuid4(), uuid4()),
        statuses=("active", "archived"),
        batch_size=25,
    )
    service = _SyncServiceStub(summary)
    monkeypatch.setattr(sync_script, "_build_service", lambda: service)

    exit_code = sync_script.run_sync(_args(status=["active", "archived"]))

    assert exit_code == 0
    assert service.calls == [
        {
            "space_id": None,
            "statuses": sync_script._parse_statuses(["active", "archived"]),
            "batch_size": 25,
        },
    ]
    output = capsys.readouterr().out
    assert "spaces=2 statuses=active,archived batch_size=25" in output


def test_run_sync_parses_single_space_id(monkeypatch) -> None:
    requested_space_id = uuid4()
    summary = _SummaryStub(
        total_spaces=1,
        synced_space_ids=(requested_space_id,),
        statuses=("active",),
        batch_size=25,
    )
    service = _SyncServiceStub(summary)
    monkeypatch.setattr(sync_script, "_build_service", lambda: service)

    exit_code = sync_script.run_sync(_args(space_id=str(requested_space_id)))

    assert exit_code == 0
    assert service.calls[0]["space_id"] == requested_space_id
    assert service.calls[0]["statuses"] == (
        sync_script.SpaceStatus.ACTIVE,
        sync_script.SpaceStatus.INACTIVE,
        sync_script.SpaceStatus.ARCHIVED,
        sync_script.SpaceStatus.SUSPENDED,
    )
