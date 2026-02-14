"""Add first-class dictionary type tables and FK constraints.

Revision ID: 011_dictionary_type_tables
Revises: 010_dictionary_changelog
Create Date: 2026-02-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "011_dictionary_type_tables"
down_revision = "010_dictionary_changelog"
branch_labels = None
depends_on = None

_DATA_TYPES: tuple[tuple[str, str, str, str], ...] = (
    ("INTEGER", "Integer", "int", "Whole-number value"),
    ("FLOAT", "Float", "float", "Decimal numeric value"),
    ("STRING", "String", "str", "Free-form text"),
    ("DATE", "Date", "datetime", "Date/time value"),
    ("CODED", "Coded", "str", "Enumerated coded value"),
    ("BOOLEAN", "Boolean", "bool", "True/False value"),
    ("JSON", "JSON", "dict", "Structured JSON payload"),
)
_DOMAIN_CONTEXTS: tuple[tuple[str, str, str], ...] = (
    ("general", "General", "Default cross-domain context"),
    ("genomics", "Genomics", "Genomics and variant interpretation"),
    ("clinical", "Clinical", "Clinical and phenotypic observations"),
    ("sports", "Sports", "Sports analytics domain"),
    ("cs_benchmarking", "CS Benchmarking", "Computer-science benchmarking data"),
)
_SENSITIVITY_LEVELS: tuple[tuple[str, str, str], ...] = (
    ("PUBLIC", "Public", "Data suitable for broad sharing"),
    ("INTERNAL", "Internal", "Internal-only research data"),
    ("PHI", "Protected Health Information", "Sensitive regulated patient data"),
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in _inspector().get_indexes(table_name)
    )


def _existing_fk_pairs(table_name: str) -> set[tuple[tuple[str, ...], str]]:
    fk_pairs: set[tuple[tuple[str, ...], str]] = set()
    for fk in _inspector().get_foreign_keys(table_name):
        constrained_columns = tuple(
            str(col) for col in fk.get("constrained_columns", [])
        )
        referred_table = str(fk.get("referred_table", ""))
        if constrained_columns and referred_table:
            fk_pairs.add((constrained_columns, referred_table))
    return fk_pairs


def _has_fk_name(table_name: str, constraint_name: str) -> bool:
    return any(
        fk.get("name") == constraint_name
        for fk in _inspector().get_foreign_keys(table_name)
    )


def _normalized_distinct_values(query: str) -> list[str]:
    values: set[str] = set()
    result = op.get_bind().execute(sa.text(query))
    for raw in result.scalars():
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if value:
            values.add(value)
    return sorted(values)


def _execute_text(
    statement: str,
    params: dict[str, object],
    *,
    jsonb_fields: tuple[str, ...] = (),
) -> None:
    clause = sa.text(statement)
    for field in jsonb_fields:
        clause = clause.bindparams(
            sa.bindparam(
                field,
                type_=postgresql.JSONB(astext_type=sa.Text()),
            ),
        )
    op.get_bind().execute(clause, params)


def _humanize(identifier: str) -> str:
    return " ".join(part.capitalize() for part in identifier.replace("_", " ").split())


def _insert_data_type(
    *,
    id_value: str,
    display_name: str,
    python_type_hint: str,
    description: str,
) -> None:
    _execute_text(
        """
            INSERT INTO dictionary_data_types
                (id, display_name, python_type_hint, description, constraint_schema)
            SELECT :id, :display_name, :python_type_hint, :description, :constraint_schema
            WHERE NOT EXISTS (
                SELECT 1 FROM dictionary_data_types WHERE id = :id
            )
            """,
        {
            "id": id_value,
            "display_name": display_name,
            "python_type_hint": python_type_hint,
            "description": description,
            "constraint_schema": {},
        },
        jsonb_fields=("constraint_schema",),
    )


def _insert_domain_context(
    *,
    id_value: str,
    display_name: str,
    description: str,
) -> None:
    _execute_text(
        """
            INSERT INTO dictionary_domain_contexts (id, display_name, description)
            SELECT :id, :display_name, :description
            WHERE NOT EXISTS (
                SELECT 1 FROM dictionary_domain_contexts WHERE id = :id
            )
            """,
        {
            "id": id_value,
            "display_name": display_name,
            "description": description,
        },
    )


def _insert_sensitivity_level(
    *,
    id_value: str,
    display_name: str,
    description: str,
) -> None:
    _execute_text(
        """
            INSERT INTO dictionary_sensitivity_levels (id, display_name, description)
            SELECT :id, :display_name, :description
            WHERE NOT EXISTS (
                SELECT 1 FROM dictionary_sensitivity_levels WHERE id = :id
            )
            """,
        {
            "id": id_value,
            "display_name": display_name,
            "description": description,
        },
    )


def _insert_entity_type(
    *,
    id_value: str,
    domain_context: str,
) -> None:
    _execute_text(
        """
            INSERT INTO dictionary_entity_types (
                id, display_name, description, domain_context, expected_properties,
                created_by, review_status
            )
            SELECT :id, :display_name, :description, :domain_context, :expected_properties,
                   :created_by, :review_status
            WHERE NOT EXISTS (
                SELECT 1 FROM dictionary_entity_types WHERE id = :id
            )
            """,
        {
            "id": id_value,
            "display_name": _humanize(id_value),
            "description": (
                "Autogenerated entity type backfilled from existing dictionary "
                "configuration."
            ),
            "domain_context": domain_context,
            "expected_properties": {},
            "created_by": "migration:011_dictionary_type_tables",
            "review_status": "ACTIVE",
        },
        jsonb_fields=("expected_properties",),
    )


def _insert_relation_type(
    *,
    id_value: str,
    domain_context: str,
) -> None:
    _execute_text(
        """
            INSERT INTO dictionary_relation_types (
                id, display_name, description, domain_context, is_directional,
                created_by, review_status
            )
            SELECT :id, :display_name, :description, :domain_context, :is_directional,
                   :created_by, :review_status
            WHERE NOT EXISTS (
                SELECT 1 FROM dictionary_relation_types WHERE id = :id
            )
            """,
        {
            "id": id_value,
            "display_name": _humanize(id_value),
            "description": (
                "Autogenerated relation type backfilled from existing relation "
                "constraints."
            ),
            "domain_context": domain_context,
            "is_directional": True,
            "created_by": "migration:011_dictionary_type_tables",
            "review_status": "ACTIVE",
        },
    )


def _create_reference_tables() -> None:
    if not _has_table("dictionary_data_types"):
        op.create_table(
            "dictionary_data_types",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("display_name", sa.String(length=64), nullable=False),
            sa.Column("python_type_hint", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "constraint_schema",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
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
            comment="First-class dictionary data types",
        )

    if not _has_table("dictionary_domain_contexts"):
        op.create_table(
            "dictionary_domain_contexts",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
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
            comment="First-class dictionary domain contexts",
        )

    if not _has_table("dictionary_sensitivity_levels"):
        op.create_table(
            "dictionary_sensitivity_levels",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("display_name", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
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
            comment="First-class dictionary sensitivity levels",
        )

    if not _has_table("dictionary_entity_types"):
        op.create_table(
            "dictionary_entity_types",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "domain_context",
                sa.String(length=64),
                sa.ForeignKey("dictionary_domain_contexts.id"),
                nullable=False,
            ),
            sa.Column("external_ontology_ref", sa.String(length=255), nullable=True),
            sa.Column(
                "expected_properties",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "description_embedding",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "created_by",
                sa.String(length=128),
                nullable=False,
                server_default="seed",
            ),
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
            comment="First-class entity types with semantic metadata",
        )
    if not _has_index("dictionary_entity_types", "idx_enttype_domain"):
        op.create_index(
            "idx_enttype_domain",
            "dictionary_entity_types",
            ["domain_context"],
            unique=False,
        )

    if not _has_table("dictionary_relation_types"):
        op.create_table(
            "dictionary_relation_types",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "domain_context",
                sa.String(length=64),
                sa.ForeignKey("dictionary_domain_contexts.id"),
                nullable=False,
            ),
            sa.Column(
                "is_directional",
                sa.Boolean(),
                nullable=False,
                server_default="true",
            ),
            sa.Column("inverse_label", sa.String(length=128), nullable=True),
            sa.Column(
                "description_embedding",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "created_by",
                sa.String(length=128),
                nullable=False,
                server_default="seed",
            ),
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
            comment="First-class relation types with semantic metadata",
        )
    if not _has_index("dictionary_relation_types", "idx_reltype_domain"):
        op.create_index(
            "idx_reltype_domain",
            "dictionary_relation_types",
            ["domain_context"],
            unique=False,
        )


def _seed_reference_rows() -> None:  # noqa: C901, PLR0912
    for id_value, display_name, python_type_hint, description in _DATA_TYPES:
        _insert_data_type(
            id_value=id_value,
            display_name=display_name,
            python_type_hint=python_type_hint,
            description=description,
        )

    for id_value, display_name, description in _DOMAIN_CONTEXTS:
        _insert_domain_context(
            id_value=id_value,
            display_name=display_name,
            description=description,
        )

    for id_value, display_name, description in _SENSITIVITY_LEVELS:
        _insert_sensitivity_level(
            id_value=id_value,
            display_name=display_name,
            description=description,
        )

    if _has_table("variable_definitions"):
        for data_type in _normalized_distinct_values(
            "SELECT DISTINCT data_type "
            "FROM variable_definitions "
            "WHERE data_type IS NOT NULL",
        ):
            _insert_data_type(
                id_value=data_type,
                display_name=_humanize(data_type),
                python_type_hint="str",
                description=(
                    "Autogenerated data type backfilled from variable definitions."
                ),
            )

        for domain_context in _normalized_distinct_values(
            "SELECT DISTINCT domain_context "
            "FROM variable_definitions "
            "WHERE domain_context IS NOT NULL",
        ):
            _insert_domain_context(
                id_value=domain_context,
                display_name=_humanize(domain_context),
                description=(
                    "Autogenerated domain context backfilled from variable definitions."
                ),
            )

        for sensitivity_level in _normalized_distinct_values(
            "SELECT DISTINCT sensitivity "
            "FROM variable_definitions "
            "WHERE sensitivity IS NOT NULL",
        ):
            _insert_sensitivity_level(
                id_value=sensitivity_level,
                display_name=_humanize(sensitivity_level),
                description=(
                    "Autogenerated sensitivity level backfilled from variable definitions."
                ),
            )

    entity_type_values: set[str] = set()
    if _has_table("entity_resolution_policies"):
        entity_type_values.update(
            _normalized_distinct_values(
                "SELECT DISTINCT entity_type "
                "FROM entity_resolution_policies "
                "WHERE entity_type IS NOT NULL",
            ),
        )
    if _has_table("relation_constraints"):
        entity_type_values.update(
            _normalized_distinct_values(
                "SELECT DISTINCT source_type "
                "FROM relation_constraints "
                "WHERE source_type IS NOT NULL",
            ),
        )
        entity_type_values.update(
            _normalized_distinct_values(
                "SELECT DISTINCT target_type "
                "FROM relation_constraints "
                "WHERE target_type IS NOT NULL",
            ),
        )
    if _has_table("entities"):
        entity_type_values.update(
            _normalized_distinct_values(
                "SELECT DISTINCT entity_type "
                "FROM entities "
                "WHERE entity_type IS NOT NULL",
            ),
        )

    for entity_type in sorted(entity_type_values):
        _insert_entity_type(id_value=entity_type, domain_context="general")

    relation_type_values: set[str] = set()
    if _has_table("relation_constraints"):
        relation_type_values.update(
            _normalized_distinct_values(
                "SELECT DISTINCT relation_type "
                "FROM relation_constraints "
                "WHERE relation_type IS NOT NULL",
            ),
        )
    if _has_table("relations"):
        relation_type_values.update(
            _normalized_distinct_values(
                "SELECT DISTINCT relation_type "
                "FROM relations "
                "WHERE relation_type IS NOT NULL",
            ),
        )

    for relation_type in sorted(relation_type_values):
        _insert_relation_type(id_value=relation_type, domain_context="general")


def _add_fk_constraints() -> None:  # noqa: C901
    if _has_table("variable_definitions"):
        existing = _existing_fk_pairs("variable_definitions")
        with op.batch_alter_table("variable_definitions") as batch_op:
            if (("data_type",), "dictionary_data_types") not in existing:
                batch_op.create_foreign_key(
                    "fk_vardef_data_type",
                    "dictionary_data_types",
                    ["data_type"],
                    ["id"],
                )
            if (("domain_context",), "dictionary_domain_contexts") not in existing:
                batch_op.create_foreign_key(
                    "fk_vardef_domain_context",
                    "dictionary_domain_contexts",
                    ["domain_context"],
                    ["id"],
                )
            if (("sensitivity",), "dictionary_sensitivity_levels") not in existing:
                batch_op.create_foreign_key(
                    "fk_vardef_sensitivity",
                    "dictionary_sensitivity_levels",
                    ["sensitivity"],
                    ["id"],
                )

    if _has_table("entity_resolution_policies"):
        existing = _existing_fk_pairs("entity_resolution_policies")
        with op.batch_alter_table("entity_resolution_policies") as batch_op:
            if (("entity_type",), "dictionary_entity_types") not in existing:
                batch_op.create_foreign_key(
                    "fk_erp_entity_type",
                    "dictionary_entity_types",
                    ["entity_type"],
                    ["id"],
                )

    if _has_table("relation_constraints"):
        existing = _existing_fk_pairs("relation_constraints")
        with op.batch_alter_table("relation_constraints") as batch_op:
            if (("source_type",), "dictionary_entity_types") not in existing:
                batch_op.create_foreign_key(
                    "fk_relcon_source_type",
                    "dictionary_entity_types",
                    ["source_type"],
                    ["id"],
                )
            if (("target_type",), "dictionary_entity_types") not in existing:
                batch_op.create_foreign_key(
                    "fk_relcon_target_type",
                    "dictionary_entity_types",
                    ["target_type"],
                    ["id"],
                )
            if (("relation_type",), "dictionary_relation_types") not in existing:
                batch_op.create_foreign_key(
                    "fk_relcon_relation_type",
                    "dictionary_relation_types",
                    ["relation_type"],
                    ["id"],
                )


def upgrade() -> None:
    _create_reference_tables()
    _seed_reference_rows()
    _add_fk_constraints()


def _drop_fk_if_present(
    *,
    table_name: str,
    fk_name: str,
) -> None:
    if not _has_table(table_name) or not _has_fk_name(table_name, fk_name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(fk_name, type_="foreignkey")


def downgrade() -> None:
    _drop_fk_if_present(
        table_name="relation_constraints",
        fk_name="fk_relcon_relation_type",
    )
    _drop_fk_if_present(
        table_name="relation_constraints",
        fk_name="fk_relcon_target_type",
    )
    _drop_fk_if_present(
        table_name="relation_constraints",
        fk_name="fk_relcon_source_type",
    )
    _drop_fk_if_present(
        table_name="entity_resolution_policies",
        fk_name="fk_erp_entity_type",
    )
    _drop_fk_if_present(
        table_name="variable_definitions",
        fk_name="fk_vardef_sensitivity",
    )
    _drop_fk_if_present(
        table_name="variable_definitions",
        fk_name="fk_vardef_domain_context",
    )
    _drop_fk_if_present(
        table_name="variable_definitions",
        fk_name="fk_vardef_data_type",
    )

    if _has_table("dictionary_relation_types"):
        if _has_index("dictionary_relation_types", "idx_reltype_domain"):
            op.drop_index("idx_reltype_domain", table_name="dictionary_relation_types")
        op.drop_table("dictionary_relation_types")

    if _has_table("dictionary_entity_types"):
        if _has_index("dictionary_entity_types", "idx_enttype_domain"):
            op.drop_index("idx_enttype_domain", table_name="dictionary_entity_types")
        op.drop_table("dictionary_entity_types")

    if _has_table("dictionary_sensitivity_levels"):
        op.drop_table("dictionary_sensitivity_levels")
    if _has_table("dictionary_domain_contexts"):
        op.drop_table("dictionary_domain_contexts")
    if _has_table("dictionary_data_types"):
        op.drop_table("dictionary_data_types")
