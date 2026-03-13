"""Contract checks for baseline run-id column types."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _run_alembic_upgrade(*, database_url: str) -> None:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    subprocess.run(
        [
            REPOSITORY_ROOT.joinpath("venv", "bin", "alembic").as_posix(),
            "-c",
            REPOSITORY_ROOT.joinpath(
                "services",
                "graph_api",
                "alembic.ini",
            ).as_posix(),
            "upgrade",
            "head",
        ],
        check=True,
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_baseline_upgrade_stores_source_document_run_ids_as_text(
    tmp_path: Path,
) -> None:
    database_url = (
        f"sqlite:///{tmp_path / 'baseline_run_id_columns_source_documents.db'}"
    )
    _run_alembic_upgrade(database_url=database_url)

    inspector = inspect(create_engine(database_url, future=True))
    source_document_columns = {
        column["name"]: str(column["type"]).upper()
        for column in inspector.get_columns("source_documents")
    }

    assert source_document_columns["enrichment_agent_run_id"].startswith(
        ("VARCHAR", "TEXT"),
    )
    assert source_document_columns["extraction_agent_run_id"].startswith(
        ("VARCHAR", "TEXT"),
    )


def test_baseline_upgrade_stores_relation_and_provenance_run_ids_as_text(
    tmp_path: Path,
) -> None:
    database_url = (
        f"sqlite:///{tmp_path / 'baseline_run_id_columns_relation_provenance.db'}"
    )
    _run_alembic_upgrade(database_url=database_url)

    inspector = inspect(create_engine(database_url, future=True))
    relation_evidence_columns = {
        column["name"]: str(column["type"]).upper()
        for column in inspector.get_columns("relation_evidence")
    }
    provenance_columns = {
        column["name"]: str(column["type"]).upper()
        for column in inspector.get_columns("provenance")
    }

    assert relation_evidence_columns["agent_run_id"].startswith(("VARCHAR", "TEXT"))
    assert provenance_columns["extraction_run_id"].startswith(("VARCHAR", "TEXT"))
