from __future__ import annotations

from pathlib import Path

from scripts import run_isolated_postgres_tests


def test_resolve_alembic_binary_prefers_current_interpreter_venv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    current_venv_bin = tmp_path / "current-venv" / "bin"
    current_venv_bin.mkdir(parents=True)
    python_executable = current_venv_bin / "python3"
    python_executable.touch()
    expected = current_venv_bin / "alembic"
    expected.touch()

    monkeypatch.setattr(run_isolated_postgres_tests, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(
        run_isolated_postgres_tests.sys,
        "executable",
        str(python_executable),
    )

    assert run_isolated_postgres_tests._resolve_alembic_binary() == str(expected)
