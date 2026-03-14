#!/usr/bin/env python3
"""Export the standalone graph-harness-service OpenAPI schema."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the standalone graph-harness-service OpenAPI schema.",
    )
    parser.add_argument(
        "--output",
        default="services/graph_harness_api/openapi.json",
        help="Destination path for the rendered OpenAPI document.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the exported schema differs from the current file.",
    )
    return parser.parse_args()


def render_openapi_document() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.append(str(repo_root))
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg2://med13_dev:med13_dev_password@localhost:5432/med13_dev",
    )
    os.environ.setdefault("GRAPH_API_URL", "http://127.0.0.1:8080")

    from services.graph_harness_api.app import create_app

    document = create_app().openapi()
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    args = _parse_args()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    display_path = (
        output_path.relative_to(repo_root)
        if output_path.is_relative_to(repo_root)
        else output_path
    )

    rendered = render_openapi_document()
    if args.check:
        current = (
            output_path.read_text(encoding="utf-8") if output_path.exists() else None
        )
        if current != rendered:
            msg = (
                "Graph-harness-service OpenAPI schema is out of date. "
                f"Run scripts/export_graph_harness_openapi.py --output {display_path}"
            )
            raise SystemExit(msg)
        print(  # noqa: T201
            f"✅ Graph-harness-service OpenAPI is up to date at {display_path}",
        )
        return

    output_path.write_text(rendered, encoding="utf-8")
    print(f"✅ Wrote graph-harness-service OpenAPI to {display_path}")  # noqa: T201


if __name__ == "__main__":
    main()
