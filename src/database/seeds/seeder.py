"""
Dictionary Seeder — loads JSON seed files into kernel tables.

Run via: python -m src.database.seeds.seeder
Or from Makefile: make seed-dictionary
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).parent


def _load_json(filename: str) -> list[dict]:
    """Load a JSON seed file from the seeds directory."""
    path = SEEDS_DIR / filename
    if not path.exists():
        logger.warning("Seed file not found: %s", path)
        return []
    with path.open() as f:
        return json.load(f)


def seed_variable_definitions(session: Session) -> int:
    """Seed variable_definitions table."""
    rows = _load_json("genomics_variables.json")
    if not rows:
        return 0

    count = 0
    for row in rows:
        existing = session.execute(
            text("SELECT 1 FROM variable_definitions WHERE id = :id"),
            {"id": row["id"]},
        ).fetchone()
        if existing:
            continue

        session.execute(
            text(
                """
                INSERT INTO variable_definitions
                    (id, canonical_name, display_name, data_type,
                     preferred_unit, constraints, domain_context,
                     sensitivity, description)
                VALUES
                    (:id, :canonical_name, :display_name, :data_type,
                     :preferred_unit, :constraints, :domain_context,
                     :sensitivity, :description)
            """,
            ),
            {
                "id": row["id"],
                "canonical_name": row["canonical_name"],
                "display_name": row["display_name"],
                "data_type": row["data_type"],
                "preferred_unit": row.get("preferred_unit"),
                "constraints": json.dumps(row.get("constraints", {})),
                "domain_context": row.get("domain_context", "general"),
                "sensitivity": row.get("sensitivity", "INTERNAL"),
                "description": row.get("description"),
            },
        )
        count += 1

    session.commit()
    logger.info("Seeded %d variable definitions", count)
    return count


def seed_variable_synonyms(session: Session) -> int:
    """Seed variable_synonyms table."""
    rows = _load_json("variable_synonyms.json")
    if not rows:
        return 0

    count = 0
    for row in rows:
        existing = session.execute(
            text(
                "SELECT 1 FROM variable_synonyms "
                "WHERE variable_id = :vid AND synonym = :syn",
            ),
            {"vid": row["variable_id"], "syn": row["synonym"]},
        ).fetchone()
        if existing:
            continue

        session.execute(
            text(
                """
                INSERT INTO variable_synonyms (variable_id, synonym, source)
                VALUES (:variable_id, :synonym, :source)
            """,
            ),
            {
                "variable_id": row["variable_id"],
                "synonym": row["synonym"],
                "source": row.get("source"),
            },
        )
        count += 1

    session.commit()
    logger.info("Seeded %d variable synonyms", count)
    return count


def seed_entity_resolution_policies(session: Session) -> int:
    """Seed entity_resolution_policies table."""
    rows = _load_json("entity_types.json")
    if not rows:
        return 0

    count = 0
    for row in rows:
        existing = session.execute(
            text("SELECT 1 FROM entity_resolution_policies WHERE entity_type = :et"),
            {"et": row["entity_type"]},
        ).fetchone()
        if existing:
            continue

        session.execute(
            text(
                """
                INSERT INTO entity_resolution_policies
                    (entity_type, policy_strategy, required_anchors,
                     auto_merge_threshold)
                VALUES
                    (:entity_type, :policy_strategy, :required_anchors,
                     :auto_merge_threshold)
            """,
            ),
            {
                "entity_type": row["entity_type"],
                "policy_strategy": row["policy_strategy"],
                "required_anchors": json.dumps(row.get("required_anchors", [])),
                "auto_merge_threshold": row.get("auto_merge_threshold", 1.0),
            },
        )
        count += 1

    session.commit()
    logger.info("Seeded %d entity resolution policies", count)
    return count


def seed_relation_constraints(session: Session) -> int:
    """Seed relation_constraints table."""
    rows = _load_json("relation_constraints.json")
    if not rows:
        return 0

    count = 0
    for row in rows:
        existing = session.execute(
            text(
                "SELECT 1 FROM relation_constraints "
                "WHERE source_type = :st AND relation_type = :rt "
                "AND target_type = :tt",
            ),
            {
                "st": row["source_type"],
                "rt": row["relation_type"],
                "tt": row["target_type"],
            },
        ).fetchone()
        if existing:
            continue

        session.execute(
            text(
                """
                INSERT INTO relation_constraints
                    (source_type, relation_type, target_type,
                     is_allowed, requires_evidence)
                VALUES
                    (:source_type, :relation_type, :target_type,
                     :is_allowed, :requires_evidence)
            """,
            ),
            {
                "source_type": row["source_type"],
                "relation_type": row["relation_type"],
                "target_type": row["target_type"],
                "is_allowed": row.get("is_allowed", True),
                "requires_evidence": row.get("requires_evidence", True),
            },
        )
        count += 1

    session.commit()
    logger.info("Seeded %d relation constraints", count)
    return count


def seed_all(session: Session) -> dict[str, int]:
    """Run all seeders. Returns counts per table."""
    results = {
        "variable_definitions": seed_variable_definitions(session),
        "variable_synonyms": seed_variable_synonyms(session),
        "entity_resolution_policies": seed_entity_resolution_policies(session),
        "relation_constraints": seed_relation_constraints(session),
    }
    total = sum(results.values())
    logger.info("Dictionary seeding complete: %d total rows", total)
    return results


if __name__ == "__main__":
    import sys

    from src.database.session import get_engine, get_session_factory

    logging.basicConfig(level=logging.INFO)

    engine = get_engine()
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        results = seed_all(session)
        logger.info("Seeding results:")
        for table, count in results.items():
            logger.info("  %s: %d rows", table, count)
        logger.info("  TOTAL: %d rows", sum(results.values()))
        sys.exit(0)
