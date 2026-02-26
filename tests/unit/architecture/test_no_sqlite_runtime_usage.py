"""Architecture guard: runtime/local-dev paths must stay Postgres-first."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SQLITE_PATTERN = re.compile(r"\bsqlite(?:3)?\b|pysqlite|aiosqlite", re.IGNORECASE)

SCAN_TARGETS = (
    "src",
    "scripts",
    "Makefile",
    "README.md",
    "alembic.ini",
    "docker-compose.postgres.yml",
    ".env.postgres.example",
)
EXCLUDED_PATH_PARTS = {
    ".git",
    "__pycache__",
    ".next",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PATH_PARTS for part in path.parts) or any(
        part.endswith(".egg-info") for part in path.parts
    )


def _iter_scannable_files() -> list[Path]:
    files: list[Path] = []
    for target in SCAN_TARGETS:
        path = PROJECT_ROOT / target
        if path.is_file():
            if _is_excluded(path):
                continue
            files.append(path)
            continue
        if path.is_dir():
            files.extend(
                file_path
                for file_path in path.rglob("*")
                if file_path.is_file() and not _is_excluded(file_path)
            )
    return files


@pytest.mark.architecture
def test_runtime_and_local_dev_paths_do_not_reference_sqlite() -> None:
    """Prevent accidental fallback to SQLite in runtime/dev configuration paths."""
    violations: list[str] = []

    for file_path in _iter_scannable_files():
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            if SQLITE_PATTERN.search(line):
                relative_path = file_path.relative_to(PROJECT_ROOT)
                violations.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert (
        not violations
    ), "Found SQLite references in runtime/local-dev paths:\n" + "\n".join(violations)
