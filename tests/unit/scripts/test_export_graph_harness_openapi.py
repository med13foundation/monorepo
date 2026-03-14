from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from services.graph_harness_api.config import get_settings

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "export_graph_harness_openapi.py"
)


def test_export_graph_harness_openapi_writes_and_checks_schema(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "graph-harness-openapi.json"

    generate = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert generate.returncode == 0, generate.stderr
    contents = output_path.read_text(encoding="utf-8")
    assert '"/v1/spaces/{space_id}/agents/supervisor/runs"' in contents
    assert '"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages"' in contents
    document = json.loads(contents)
    assert document["info"]["version"] == get_settings().version

    check = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert check.returncode == 0, check.stderr


def test_export_graph_harness_openapi_check_fails_when_schema_is_stale(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "graph-harness-openapi.json"
    output_path.write_text('{"openapi":"stale"}\n', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--output", str(output_path), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Graph-harness-service OpenAPI schema is out of date" in result.stderr
