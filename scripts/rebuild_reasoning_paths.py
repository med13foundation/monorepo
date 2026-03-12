"""Rebuild persisted derived reasoning paths."""

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

    from src.application.services.kernel import KernelReasoningPathService


class _ScriptServiceFactory(ApplicationServiceFactoryMixin):
    """Minimal service factory wrapper for operational scripts."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild derived reasoning paths from grounded claim chains.",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        default=None,
        help="Optional research space ID to rebuild. Rebuild all spaces when omitted.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Maximum number of claim-relation edges per persisted path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args()


def _build_service(session: Session) -> KernelReasoningPathService:
    factory = _ScriptServiceFactory()
    return factory.create_kernel_reasoning_path_service(session)


def run_rebuild(
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
        if args.space_id:
            summaries = [
                service.rebuild_for_space(
                    args.space_id,
                    max_depth=max(1, min(4, int(args.max_depth))),
                    replace_existing=True,
                ),
            ]
        else:
            summaries = service.rebuild_global(
                max_depth=max(1, min(4, int(args.max_depth))),
            )
        session.commit()

    payload = [asdict(summary) for summary in summaries]
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for summary in payload:
            print(
                "space="
                f"{summary['research_space_id']} "
                f"eligible_claims={summary['eligible_claims']} "
                f"accepted_claim_relations={summary['accepted_claim_relations']} "
                f"rebuilt_paths={summary['rebuilt_paths']} "
                f"max_depth={summary['max_depth']}",
            )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    args = _parse_args()
    return run_rebuild(args)


if __name__ == "__main__":
    raise SystemExit(main())
