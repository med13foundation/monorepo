from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def test_fastapi_concurrency_guardrails_pass() -> None:
    validator_script = PROJECT_ROOT / "scripts" / "validate_architecture.py"
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(validator_script)],
        check=False,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr
    assert "async_route_no_await" not in output
    assert "async_sync_hot_path_call" not in output
