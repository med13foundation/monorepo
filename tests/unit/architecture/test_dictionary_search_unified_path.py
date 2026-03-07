"""Architecture guard: dictionary repository search must stay behind the harness."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
ALLOWED_DIRECT_CALLERS: frozenset[str] = frozenset(
    {
        "src/infrastructure/llm/adapters/deterministic_dictionary_search_harness_adapter.py",
        "src/infrastructure/llm/adapters/dictionary_search_harness_adapter.py",
    },
)


@pytest.mark.architecture
def test_repository_search_dictionary_is_only_called_by_harness() -> None:
    violations: list[str] = []
    for file_path in SRC_ROOT.rglob("*.py"):
        relative_path = file_path.relative_to(PROJECT_ROOT).as_posix()
        if relative_path in ALLOWED_DIRECT_CALLERS:
            continue
        content = file_path.read_text(encoding="utf-8")
        for line_number, line in enumerate(content.splitlines(), start=1):
            if ".search_dictionary(" not in line:
                continue
            violations.append(f"{relative_path}:{line_number}")

    assert not violations, (
        "Direct repository dictionary search calls found outside the unified harness:\n"
        + "\n".join(violations)
    )
