"""Audit and optionally repair claim-backed projection readiness."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from src.database.session import SessionLocal, set_session_rls_context
from src.infrastructure.dependency_injection.service_factories import (
    ApplicationServiceFactoryMixin,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.orm import Session

    from src.application.services.kernel import KernelClaimProjectionReadinessService


class _ScriptServiceFactory(ApplicationServiceFactoryMixin):
    """Minimal service factory wrapper for operational scripts."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check global readiness for claim-backed canonical relation projections."
        ),
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Maximum number of sampled rows per readiness issue.",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Attempt automatic repair before evaluating final readiness.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="When combined with --repair, perform repair logic without committing.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args()


def _build_service(session: Session) -> KernelClaimProjectionReadinessService:
    factory = _ScriptServiceFactory()
    return factory.create_kernel_claim_projection_readiness_service(session)


def run_readiness_check(
    args: argparse.Namespace,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    with session_factory() as session:
        set_session_rls_context(
            session,
            has_phi_access=True,
            is_admin=True,
            bypass_rls=True,
        )
        service = _build_service(session)
        repair_summary = None
        if args.repair:
            repair_summary = service.repair_global(dry_run=args.dry_run)
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        report = service.audit(sample_limit=max(1, int(args.sample_limit)))

    payload = {
        "ready": report.ready,
        "orphan_relations": asdict(report.orphan_relations),
        "missing_claim_participants": asdict(report.missing_claim_participants),
        "missing_claim_evidence": asdict(report.missing_claim_evidence),
        "linked_relation_mismatches": asdict(report.linked_relation_mismatches),
        "invalid_projection_relations": asdict(report.invalid_projection_relations),
        "repair_summary": (
            asdict(repair_summary) if repair_summary is not None else None
        ),
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ready={payload['ready']}")
        for key in (
            "orphan_relations",
            "missing_claim_participants",
            "missing_claim_evidence",
            "linked_relation_mismatches",
            "invalid_projection_relations",
        ):
            issue = payload[key]
            print(f"{key}={issue['count']}")
            for sample in issue["samples"]:
                print(
                    "  - "
                    f"space={sample['research_space_id']} "
                    f"claim={sample['claim_id']} "
                    f"relation={sample['relation_id']} "
                    f"detail={sample['detail']}",
                )
        if payload["repair_summary"] is not None:
            repair = payload["repair_summary"]
            print(
                "repair="
                f"dry_run={repair['dry_run']} "
                f"materialized={repair['materialized_claims']} "
                f"detached={repair['detached_claims']} "
                f"unresolved={repair['unresolved_claims']}",
            )
    return 0 if report.ready else 1


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    args = _parse_args()
    return run_readiness_check(args)


if __name__ == "__main__":
    raise SystemExit(main())
