"""Smoke tests for the graph-service Alembic history."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CURRENT_HEAD_REVISION = "022_entity_resolution_hardening"
_ALEMBIC_SUBPROCESS_TEMPLATE = """
import os
import sys

repo_root = os.environ["MED13_REPOSITORY_ROOT"]
normalized_repo_root = os.path.normcase(os.path.abspath(repo_root))

def _normalized(path: str) -> str:
    resolved = path if path else os.getcwd()
    return os.path.normcase(os.path.abspath(resolved))

sys.path = [
    path for path in sys.path
    if _normalized(path) != normalized_repo_root
]

from alembic.config import main

main(argv=["-c", "services/graph_api/alembic.ini", {command!r}, {revision!r}])
""".strip()


def _build_alembic_subprocess_command(*, command: str, revision: str) -> list[str]:
    script = _ALEMBIC_SUBPROCESS_TEMPLATE.format(
        command=command,
        revision=revision,
    )
    return [sys.executable, "-c", script]


def _run_alembic(*, database_url: str, command: str, revision: str) -> None:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    env["MED13_REPOSITORY_ROOT"] = str(REPOSITORY_ROOT)
    subprocess.run(
        _build_alembic_subprocess_command(command=command, revision=revision),
        check=True,
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_upgrade_head_creates_current_baseline_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'baseline_head.db'}"
    _run_alembic(database_url=database_url, command="upgrade", revision="head")

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

        assert {
            "relations",
            "relation_claims",
            "claim_participants",
            "claim_evidence",
            "relation_projection_sources",
            "reasoning_paths",
            "reasoning_path_steps",
            "graph_spaces",
            "graph_space_memberships",
            "graph_operation_runs",
            "entity_aliases",
            "entity_embeddings",
            "entity_relation_summary",
            "entity_claim_summary",
            "entity_neighbors",
            "pipeline_run_events",
            "harness_runs",
            "harness_run_intents",
            "harness_run_approvals",
            "harness_proposals",
            "harness_chat_sessions",
            "harness_chat_messages",
            "harness_schedules",
            "harness_research_state",
            "harness_graph_snapshots",
        }.issubset(table_names)
        assert "harness_run_artifacts" not in table_names
        assert "harness_run_workspaces" not in table_names
        assert "harness_run_progress" not in table_names
        assert "harness_run_events" not in table_names

        relation_columns = {
            column["name"] for column in inspector.get_columns("relation_evidence")
        }
        projection_columns = {
            column["name"]
            for column in inspector.get_columns("relation_projection_sources")
        }
        path_columns = {
            column["name"] for column in inspector.get_columns("reasoning_paths")
        }
        graph_space_columns = {
            column["name"] for column in inspector.get_columns("graph_spaces")
        }
        entity_columns = {
            column["name"] for column in inspector.get_columns("entities")
        }
        identifier_columns = {
            column["name"] for column in inspector.get_columns("entity_identifiers")
        }
        entity_alias_columns = {
            column["name"] for column in inspector.get_columns("entity_aliases")
        }

        assert {
            "evidence_sentence",
            "evidence_sentence_source",
            "evidence_sentence_confidence",
            "evidence_sentence_rationale",
            "agent_run_id",
            "source_document_ref",
        }.issubset(relation_columns)
        assert {
            "projection_origin",
            "research_space_id",
            "claim_id",
            "source_document_ref",
        }.issubset(
            projection_columns,
        )
        assert {"path_kind", "status", "path_signature_hash"}.issubset(path_columns)
        assert {
            "sync_source",
            "sync_fingerprint",
            "source_updated_at",
            "last_synced_at",
        }.issubset(graph_space_columns)
        assert "display_label_normalized" in entity_columns
        assert {
            "research_space_id",
            "identifier_normalized",
        }.issubset(identifier_columns)
        assert {
            "entity_id",
            "research_space_id",
            "entity_type",
            "alias_label",
            "alias_normalized",
            "is_active",
        }.issubset(entity_alias_columns)

        with engine.connect() as connection:
            versions = (
                connection.execute(text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert versions == [CURRENT_HEAD_REVISION]


def test_upgrade_head_and_downgrade_base_round_trip(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'baseline_round_trip.db'}"
    _run_alembic(database_url=database_url, command="upgrade", revision="head")
    _run_alembic(database_url=database_url, command="downgrade", revision="base")

    engine = create_engine(database_url, future=True)
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert "relations" not in table_names
    assert "relation_claims" not in table_names
    assert "relation_projection_sources" not in table_names
    assert "reasoning_paths" not in table_names


def test_fresh_upgrade_head_is_repeatable_from_clean_database(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'baseline_repeatable.db'}"
    _run_alembic(database_url=database_url, command="upgrade", revision="head")

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        pipeline_columns = {
            column["name"] for column in inspector.get_columns("pipeline_run_events")
        }
    finally:
        engine.dispose()

    assert {"created_at", "updated_at", "pipeline_run_id", "event_type"}.issubset(
        pipeline_columns,
    )


def test_upgrade_head_recovers_from_stale_baseline_version(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'baseline_stale_version.db'}"
    _run_alembic(
        database_url=database_url,
        command="upgrade",
        revision="002_reasoning_paths",
    )

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE alembic_version
                    SET version_num = '001_current_baseline'
                    """,
                ),
            )
    finally:
        engine.dispose()

    _run_alembic(database_url=database_url, command="upgrade", revision="head")

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert {"reasoning_paths", "reasoning_path_steps", "entity_aliases"}.issubset(
            table_names,
        )
        with engine.connect() as connection:
            versions = (
                connection.execute(text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert versions == [CURRENT_HEAD_REVISION]
