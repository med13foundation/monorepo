"""Contract checks for revision 022 run-id migration SQL intent."""

from __future__ import annotations

from pathlib import Path


def _migration_source() -> str:
    path = Path("alembic/versions/022_run_ids_as_text.py")
    return path.read_text(encoding="utf-8")


def test_022_upgrade_postgres_uses_explicit_text_casts() -> None:
    source = _migration_source()

    assert "USING enrichment_agent_run_id::text" in source
    assert "USING extraction_agent_run_id::text" in source
    assert "USING agent_run_id::text" in source
    assert "USING extraction_run_id::text" in source


def test_022_downgrade_postgres_documents_non_uuid_nulling() -> None:
    source = _migration_source()

    assert "Non-UUID run ids are intentionally nulled" in source
    assert "ELSE NULL" in source
    assert "ALTER COLUMN agent_run_id TYPE UUID" in source
    assert "ALTER COLUMN extraction_run_id TYPE UUID" in source
