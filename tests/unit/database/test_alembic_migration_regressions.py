"""Regression tests for Alembic migration compatibility behaviors."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_HEAD_REVISION = "006_queue_payload_refs"
LEGACY_REVISION_ALIAS = "004_relation_evidence_and_extraction_queue_contract"
ROLLOUT_MARKER_REVISION = "005_rel_evidence_rollout_marker"
RAW_STORAGE_KEY_VALUE = "raw/clinvar/variant-1001.json"
PAYLOAD_REF_VALUE = "payload://clinvar/variant-1001"


def _run_alembic_upgrade(*, database_url: str, revision: str) -> None:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    alembic_executable = which("alembic")
    if alembic_executable is None:
        msg = "alembic executable not found on PATH"
        raise RuntimeError(msg)
    subprocess.run(
        [alembic_executable, "upgrade", revision],
        check=True,
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_upgrade_head_remaps_legacy_revision_alias(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy_revision_alias.db'}"
    engine = create_engine(database_url, future=True)

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)",
            ),
        )
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES (:version_num)",
            ),
            {"version_num": LEGACY_REVISION_ALIAS},
        )

    _run_alembic_upgrade(database_url=database_url, revision="head")

    with engine.connect() as connection:
        versions = (
            connection.execute(
                text("SELECT version_num FROM alembic_version"),
            )
            .scalars()
            .all()
        )

    assert versions == [EXPECTED_HEAD_REVISION]


def test_006_backfills_extraction_queue_payload_reference_columns(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'queue_payload_ref_backfill.db'}"
    _run_alembic_upgrade(
        database_url=database_url,
        revision=ROLLOUT_MARKER_REVISION,
    )

    engine = create_engine(database_url, future=True)
    queued_at = datetime.now(UTC)
    queue_item_id = str(uuid4())

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO extraction_queue ("
                "id, publication_id, pubmed_id, source_type, source_record_id, "
                "source_id, ingestion_job_id, status, attempts, last_error, "
                "extraction_version, metadata_payload, queued_at, started_at, "
                "completed_at, updated_at"
                ") VALUES ("
                ":id, :publication_id, :pubmed_id, :source_type, :source_record_id, "
                ":source_id, :ingestion_job_id, :status, :attempts, :last_error, "
                ":extraction_version, :metadata_payload, :queued_at, :started_at, "
                ":completed_at, :updated_at"
                ")",
            ),
            {
                "id": queue_item_id,
                "publication_id": None,
                "pubmed_id": None,
                "source_type": "clinvar",
                "source_record_id": "clinvar:clinvar_id:1001",
                "source_id": str(uuid4()),
                "ingestion_job_id": str(uuid4()),
                "status": "pending",
                "attempts": 0,
                "last_error": None,
                "extraction_version": 1,
                "metadata_payload": json.dumps(
                    {
                        "raw_storage_key": RAW_STORAGE_KEY_VALUE,
                        "payload_ref": PAYLOAD_REF_VALUE,
                    },
                ),
                "queued_at": queued_at,
                "started_at": None,
                "completed_at": None,
                "updated_at": queued_at,
            },
        )

    _run_alembic_upgrade(
        database_url=database_url,
        revision=EXPECTED_HEAD_REVISION,
    )

    inspector = inspect(engine)
    column_names = {
        column["name"] for column in inspector.get_columns("extraction_queue")
    }
    assert "raw_storage_key" in column_names
    assert "payload_ref" in column_names

    with engine.connect() as connection:
        payload_columns = (
            connection.execute(
                text(
                    "SELECT raw_storage_key, payload_ref "
                    "FROM extraction_queue "
                    "WHERE id = :queue_item_id",
                ),
                {"queue_item_id": queue_item_id},
            )
            .mappings()
            .one()
        )

    assert payload_columns["raw_storage_key"] == RAW_STORAGE_KEY_VALUE
    assert payload_columns["payload_ref"] == PAYLOAD_REF_VALUE
