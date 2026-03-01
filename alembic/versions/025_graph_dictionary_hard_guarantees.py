"""Enforce hard dictionary integrity guarantees for graph writes.

Revision ID: 025_graph_dict_hard_guarantees
Revises: 024_claim_first_orchestration
Create Date: 2026-02-27
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "025_graph_dict_hard_guarantees"
down_revision = "024_claim_first_orchestration"
branch_labels = None
depends_on = None

_RELATION_SYNONYMS_TABLE = "dictionary_relation_synonyms"

_RELATION_SYNONYM_SEEDS: tuple[tuple[str, str, str], ...] = (
    ("MENTIONS", "MENTIONS_GENE", "seed:legacy_alias"),
    ("MENTIONS", "MENTIONS_PROTEIN", "seed:legacy_alias"),
    ("MENTIONS", "MENTIONS_VARIANT", "seed:legacy_alias"),
    ("MENTIONS", "MENTIONS_PHENOTYPE", "seed:legacy_alias"),
    ("MENTIONS", "MENTIONS_DISEASE", "seed:legacy_alias"),
    ("MENTIONS", "MENTIONS_DRUG", "seed:legacy_alias"),
    ("HAS_AUTHOR", "AUTHORED_BY", "seed:legacy_alias"),
    ("HAS_AUTHOR", "WRITTEN_BY", "seed:legacy_alias"),
    ("HAS_KEYWORD", "HAS_MESH_TERM", "seed:legacy_alias"),
    ("HAS_KEYWORD", "TAGGED_WITH", "seed:legacy_alias"),
)


def upgrade() -> None:
    _create_relation_synonyms_table()
    _seed_relation_synonyms()
    _normalize_existing_graph_type_values()
    _collapse_alias_relation_duplicates()
    _rewrite_relations_to_canonical_types()
    _validate_no_orphan_graph_type_values()
    _add_graph_constraints()
    _create_integrity_functions()
    _create_integrity_triggers()
    _validate_existing_graph_rows()


def downgrade() -> None:
    _drop_integrity_triggers()
    _drop_integrity_functions()
    _drop_graph_constraints()
    _drop_relation_synonyms_table()


def _create_relation_synonyms_table() -> None:
    if _has_table(_RELATION_SYNONYMS_TABLE):
        return

    op.create_table(
        _RELATION_SYNONYMS_TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "relation_type",
            sa.String(length=64),
            sa.ForeignKey("dictionary_relation_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("synonym", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column(
            "created_by",
            sa.String(length=128),
            nullable=False,
            server_default="seed",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "valid_from",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_dictionary_relation_synonyms_active_validity",
        ),
    )

    op.create_index(
        "idx_rel_syn_relation_type",
        _RELATION_SYNONYMS_TABLE,
        ["relation_type"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_relation_synonyms_active_synonym",
            _RELATION_SYNONYMS_TABLE,
            [sa.text("lower(synonym)")],
            unique=True,
            postgresql_where=sa.text("is_active"),
        )
    else:
        op.create_index(
            "uq_relation_synonyms_active_synonym",
            _RELATION_SYNONYMS_TABLE,
            [sa.text("lower(synonym)")],
            unique=True,
        )


def _seed_relation_synonyms() -> None:
    if not _has_table(_RELATION_SYNONYMS_TABLE):
        return

    bind = op.get_bind()
    for relation_type, synonym, source in _RELATION_SYNONYM_SEEDS:
        bind.execute(
            sa.text(
                """
                INSERT INTO dictionary_relation_synonyms
                    (relation_type, synonym, source, created_by, review_status)
                SELECT
                    :relation_type,
                    :synonym,
                    :source,
                    'seed',
                    'ACTIVE'
                WHERE EXISTS (
                    SELECT 1
                    FROM dictionary_relation_types rt
                    WHERE rt.id = :relation_type
                )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM dictionary_relation_synonyms rs
                    WHERE lower(rs.synonym) = lower(:synonym)
                      AND rs.is_active IS TRUE
                  )
                """,
            ),
            {
                "relation_type": relation_type,
                "synonym": synonym,
                "source": source,
            },
        )


def _normalize_existing_graph_type_values() -> None:
    if _has_table("entities"):
        op.execute(
            sa.text(
                "UPDATE entities SET entity_type = upper(btrim(entity_type)) WHERE entity_type IS NOT NULL",
            ),
        )
    if _has_table("relations"):
        op.execute(
            sa.text(
                "UPDATE relations SET relation_type = upper(btrim(relation_type)) WHERE relation_type IS NOT NULL",
            ),
        )


def _rewrite_relations_to_canonical_types() -> None:
    if not _has_table("relations") or not _has_table(_RELATION_SYNONYMS_TABLE):
        return

    op.execute(
        sa.text(
            """
            UPDATE relations AS rel
            SET relation_type = syn.relation_type
            FROM dictionary_relation_synonyms AS syn
            JOIN dictionary_relation_types AS rt
              ON rt.id = syn.relation_type
            WHERE rel.relation_type = syn.synonym
              AND syn.is_active IS TRUE
              AND syn.review_status = 'ACTIVE'
              AND rt.is_active IS TRUE
              AND rt.review_status = 'ACTIVE'
            """,
        ),
    )


def _collapse_alias_relation_duplicates() -> None:
    if not _has_table("relations") or not _has_table(_RELATION_SYNONYMS_TABLE):
        return

    op.execute(
        sa.text(
            """
            WITH duplicate_pairs AS (
                SELECT
                    alias_rel.id AS alias_relation_id,
                    canonical_rel.id AS canonical_relation_id
                FROM relations AS alias_rel
                JOIN dictionary_relation_synonyms AS syn
                  ON syn.synonym = alias_rel.relation_type
                 AND syn.is_active IS TRUE
                 AND syn.review_status = 'ACTIVE'
                JOIN relations AS canonical_rel
                  ON canonical_rel.research_space_id = alias_rel.research_space_id
                 AND canonical_rel.source_id = alias_rel.source_id
                 AND canonical_rel.target_id = alias_rel.target_id
                 AND canonical_rel.relation_type = syn.relation_type
            )
            UPDATE relation_evidence AS re
               SET relation_id = dp.canonical_relation_id
            FROM duplicate_pairs AS dp
            WHERE re.relation_id = dp.alias_relation_id
            """,
        ),
    )

    op.execute(
        sa.text(
            """
            WITH duplicate_pairs AS (
                SELECT alias_rel.id AS alias_relation_id
                FROM relations AS alias_rel
                JOIN dictionary_relation_synonyms AS syn
                  ON syn.synonym = alias_rel.relation_type
                 AND syn.is_active IS TRUE
                 AND syn.review_status = 'ACTIVE'
                JOIN relations AS canonical_rel
                  ON canonical_rel.research_space_id = alias_rel.research_space_id
                 AND canonical_rel.source_id = alias_rel.source_id
                 AND canonical_rel.target_id = alias_rel.target_id
                 AND canonical_rel.relation_type = syn.relation_type
            )
            DELETE FROM relations AS rel
            USING duplicate_pairs AS dp
            WHERE rel.id = dp.alias_relation_id
            """,
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE relations AS rel
               SET source_count = agg.source_count,
                   aggregate_confidence = agg.aggregate_confidence,
                   highest_evidence_tier = agg.highest_evidence_tier,
                   updated_at = now()
            FROM (
                SELECT
                    re.relation_id,
                    count(*)::int AS source_count,
                    LEAST(
                        GREATEST(
                            1 - EXP(
                                SUM(
                                    LN(
                                        GREATEST(
                                            1e-12,
                                            1 - LEAST(GREATEST(re.confidence, 0), 1)
                                        )
                                    )
                                )
                            ),
                            0
                        ),
                        1
                    ) AS aggregate_confidence,
                    (ARRAY_AGG(
                        upper(re.evidence_tier) ORDER BY
                            CASE upper(re.evidence_tier)
                                WHEN 'EXPERT_CURATED' THEN 6
                                WHEN 'CLINICAL' THEN 5
                                WHEN 'EXPERIMENTAL' THEN 4
                                WHEN 'LITERATURE' THEN 3
                                WHEN 'STRUCTURED_DATA' THEN 2
                                WHEN 'COMPUTATIONAL' THEN 1
                                ELSE 0
                            END DESC
                    ))[1] AS highest_evidence_tier
                FROM relation_evidence AS re
                GROUP BY re.relation_id
            ) AS agg
            WHERE rel.id = agg.relation_id
            """,
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE relations AS rel
               SET source_count = 0,
                   aggregate_confidence = 0,
                   highest_evidence_tier = NULL,
                   updated_at = now()
            WHERE NOT EXISTS (
                SELECT 1
                FROM relation_evidence AS re
                WHERE re.relation_id = rel.id
            )
            """,
        ),
    )


def _validate_no_orphan_graph_type_values() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if _has_table("entities"):
        op.execute(
            """
            DO $$
            DECLARE
                v_count INTEGER;
                v_example TEXT;
            BEGIN
                SELECT count(*),
                       string_agg(entity_type, ', ' ORDER BY entity_type)
                  INTO v_count, v_example
                FROM (
                    SELECT DISTINCT e.entity_type
                    FROM entities e
                    LEFT JOIN dictionary_entity_types det
                      ON det.id = e.entity_type
                    WHERE det.id IS NULL
                    ORDER BY e.entity_type
                    LIMIT 10
                ) missing;

                IF v_count > 0 THEN
                    RAISE EXCEPTION
                        'Cannot enforce entities.entity_type FK; missing dictionary_entity_types entries. Examples: %',
                        COALESCE(v_example, '<none>');
                END IF;
            END $$;
            """,
        )

    if _has_table("relations"):
        op.execute(
            """
            DO $$
            DECLARE
                v_count INTEGER;
                v_example TEXT;
            BEGIN
                SELECT count(*),
                       string_agg(relation_type, ', ' ORDER BY relation_type)
                  INTO v_count, v_example
                FROM (
                    SELECT DISTINCT r.relation_type
                    FROM relations r
                    LEFT JOIN dictionary_relation_types drt
                      ON drt.id = r.relation_type
                    WHERE drt.id IS NULL
                    ORDER BY r.relation_type
                    LIMIT 10
                ) missing;

                IF v_count > 0 THEN
                    RAISE EXCEPTION
                        'Cannot enforce relations.relation_type FK; missing dictionary_relation_types entries. Examples: %',
                        COALESCE(v_example, '<none>');
                END IF;
            END $$;
            """,
        )


def _add_graph_constraints() -> None:
    if _has_table("entities"):
        if not _has_unique_constraint("entities", "uq_entities_id_space"):
            op.create_unique_constraint(
                "uq_entities_id_space",
                "entities",
                ["id", "research_space_id"],
            )
        if not _has_foreign_key("entities", "fk_entities_entity_type_dictionary"):
            op.create_foreign_key(
                "fk_entities_entity_type_dictionary",
                "entities",
                "dictionary_entity_types",
                ["entity_type"],
                ["id"],
            )

    if _has_table("relations") and _has_table("entities"):
        if not _has_foreign_key("relations", "fk_relations_relation_type_dictionary"):
            op.create_foreign_key(
                "fk_relations_relation_type_dictionary",
                "relations",
                "dictionary_relation_types",
                ["relation_type"],
                ["id"],
            )
        if not _has_foreign_key("relations", "fk_relations_source_space_entities"):
            op.create_foreign_key(
                "fk_relations_source_space_entities",
                "relations",
                "entities",
                ["source_id", "research_space_id"],
                ["id", "research_space_id"],
                ondelete="CASCADE",
            )
        if not _has_foreign_key("relations", "fk_relations_target_space_entities"):
            op.create_foreign_key(
                "fk_relations_target_space_entities",
                "relations",
                "entities",
                ["target_id", "research_space_id"],
                ["id", "research_space_id"],
                ondelete="CASCADE",
            )


def _create_integrity_functions() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_normalize_and_validate_entity_type()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.entity_type := upper(btrim(NEW.entity_type));
            IF NEW.entity_type IS NULL OR NEW.entity_type = '' THEN
                RAISE EXCEPTION 'entity_type is required';
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM dictionary_entity_types det
                WHERE det.id = NEW.entity_type
                  AND det.is_active IS TRUE
                  AND det.review_status = 'ACTIVE'
            ) THEN
                RAISE EXCEPTION
                    'entity_type % is not an ACTIVE dictionary_entity_type',
                    NEW.entity_type;
            END IF;

            RETURN NEW;
        END;
        $$;
        """,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_normalize_and_validate_relation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_canonical_relation_type TEXT;
            v_source_type TEXT;
            v_target_type TEXT;
        BEGIN
            NEW.relation_type := upper(btrim(NEW.relation_type));
            IF NEW.relation_type IS NULL OR NEW.relation_type = '' THEN
                RAISE EXCEPTION 'relation_type is required';
            END IF;

            SELECT syn.relation_type
              INTO v_canonical_relation_type
            FROM dictionary_relation_synonyms syn
            JOIN dictionary_relation_types drt
              ON drt.id = syn.relation_type
            WHERE syn.synonym = NEW.relation_type
              AND syn.is_active IS TRUE
              AND syn.review_status = 'ACTIVE'
              AND drt.is_active IS TRUE
              AND drt.review_status = 'ACTIVE'
            ORDER BY syn.id
            LIMIT 1;

            IF v_canonical_relation_type IS NOT NULL THEN
                NEW.relation_type := v_canonical_relation_type;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM dictionary_relation_types drt
                WHERE drt.id = NEW.relation_type
                  AND drt.is_active IS TRUE
                  AND drt.review_status = 'ACTIVE'
            ) THEN
                RAISE EXCEPTION
                    'relation_type % is not an ACTIVE dictionary_relation_type',
                    NEW.relation_type;
            END IF;

            SELECT e.entity_type
              INTO v_source_type
            FROM entities e
            WHERE e.id = NEW.source_id
              AND e.research_space_id = NEW.research_space_id;
            IF v_source_type IS NULL THEN
                RAISE EXCEPTION
                    'source_id % does not belong to research_space_id %',
                    NEW.source_id,
                    NEW.research_space_id;
            END IF;

            SELECT e.entity_type
              INTO v_target_type
            FROM entities e
            WHERE e.id = NEW.target_id
              AND e.research_space_id = NEW.research_space_id;
            IF v_target_type IS NULL THEN
                RAISE EXCEPTION
                    'target_id % does not belong to research_space_id %',
                    NEW.target_id,
                    NEW.research_space_id;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM relation_constraints rc
                WHERE rc.source_type = v_source_type
                  AND rc.relation_type = NEW.relation_type
                  AND rc.target_type = v_target_type
                  AND rc.is_allowed IS TRUE
                  AND rc.is_active IS TRUE
                  AND rc.review_status = 'ACTIVE'
            ) THEN
                RAISE EXCEPTION
                    'relation triple (% -> % -> %) is not allowed by ACTIVE relation constraints',
                    v_source_type,
                    NEW.relation_type,
                    v_target_type;
            END IF;

            RETURN NEW;
        END;
        $$;
        """,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_enforce_relation_requires_evidence()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_source_type TEXT;
            v_target_type TEXT;
            v_requires_evidence BOOLEAN;
        BEGIN
            SELECT e.entity_type
              INTO v_source_type
            FROM entities e
            WHERE e.id = NEW.source_id;

            SELECT e.entity_type
              INTO v_target_type
            FROM entities e
            WHERE e.id = NEW.target_id;

            SELECT rc.requires_evidence
              INTO v_requires_evidence
            FROM relation_constraints rc
            WHERE rc.source_type = v_source_type
              AND rc.relation_type = NEW.relation_type
              AND rc.target_type = v_target_type
              AND rc.is_allowed IS TRUE
              AND rc.is_active IS TRUE
              AND rc.review_status = 'ACTIVE'
            ORDER BY rc.id DESC
            LIMIT 1;

            IF COALESCE(v_requires_evidence, TRUE)
               AND NOT EXISTS (
                    SELECT 1
                    FROM relation_evidence re
                    WHERE re.relation_id = NEW.id
               ) THEN
                RAISE EXCEPTION
                    'relation % requires evidence but none exists at commit',
                    NEW.id;
            END IF;

            RETURN NEW;
        END;
        $$;
        """,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_prevent_deactivate_entity_type_with_usage()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.is_active IS TRUE
               AND (
                    NEW.is_active IS NOT TRUE
                    OR NEW.review_status <> 'ACTIVE'
               )
               AND EXISTS (
                    SELECT 1
                    FROM entities e
                    WHERE e.entity_type = OLD.id
                    LIMIT 1
               ) THEN
                RAISE EXCEPTION
                    'Cannot deactivate/revoke dictionary_entity_type % while entities still reference it',
                    OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_prevent_deactivate_relation_type_with_usage()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.is_active IS TRUE
               AND (
                    NEW.is_active IS NOT TRUE
                    OR NEW.review_status <> 'ACTIVE'
               )
               AND EXISTS (
                    SELECT 1
                    FROM relations r
                    WHERE r.relation_type = OLD.id
                    LIMIT 1
               ) THEN
                RAISE EXCEPTION
                    'Cannot deactivate/revoke dictionary_relation_type % while relations still reference it',
                    OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """,
    )


def _create_integrity_triggers() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if _has_table("entities"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_entities_normalize_validate ON entities",
        )
        op.execute(
            """
            CREATE TRIGGER trg_entities_normalize_validate
            BEFORE INSERT OR UPDATE OF entity_type
            ON entities
            FOR EACH ROW
            EXECUTE FUNCTION trg_normalize_and_validate_entity_type()
            """,
        )

    if _has_table("relations"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_relations_normalize_validate ON relations",
        )
        op.execute(
            """
            CREATE TRIGGER trg_relations_normalize_validate
            BEFORE INSERT OR UPDATE OF relation_type, source_id, target_id, research_space_id
            ON relations
            FOR EACH ROW
            EXECUTE FUNCTION trg_normalize_and_validate_relation()
            """,
        )

        op.execute(
            "DROP TRIGGER IF EXISTS trg_relations_requires_evidence ON relations",
        )
        op.execute(
            """
            CREATE CONSTRAINT TRIGGER trg_relations_requires_evidence
            AFTER INSERT OR UPDATE OF relation_type, source_id, target_id
            ON relations
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION trg_enforce_relation_requires_evidence()
            """,
        )

    if _has_table("dictionary_entity_types"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_dict_entity_type_usage_guard ON dictionary_entity_types",
        )
        op.execute(
            """
            CREATE TRIGGER trg_dict_entity_type_usage_guard
            BEFORE UPDATE OF is_active, review_status
            ON dictionary_entity_types
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_deactivate_entity_type_with_usage()
            """,
        )

    if _has_table("dictionary_relation_types"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_dict_relation_type_usage_guard ON dictionary_relation_types",
        )
        op.execute(
            """
            CREATE TRIGGER trg_dict_relation_type_usage_guard
            BEFORE UPDATE OF is_active, review_status
            ON dictionary_relation_types
            FOR EACH ROW
            EXECUTE FUNCTION trg_prevent_deactivate_relation_type_with_usage()
            """,
        )


def _validate_existing_graph_rows() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if _has_table("entities") and _has_table("dictionary_entity_types"):
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM entities e
                    JOIN dictionary_entity_types det
                      ON det.id = e.entity_type
                    WHERE det.is_active IS NOT TRUE
                       OR det.review_status <> 'ACTIVE'
                ) THEN
                    RAISE EXCEPTION
                        'Existing entities rows reference non-ACTIVE dictionary_entity_types';
                END IF;
            END $$;
            """,
        )

    if _has_table("relations") and _has_table("dictionary_relation_types"):
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM relations r
                    JOIN dictionary_relation_types drt
                      ON drt.id = r.relation_type
                    WHERE drt.is_active IS NOT TRUE
                       OR drt.review_status <> 'ACTIVE'
                ) THEN
                    RAISE EXCEPTION
                        'Existing relations rows reference non-ACTIVE dictionary_relation_types';
                END IF;
            END $$;
            """,
        )

    if (
        _has_table("relations")
        and _has_table("entities")
        and _has_table("relation_constraints")
    ):
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM relations r
                    JOIN entities src ON src.id = r.source_id
                    JOIN entities tgt ON tgt.id = r.target_id
                    LEFT JOIN relation_constraints rc
                      ON rc.source_type = src.entity_type
                     AND rc.relation_type = r.relation_type
                     AND rc.target_type = tgt.entity_type
                     AND rc.is_allowed IS TRUE
                     AND rc.is_active IS TRUE
                     AND rc.review_status = 'ACTIVE'
                    WHERE rc.id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Existing relations violate ACTIVE relation_constraints';
                END IF;
            END $$;
            """,
        )

    if (
        _has_table("relations")
        and _has_table("entities")
        and _has_table("relation_constraints")
        and _has_table("relation_evidence")
    ):
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM relations r
                    JOIN entities src ON src.id = r.source_id
                    JOIN entities tgt ON tgt.id = r.target_id
                    JOIN relation_constraints rc
                      ON rc.source_type = src.entity_type
                     AND rc.relation_type = r.relation_type
                     AND rc.target_type = tgt.entity_type
                     AND rc.is_allowed IS TRUE
                     AND rc.is_active IS TRUE
                     AND rc.review_status = 'ACTIVE'
                    WHERE rc.requires_evidence IS TRUE
                      AND NOT EXISTS (
                            SELECT 1
                            FROM relation_evidence re
                            WHERE re.relation_id = r.id
                      )
                ) THEN
                    RAISE EXCEPTION
                        'Existing relations that require evidence are missing relation_evidence rows';
                END IF;
            END $$;
            """,
        )


def _drop_integrity_triggers() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if _has_table("dictionary_relation_types"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_dict_relation_type_usage_guard ON dictionary_relation_types",
        )
    if _has_table("dictionary_entity_types"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_dict_entity_type_usage_guard ON dictionary_entity_types",
        )
    if _has_table("relations"):
        op.execute(
            "DROP TRIGGER IF EXISTS trg_relations_requires_evidence ON relations",
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_relations_normalize_validate ON relations",
        )
    if _has_table("entities"):
        op.execute("DROP TRIGGER IF EXISTS trg_entities_normalize_validate ON entities")


def _drop_integrity_functions() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "DROP FUNCTION IF EXISTS trg_prevent_deactivate_relation_type_with_usage()",
    )
    op.execute(
        "DROP FUNCTION IF EXISTS trg_prevent_deactivate_entity_type_with_usage()",
    )
    op.execute("DROP FUNCTION IF EXISTS trg_enforce_relation_requires_evidence()")
    op.execute("DROP FUNCTION IF EXISTS trg_normalize_and_validate_relation()")
    op.execute("DROP FUNCTION IF EXISTS trg_normalize_and_validate_entity_type()")


def _drop_graph_constraints() -> None:
    if _has_table("relations"):
        if _has_foreign_key("relations", "fk_relations_target_space_entities"):
            op.drop_constraint(
                "fk_relations_target_space_entities",
                "relations",
                type_="foreignkey",
            )
        if _has_foreign_key("relations", "fk_relations_source_space_entities"):
            op.drop_constraint(
                "fk_relations_source_space_entities",
                "relations",
                type_="foreignkey",
            )
        if _has_foreign_key("relations", "fk_relations_relation_type_dictionary"):
            op.drop_constraint(
                "fk_relations_relation_type_dictionary",
                "relations",
                type_="foreignkey",
            )
    if _has_table("entities"):
        if _has_foreign_key("entities", "fk_entities_entity_type_dictionary"):
            op.drop_constraint(
                "fk_entities_entity_type_dictionary",
                "entities",
                type_="foreignkey",
            )
        if _has_unique_constraint("entities", "uq_entities_id_space"):
            op.drop_constraint("uq_entities_id_space", "entities", type_="unique")


def _drop_relation_synonyms_table() -> None:
    if not _has_table(_RELATION_SYNONYMS_TABLE):
        return
    if _has_index(_RELATION_SYNONYMS_TABLE, "uq_relation_synonyms_active_synonym"):
        op.drop_index(
            "uq_relation_synonyms_active_synonym",
            table_name=_RELATION_SYNONYMS_TABLE,
        )
    if _has_index(_RELATION_SYNONYMS_TABLE, "idx_rel_syn_relation_type"):
        op.drop_index("idx_rel_syn_relation_type", table_name=_RELATION_SYNONYMS_TABLE)
    op.drop_table(_RELATION_SYNONYMS_TABLE)


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        index.get("name") == index_name for index in inspector.get_indexes(table_name)
    )


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def _has_foreign_key(table_name: str, fk_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name)
    )
