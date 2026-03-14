from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCKERFILE_PATH = REPO_ROOT / "services" / "graph_harness_api" / "Dockerfile"
DOCKERIGNORE_PATH = REPO_ROOT / ".dockerignore"
REQUIREMENTS_PATH = REPO_ROOT / "services" / "graph_harness_api" / "requirements.txt"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_graph_harness_container_keeps_separate_test_and_runtime_stages() -> None:
    """Regression: the Dockerfile must keep a dedicated pytest target."""
    dockerfile = _read_text(DOCKERFILE_PATH)

    assert "FROM python:3.13.11-slim AS base" in dockerfile
    assert "FROM base AS test" in dockerfile
    assert "FROM base AS runtime" in dockerfile
    assert dockerfile.index("FROM base AS test") < dockerfile.index(
        "FROM base AS runtime",
    )
    assert 'CMD ["pytest"]' in dockerfile
    assert 'CMD ["python", "-m", "services.graph_harness_api"]' in dockerfile


def test_graph_harness_test_stage_copies_subprocess_and_validator_inputs() -> None:
    """Regression: subprocess-driven tests need repo assets inside the image."""
    dockerfile = _read_text(DOCKERFILE_PATH)

    required_copy_lines = (
        "COPY architecture_overrides.json ./architecture_overrides.json",
        "COPY pytest.ini ./pytest.ini",
        "COPY src/web/types ./src/web/types",
        "COPY docs ./docs",
        "COPY scripts ./scripts",
        "COPY tests ./tests",
    )

    for copy_line in required_copy_lines:
        assert copy_line in dockerfile

    assert "PYTHONPATH=/app" in dockerfile
    assert 'pip install ".[dev]"' in dockerfile
    assert "ln -sf /usr/local/bin/alembic /app/venv/bin/alembic" in dockerfile


def test_graph_harness_container_installs_git_for_git_based_runtime_dependencies() -> (
    None
):
    """Regression: git-backed requirements need git available in the image."""
    dockerfile = _read_text(DOCKERFILE_PATH)
    requirements = _read_text(REQUIREMENTS_PATH)

    assert "git+" in requirements
    assert "apt-get install --yes --no-install-recommends git" in dockerfile


def test_dockerignore_reincludes_graph_harness_test_assets() -> None:
    """Regression: the build context must expose test-only assets to Docker."""
    dockerignore = _read_text(DOCKERIGNORE_PATH)

    assert "tests" in dockerignore
    assert "docs" in dockerignore
    assert "src/web" in dockerignore

    expected_reincludes = (
        "!tests/",
        "!tests/**",
        "!docs/",
        "!docs/**",
        "!src/web/types/",
        "!src/web/types/**",
    )

    for pattern in expected_reincludes:
        assert pattern in dockerignore
