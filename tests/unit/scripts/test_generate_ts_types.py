from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "generate_ts_types.py"


def test_generate_ts_types_supports_output_and_check(tmp_path: Path) -> None:
    output_path = tmp_path / "graph-service.generated.ts"

    generate = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--module",
            "src.type_definitions.graph_service_contracts",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert generate.returncode == 0, generate.stderr
    contents = output_path.read_text(encoding="utf-8")
    assert "export interface KernelRelationResponse" in contents
    assert "export interface HypothesisResponse" in contents

    check = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--module",
            "src.type_definitions.graph_service_contracts",
            "--output",
            str(output_path),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert check.returncode == 0, check.stderr


def test_generate_ts_types_check_fails_when_output_is_stale(tmp_path: Path) -> None:
    output_path = tmp_path / "graph-service.generated.ts"
    output_path.write_text("// stale\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--module",
            "src.type_definitions.graph_service_contracts",
            "--output",
            str(output_path),
            "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "TypeScript type output is out of date" in result.stderr


def test_generate_ts_types_skips_specialized_generic_interfaces(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "admin.generated.ts"

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--module",
            "src.routes.admin_routes.data_sources.schemas",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    contents = output_path.read_text(encoding="utf-8")
    assert "export interface PaginatedResponse<T = unknown>" in contents
    assert "export interface PaginatedResponse[DataSourceResponse]" not in contents
