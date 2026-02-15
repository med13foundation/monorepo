"""Add controlled dictionary search embedding columns and indexes.

Revision ID: 013_dictionary_embeddings
Revises: 012_dictionary_value_sets
Create Date: 2026-02-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "013_dictionary_embeddings"
down_revision = "012_dictionary_value_sets"
branch_labels = None
depends_on = None

_VECTOR_DIMENSIONS = 1536


def _bind() -> sa.Connection:
    return op.get_bind()


def _inspector() -> sa.Inspector:
    return sa.inspect(_bind())


def _is_postgres() -> bool:
    return _bind().dialect.name == "postgresql"


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    if _is_postgres():
        exists = (
            _bind()
            .execute(
                sa.text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = :table_name
                      AND column_name = :column_name
                      AND table_schema = ANY(current_schemas(false))
                    LIMIT 1
                    """,
                ),
                {
                    "table_name": table_name,
                    "column_name": column_name,
                },
            )
            .scalar_one_or_none()
        )
        return exists is not None
    return column_name in {
        column["name"] for column in _inspector().get_columns(table_name)
    }


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index["name"] == index_name for index in _inspector().get_indexes(table_name)
    )


def _is_vector_column(table_name: str, column_name: str) -> bool:
    if not _is_postgres() or not _has_column(table_name, column_name):
        return False

    udt_name = (
        _bind()
        .execute(
            sa.text(
                """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_name = :table_name
              AND column_name = :column_name
              AND table_schema = ANY(current_schemas(false))
            ORDER BY CASE WHEN table_schema = 'public' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            ),
            {
                "table_name": table_name,
                "column_name": column_name,
            },
        )
        .scalar_one_or_none()
    )

    return isinstance(udt_name, str) and udt_name == "vector"


def _enable_postgres_extensions() -> None:
    if not _is_postgres():
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def _ensure_embedding_columns() -> None:  # noqa: C901
    if not _has_table("variable_definitions"):
        return

    if not _has_column("variable_definitions", "description_embedding"):
        if _is_postgres():
            op.execute(
                f"""
                ALTER TABLE variable_definitions
                ADD COLUMN description_embedding VECTOR({_VECTOR_DIMENSIONS})
                """,
            )
        else:
            op.add_column(
                "variable_definitions",
                sa.Column(
                    "description_embedding",
                    sa.JSON(),
                    nullable=True,
                ),
            )
    elif _is_postgres() and not _is_vector_column(
        "variable_definitions",
        "description_embedding",
    ):
        op.execute(
            """
            ALTER TABLE variable_definitions
            ALTER COLUMN description_embedding
            TYPE VECTOR(1536)
            USING CASE
                WHEN description_embedding IS NULL THEN NULL
                WHEN jsonb_typeof(description_embedding) = 'array'
                    THEN translate(description_embedding::text, ' ', '')::vector
                ELSE NULL
            END
            """,
        )

    if not _has_column("variable_definitions", "embedded_at"):
        op.add_column(
            "variable_definitions",
            sa.Column("embedded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        )

    if not _has_column("variable_definitions", "embedding_model"):
        op.add_column(
            "variable_definitions",
            sa.Column("embedding_model", sa.String(length=64), nullable=True),
        )

    for table_name in (
        "dictionary_entity_types",
        "dictionary_relation_types",
    ):
        if not _has_table(table_name):
            continue

        if (
            _is_postgres()
            and _has_column(
                table_name,
                "description_embedding",
            )
            and not _is_vector_column(table_name, "description_embedding")
        ):
            op.execute(
                sa.text(
                    f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN description_embedding
                    TYPE VECTOR(1536)
                    USING CASE
                        WHEN description_embedding IS NULL THEN NULL
                        WHEN jsonb_typeof(description_embedding) = 'array'
                            THEN translate(description_embedding::text, ' ', '')::vector
                        ELSE NULL
                    END
                    """,
                ),
            )

        if not _has_column(table_name, "embedded_at"):
            op.add_column(
                table_name,
                sa.Column("embedded_at", sa.TIMESTAMP(timezone=True), nullable=True),
            )

        if not _has_column(table_name, "embedding_model"):
            op.add_column(
                table_name,
                sa.Column("embedding_model", sa.String(length=64), nullable=True),
            )


def _create_indexes() -> None:
    if _has_table("variable_synonyms") and not _has_index(
        "variable_synonyms",
        "idx_synonym_lower",
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_synonym_lower
            ON variable_synonyms ((LOWER(synonym)))
            """,
        )

    if (
        _is_postgres()
        and _has_table("variable_synonyms")
        and not _has_index(
            "variable_synonyms",
            "idx_synonym_trigram",
        )
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_synonym_trigram
            ON variable_synonyms USING GIN (synonym gin_trgm_ops)
            """,
        )

    if _has_table("variable_definitions") and not _has_index(
        "variable_definitions",
        "idx_vardef_canonical_lower",
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vardef_canonical_lower
            ON variable_definitions ((LOWER(canonical_name)))
            """,
        )

    if (
        _is_postgres()
        and _has_table("variable_definitions")
        and _is_vector_column(
            "variable_definitions",
            "description_embedding",
        )
        and not _has_index("variable_definitions", "idx_vardef_embedding")
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vardef_embedding
            ON variable_definitions
            USING hnsw (description_embedding vector_cosine_ops)
            """,
        )

    if (
        _is_postgres()
        and _has_table("dictionary_entity_types")
        and _is_vector_column(
            "dictionary_entity_types",
            "description_embedding",
        )
        and not _has_index("dictionary_entity_types", "idx_enttype_embedding")
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_enttype_embedding
            ON dictionary_entity_types
            USING hnsw (description_embedding vector_cosine_ops)
            """,
        )

    if _has_table("dictionary_entity_types") and not _has_index(
        "dictionary_entity_types",
        "idx_enttype_domain",
    ):
        op.create_index(
            "idx_enttype_domain",
            "dictionary_entity_types",
            ["domain_context"],
            unique=False,
        )

    if (
        _is_postgres()
        and _has_table(
            "dictionary_relation_types",
        )
        and _is_vector_column(
            "dictionary_relation_types",
            "description_embedding",
        )
        and not _has_index("dictionary_relation_types", "idx_reltype_embedding")
    ):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reltype_embedding
            ON dictionary_relation_types
            USING hnsw (description_embedding vector_cosine_ops)
            """,
        )

    if _has_table("dictionary_relation_types") and not _has_index(
        "dictionary_relation_types",
        "idx_reltype_domain",
    ):
        op.create_index(
            "idx_reltype_domain",
            "dictionary_relation_types",
            ["domain_context"],
            unique=False,
        )


def upgrade() -> None:
    _enable_postgres_extensions()
    _ensure_embedding_columns()
    _create_indexes()


def _drop_index_if_exists(index_name: str) -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if not _has_column(table_name, column_name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_column(column_name)


def _revert_vector_columns() -> None:
    if not _is_postgres():
        return

    for table_name in (
        "dictionary_entity_types",
        "dictionary_relation_types",
    ):
        if _is_vector_column(table_name, "description_embedding"):
            op.execute(
                sa.text(
                    f"""
                    ALTER TABLE {table_name}
                    ALTER COLUMN description_embedding
                    TYPE JSONB
                    USING CASE
                        WHEN description_embedding IS NULL THEN NULL
                        ELSE description_embedding::text::jsonb
                    END
                    """,
                ),
            )


def downgrade() -> None:
    _drop_index_if_exists("idx_reltype_domain")
    _drop_index_if_exists("idx_reltype_embedding")
    _drop_index_if_exists("idx_enttype_domain")
    _drop_index_if_exists("idx_enttype_embedding")
    _drop_index_if_exists("idx_vardef_embedding")
    _drop_index_if_exists("idx_vardef_canonical_lower")
    _drop_index_if_exists("idx_synonym_trigram")
    _drop_index_if_exists("idx_synonym_lower")

    _drop_column_if_exists("variable_definitions", "embedding_model")
    _drop_column_if_exists("variable_definitions", "embedded_at")
    _drop_column_if_exists("variable_definitions", "description_embedding")

    _drop_column_if_exists("dictionary_entity_types", "embedding_model")
    _drop_column_if_exists("dictionary_entity_types", "embedded_at")
    _drop_column_if_exists("dictionary_relation_types", "embedding_model")
    _drop_column_if_exists("dictionary_relation_types", "embedded_at")

    _revert_vector_columns()
