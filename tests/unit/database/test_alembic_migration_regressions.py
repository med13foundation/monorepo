"""Regression tests for Alembic migration compatibility behaviors."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_HEAD_REVISION = "016_enable_kernel_rls"
PRE_VERSIONING_REVISION = "013_dictionary_embeddings"
PRE_TRANSFORM_UPGRADE_REVISION = "014_dict_version_validity"
PRE_RLS_REVISION = "015_dict_transforms_upgrade"
LEGACY_REVISION_ALIAS = "004_relation_evidence_and_extraction_queue_contract"
ROLLOUT_MARKER_REVISION = "005_rel_evidence_rollout_marker"
RAW_STORAGE_KEY_VALUE = "raw/clinvar/variant-1001.json"
PAYLOAD_REF_VALUE = "payload://clinvar/variant-1001"


def _run_alembic_upgrade(*, database_url: str, revision: str) -> None:
    env = dict(os.environ)
    env["ALEMBIC_DATABASE_URL"] = database_url
    venv_alembic = Path(sys.executable).with_name("alembic")
    command = [str(venv_alembic), "upgrade", revision]
    if not venv_alembic.exists():
        fallback_alembic = which("alembic")
        if fallback_alembic is None:
            msg = "alembic executable not found on PATH"
            raise RuntimeError(msg)
        command = [fallback_alembic, "upgrade", revision]
    subprocess.run(
        command,
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
    queued_at_iso = datetime.now(UTC).isoformat()
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
                "queued_at": queued_at_iso,
                "started_at": None,
                "completed_at": None,
                "updated_at": queued_at_iso,
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


def test_013_creates_dictionary_dimension_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'dictionary_type_tables.db'}"
    _run_alembic_upgrade(database_url=database_url, revision=EXPECTED_HEAD_REVISION)

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert "dictionary_changelog" in table_names
    assert "dictionary_data_types" in table_names
    assert "dictionary_domain_contexts" in table_names
    assert "dictionary_sensitivity_levels" in table_names
    assert "dictionary_entity_types" in table_names
    assert "dictionary_relation_types" in table_names
    assert "value_sets" in table_names
    assert "value_set_items" in table_names

    variable_fk_targets = {
        fk["referred_table"]
        for fk in inspector.get_foreign_keys("variable_definitions")
    }
    assert "dictionary_data_types" in variable_fk_targets
    assert "dictionary_domain_contexts" in variable_fk_targets
    assert "dictionary_sensitivity_levels" in variable_fk_targets

    policy_fk_targets = {
        fk["referred_table"]
        for fk in inspector.get_foreign_keys("entity_resolution_policies")
    }
    assert "dictionary_entity_types" in policy_fk_targets

    relation_fk_targets = {
        fk["referred_table"]
        for fk in inspector.get_foreign_keys("relation_constraints")
    }
    assert "dictionary_entity_types" in relation_fk_targets
    assert "dictionary_relation_types" in relation_fk_targets

    value_set_fk_targets = {
        fk["referred_table"] for fk in inspector.get_foreign_keys("value_sets")
    }
    assert "variable_definitions" in value_set_fk_targets

    value_set_item_fk_targets = {
        fk["referred_table"] for fk in inspector.get_foreign_keys("value_set_items")
    }
    assert "value_sets" in value_set_item_fk_targets

    variable_columns = {
        column["name"] for column in inspector.get_columns("variable_definitions")
    }
    assert "description_embedding" in variable_columns
    assert "embedded_at" in variable_columns
    assert "embedding_model" in variable_columns

    entity_type_columns = {
        column["name"] for column in inspector.get_columns("dictionary_entity_types")
    }
    assert "embedded_at" in entity_type_columns
    assert "embedding_model" in entity_type_columns

    relation_type_columns = {
        column["name"] for column in inspector.get_columns("dictionary_relation_types")
    }
    assert "embedded_at" in relation_type_columns
    assert "embedding_model" in relation_type_columns


def test_014_backfills_versioning_and_constraints(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'dictionary_versioning_validity.db'}"
    _run_alembic_upgrade(
        database_url=database_url,
        revision=PRE_VERSIONING_REVISION,
    )

    engine = create_engine(database_url, future=True)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO dictionary_data_types
                    (id, display_name, python_type_hint, description, constraint_schema)
                VALUES
                    ('STRING', 'String', 'str', 'String values', '{}')
                """,
            ),
        )
        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO dictionary_domain_contexts
                    (id, display_name, description)
                VALUES
                    ('general', 'General', 'General domain context')
                """,
            ),
        )
        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO dictionary_sensitivity_levels
                    (id, display_name, description)
                VALUES
                    ('INTERNAL', 'Internal', 'Internal sensitivity level')
                """,
            ),
        )
        connection.execute(
            text(
                """
                INSERT INTO variable_definitions
                    (id, canonical_name, display_name, data_type, constraints,
                     domain_context, sensitivity, created_by, review_status)
                VALUES
                    ('VAR_VERSIONING_ACTIVE', 'versioning_active', 'Versioning Active',
                     'STRING', '{}', 'general', 'INTERNAL', 'seed', 'ACTIVE')
                """,
            ),
        )
        connection.execute(
            text(
                """
                INSERT INTO variable_definitions
                    (id, canonical_name, display_name, data_type, constraints,
                     domain_context, sensitivity, created_by, review_status,
                     reviewed_at, revocation_reason)
                VALUES
                    ('VAR_VERSIONING_REVOKED', 'versioning_revoked', 'Versioning Revoked',
                     'STRING', '{}', 'general', 'INTERNAL', 'seed', 'REVOKED',
                     CURRENT_TIMESTAMP, 'legacy revoked row')
                """,
            ),
        )

    _run_alembic_upgrade(database_url=database_url, revision=EXPECTED_HEAD_REVISION)

    inspector = inspect(engine)
    variable_columns = {
        column["name"] for column in inspector.get_columns("variable_definitions")
    }
    assert "is_active" in variable_columns
    assert "valid_from" in variable_columns
    assert "valid_to" in variable_columns
    assert "superseded_by" in variable_columns

    domain_columns = {
        column["name"] for column in inspector.get_columns("dictionary_domain_contexts")
    }
    assert "is_active" in domain_columns
    assert "valid_from" in domain_columns
    assert "valid_to" in domain_columns
    assert "superseded_by" in domain_columns

    sensitivity_columns = {
        column["name"]
        for column in inspector.get_columns("dictionary_sensitivity_levels")
    }
    assert "is_active" in sensitivity_columns
    assert "valid_from" in sensitivity_columns
    assert "valid_to" in sensitivity_columns
    assert "superseded_by" in sensitivity_columns

    variable_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("variable_definitions")
    }
    assert any(
        "ck_variable_definitions_active_validity" in constraint_name
        for constraint_name in variable_constraints
    )

    domain_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("dictionary_domain_contexts")
    }
    assert any(
        "ck_dictionary_domain_contexts_active_validity" in constraint_name
        for constraint_name in domain_constraints
    )

    sensitivity_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "dictionary_sensitivity_levels",
        )
    }
    assert any(
        "ck_dictionary_sensitivity_levels_active_validity" in constraint_name
        for constraint_name in sensitivity_constraints
    )

    with engine.connect() as connection:
        active_row = (
            connection.execute(
                text(
                    """
                SELECT is_active, valid_from, valid_to
                FROM variable_definitions
                WHERE id = 'VAR_VERSIONING_ACTIVE'
                """,
                ),
            )
            .mappings()
            .one()
        )
        revoked_row = (
            connection.execute(
                text(
                    """
                SELECT is_active, valid_from, valid_to
                FROM variable_definitions
                WHERE id = 'VAR_VERSIONING_REVOKED'
                """,
                ),
            )
            .mappings()
            .one()
        )
        domain_row = (
            connection.execute(
                text(
                    """
                SELECT is_active, valid_from, valid_to
                FROM dictionary_domain_contexts
                WHERE id = 'general'
                """,
                ),
            )
            .mappings()
            .one()
        )
        sensitivity_row = (
            connection.execute(
                text(
                    """
                SELECT is_active, valid_from, valid_to
                FROM dictionary_sensitivity_levels
                WHERE id = 'INTERNAL'
                """,
                ),
            )
            .mappings()
            .one()
        )

    assert bool(active_row["is_active"]) is True
    assert active_row["valid_from"] is not None
    assert active_row["valid_to"] is None

    assert bool(revoked_row["is_active"]) is False
    assert revoked_row["valid_from"] is not None
    assert revoked_row["valid_to"] is not None

    assert bool(domain_row["is_active"]) is True
    assert domain_row["valid_from"] is not None
    assert domain_row["valid_to"] is None

    assert bool(sensitivity_row["is_active"]) is True
    assert sensitivity_row["valid_from"] is not None
    assert sensitivity_row["valid_to"] is None


def test_015_adds_transform_upgrade_columns(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'dictionary_transform_upgrade.db'}"
    _run_alembic_upgrade(
        database_url=database_url,
        revision=PRE_TRANSFORM_UPGRADE_REVISION,
    )

    engine = create_engine(database_url, future=True)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO transform_registry
                    (id, input_unit, output_unit, implementation_ref, status, created_by)
                VALUES
                    (
                        'TR_TEST_MG_TO_G',
                        'mg',
                        'g',
                        'func:std_lib.convert.mg_to_g',
                        'ACTIVE',
                        'seed'
                    )
                """,
            ),
        )

    _run_alembic_upgrade(database_url=database_url, revision=EXPECTED_HEAD_REVISION)

    inspector = inspect(engine)
    transform_columns = {
        column["name"] for column in inspector.get_columns("transform_registry")
    }
    assert "category" in transform_columns
    assert "input_data_type" in transform_columns
    assert "output_data_type" in transform_columns
    assert "is_deterministic" in transform_columns
    assert "is_production_allowed" in transform_columns
    assert "test_input" in transform_columns
    assert "expected_output" in transform_columns
    assert "description" in transform_columns

    with engine.connect() as connection:
        transform_row = (
            connection.execute(
                text(
                    """
                    SELECT
                        category,
                        is_deterministic,
                        is_production_allowed,
                        test_input,
                        expected_output,
                        description
                    FROM transform_registry
                    WHERE id = 'TR_TEST_MG_TO_G'
                    """,
                ),
            )
            .mappings()
            .one()
        )

    assert transform_row["category"] == "UNIT_CONVERSION"
    assert bool(transform_row["is_deterministic"]) is True
    assert bool(transform_row["is_production_allowed"]) is False
    assert transform_row["test_input"] is None
    assert transform_row["expected_output"] is None
    assert transform_row["description"] is None


def test_016_rls_migration_is_safe_on_sqlite(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'kernel_rls_sqlite_compat.db'}"
    _run_alembic_upgrade(
        database_url=database_url,
        revision=PRE_RLS_REVISION,
    )
    _run_alembic_upgrade(database_url=database_url, revision=EXPECTED_HEAD_REVISION)

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())
    assert "entities" in table_names
    assert "entity_identifiers" in table_names
    assert "observations" in table_names
    assert "relations" in table_names
    assert "relation_evidence" in table_names
    assert "provenance" in table_names
