"""Add canonical relation evidence + source-aware extraction queue contract.

Revision ID: 004_rel_evidence_extract_queue
Revises: 003_add_source_sync_tracking
Create Date: 2026-02-13
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "004_rel_evidence_extract_queue"
down_revision = "003_add_source_sync_tracking"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _is_sqlite() -> bool:
    return _dialect_name() == "sqlite"


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name for column in _inspector().get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in _inspector().get_indexes(table_name)
    )


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    return any(
        constraint["name"] == constraint_name
        for constraint in _inspector().get_unique_constraints(table_name)
    )


def _drop_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    if _has_unique_constraint(table_name, constraint_name):
        op.drop_constraint(
            constraint_name,
            table_name,
            type_="unique",
        )


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _ensure_relations_aggregate_columns() -> None:
    aggregate_columns = (
        (
            "aggregate_confidence",
            sa.Column(
                "aggregate_confidence",
                sa.Float(),
                nullable=False,
                server_default="0.0",
            ),
        ),
        (
            "source_count",
            sa.Column(
                "source_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        ),
        (
            "highest_evidence_tier",
            sa.Column("highest_evidence_tier", sa.String(length=32), nullable=True),
        ),
    )
    for column_name, column in aggregate_columns:
        if not _has_column("relations", column_name):
            op.add_column("relations", column)


def _ensure_relation_evidence_table() -> None:
    if _has_table("relation_evidence"):
        return
    op.create_table(
        "relation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "relation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("relations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column(
            "evidence_tier",
            sa.String(length=32),
            nullable=False,
            server_default="COMPUTATIONAL",
        ),
        sa.Column(
            "provenance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provenance.id"),
            nullable=True,
        ),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    )


def _ensure_relation_evidence_updated_at() -> None:
    if _has_column("relation_evidence", "updated_at"):
        return
    op.add_column(
        "relation_evidence",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def _ensure_relation_evidence_indexes() -> None:
    relation_evidence_indexes = (
        ("idx_relation_evidence_relation", ["relation_id"]),
        ("idx_relation_evidence_provenance", ["provenance_id"]),
        ("idx_relation_evidence_tier", ["evidence_tier"]),
    )
    for index_name, columns in relation_evidence_indexes:
        if not _has_index("relation_evidence", index_name):
            op.create_index(index_name, "relation_evidence", columns)


def _sqlite_backfill_relation_evidence() -> None:
    if not _has_column("relations", "confidence"):
        return
    op.execute(
        """
        INSERT INTO relation_evidence (
            id,
            relation_id,
            confidence,
            evidence_summary,
            evidence_tier,
            provenance_id,
            source_document_id,
            agent_run_id,
            created_at
        )
        SELECT
            rel.id,
            rel.id,
            CASE
                WHEN rel.confidence IS NULL THEN 0.0
                WHEN rel.confidence < 0.0 THEN 0.0
                WHEN rel.confidence > 1.0 THEN 1.0
                ELSE rel.confidence
            END,
            rel.evidence_summary,
            COALESCE(NULLIF(TRIM(rel.evidence_tier), ''), 'COMPUTATIONAL'),
            rel.provenance_id,
            NULL,
            NULL,
            rel.created_at
        FROM relations rel
        WHERE NOT EXISTS (SELECT 1 FROM relation_evidence)
        """,
    )


def _sqlite_update_relation_aggregates() -> None:
    op.execute(
        """
        UPDATE relations
        SET
            source_count = (
                SELECT COUNT(*)
                FROM relation_evidence evidence
                WHERE evidence.relation_id = relations.id
            ),
            aggregate_confidence = COALESCE(
                (
                    SELECT MAX(
                        CASE
                            WHEN evidence.confidence < 0.0 THEN 0.0
                            WHEN evidence.confidence > 1.0 THEN 1.0
                            ELSE evidence.confidence
                        END
                    )
                    FROM relation_evidence evidence
                    WHERE evidence.relation_id = relations.id
                ),
                0.0
            ),
            highest_evidence_tier = (
                SELECT evidence.evidence_tier
                FROM relation_evidence evidence
                WHERE evidence.relation_id = relations.id
                ORDER BY
                    CASE UPPER(evidence.evidence_tier)
                        WHEN 'EXPERT_CURATED' THEN 6
                        WHEN 'CLINICAL' THEN 5
                        WHEN 'EXPERIMENTAL' THEN 4
                        WHEN 'LITERATURE' THEN 3
                        WHEN 'STRUCTURED_DATA' THEN 2
                        WHEN 'COMPUTATIONAL' THEN 1
                        ELSE 0
                    END DESC,
                    evidence.created_at ASC,
                    CAST(evidence.id AS TEXT) ASC
                LIMIT 1
            )
        """,
    )


def _ensure_relations_canonical_edge_unique_index_sqlite() -> None:
    if _has_index("relations", "uq_relations_canonical_edge"):
        return
    op.create_index(
        "uq_relations_canonical_edge",
        "relations",
        ["source_id", "relation_type", "target_id", "research_space_id"],
        unique=True,
    )


def _ensure_relations_aggregate_confidence_index() -> None:
    if _has_index("relations", "idx_relations_aggregate_confidence"):
        return
    op.create_index(
        "idx_relations_aggregate_confidence",
        "relations",
        ["aggregate_confidence"],
    )


def _upgrade_relations_sqlite() -> None:
    _sqlite_backfill_relation_evidence()
    _sqlite_update_relation_aggregates()
    _ensure_relations_canonical_edge_unique_index_sqlite()
    _ensure_relations_aggregate_confidence_index()


def _postgres_backfill_relation_evidence_and_deduplicate() -> None:
    if not _has_column("relations", "confidence"):
        return
    op.execute(
        """
        INSERT INTO relation_evidence (
            id,
            relation_id,
            confidence,
            evidence_summary,
            evidence_tier,
            provenance_id,
            source_document_id,
            agent_run_id,
            created_at
        )
        SELECT
            ranked.id,
            ranked.winner_id,
            LEAST(GREATEST(COALESCE(ranked.confidence, 0.0), 0.0), 1.0),
            ranked.evidence_summary,
            COALESCE(NULLIF(TRIM(ranked.evidence_tier), ''), 'COMPUTATIONAL'),
            ranked.provenance_id,
            NULL,
            NULL,
            ranked.created_at
        FROM (
            SELECT
                rel.id,
                rel.confidence,
                rel.evidence_summary,
                rel.evidence_tier,
                rel.provenance_id,
                rel.created_at,
                FIRST_VALUE(rel.id) OVER (
                    PARTITION BY
                        rel.research_space_id,
                        rel.source_id,
                        rel.relation_type,
                        rel.target_id
                    ORDER BY
                        CASE WHEN rel.reviewed_at IS NULL THEN 1 ELSE 0 END,
                        rel.reviewed_at DESC NULLS LAST,
                        CASE rel.curation_status
                            WHEN 'RETRACTED' THEN 5
                            WHEN 'REJECTED' THEN 4
                            WHEN 'UNDER_REVIEW' THEN 3
                            WHEN 'DRAFT' THEN 2
                            WHEN 'APPROVED' THEN 1
                            ELSE 0
                        END DESC,
                        rel.created_at ASC NULLS LAST,
                        rel.id::text ASC
                ) AS winner_id
            FROM relations rel
        ) AS ranked
        WHERE NOT EXISTS (SELECT 1 FROM relation_evidence)
        """,
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT
                rel.id,
                rel.created_at,
                rel.updated_at,
                FIRST_VALUE(rel.id) OVER (
                    PARTITION BY
                        rel.research_space_id,
                        rel.source_id,
                        rel.relation_type,
                        rel.target_id
                    ORDER BY
                        CASE WHEN rel.reviewed_at IS NULL THEN 1 ELSE 0 END,
                        rel.reviewed_at DESC NULLS LAST,
                        CASE rel.curation_status
                            WHEN 'RETRACTED' THEN 5
                            WHEN 'REJECTED' THEN 4
                            WHEN 'UNDER_REVIEW' THEN 3
                            WHEN 'DRAFT' THEN 2
                            WHEN 'APPROVED' THEN 1
                            ELSE 0
                        END DESC,
                        rel.created_at ASC NULLS LAST,
                        rel.id::text ASC
                ) AS winner_id
            FROM relations rel
        ),
        grouped AS (
            SELECT
                winner_id AS relation_id,
                MIN(created_at) AS min_created_at,
                MAX(updated_at) AS max_updated_at
            FROM ranked
            GROUP BY winner_id
        )
        UPDATE relations rel
        SET
            created_at = grouped.min_created_at,
            updated_at = grouped.max_updated_at
        FROM grouped
        WHERE rel.id = grouped.relation_id
        """,
    )

    op.execute(
        """
        WITH ranked AS (
            SELECT
                rel.id,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        rel.research_space_id,
                        rel.source_id,
                        rel.relation_type,
                        rel.target_id
                    ORDER BY
                        CASE WHEN rel.reviewed_at IS NULL THEN 1 ELSE 0 END,
                        rel.reviewed_at DESC NULLS LAST,
                        CASE rel.curation_status
                            WHEN 'RETRACTED' THEN 5
                            WHEN 'REJECTED' THEN 4
                            WHEN 'UNDER_REVIEW' THEN 3
                            WHEN 'DRAFT' THEN 2
                            WHEN 'APPROVED' THEN 1
                            ELSE 0
                        END DESC,
                        rel.created_at ASC NULLS LAST,
                        rel.id::text ASC
                ) AS relation_rank
            FROM relations rel
        )
        DELETE FROM relations rel
        USING ranked
        WHERE rel.id = ranked.id AND ranked.relation_rank > 1
        """,
    )


def _postgres_update_relation_aggregates() -> None:
    op.execute(
        """
        WITH evidence_stats AS (
            SELECT
                relation_id,
                COUNT(*)::int AS source_count,
                1 - EXP(
                    SUM(
                        LN(
                            GREATEST(
                                1 - LEAST(GREATEST(confidence, 0.0), 1.0),
                                1e-12
                            )
                        )
                    )
                ) AS aggregate_confidence
            FROM relation_evidence
            GROUP BY relation_id
        ),
        tier_ranked AS (
            SELECT
                relation_id,
                evidence_tier,
                ROW_NUMBER() OVER (
                    PARTITION BY relation_id
                    ORDER BY
                        CASE UPPER(evidence_tier)
                            WHEN 'EXPERT_CURATED' THEN 6
                            WHEN 'CLINICAL' THEN 5
                            WHEN 'EXPERIMENTAL' THEN 4
                            WHEN 'LITERATURE' THEN 3
                            WHEN 'STRUCTURED_DATA' THEN 2
                            WHEN 'COMPUTATIONAL' THEN 1
                            ELSE 0
                        END DESC,
                        created_at ASC,
                        id::text ASC
                ) AS tier_rank
            FROM relation_evidence
        )
        UPDATE relations rel
        SET
            source_count = evidence_stats.source_count,
            aggregate_confidence = LEAST(
                GREATEST(evidence_stats.aggregate_confidence, 0.0),
                1.0
            ),
            highest_evidence_tier = tier_ranked.evidence_tier
        FROM evidence_stats
        LEFT JOIN tier_ranked
            ON tier_ranked.relation_id = evidence_stats.relation_id
            AND tier_ranked.tier_rank = 1
        WHERE rel.id = evidence_stats.relation_id
        """,
    )


def _ensure_relations_canonical_edge_unique_constraint_postgres() -> None:
    if _has_unique_constraint("relations", "uq_relations_canonical_edge"):
        return
    op.create_unique_constraint(
        "uq_relations_canonical_edge",
        "relations",
        ["source_id", "relation_type", "target_id", "research_space_id"],
    )


def _drop_legacy_relation_evidence_columns() -> None:
    for column_name in ("confidence", "evidence_summary", "evidence_tier"):
        if _has_column("relations", column_name):
            op.drop_column("relations", column_name)


def _upgrade_relations_postgres() -> None:
    _postgres_backfill_relation_evidence_and_deduplicate()
    _postgres_update_relation_aggregates()
    _ensure_relations_canonical_edge_unique_constraint_postgres()
    _ensure_relations_aggregate_confidence_index()
    _drop_legacy_relation_evidence_columns()


def _upgrade_relations() -> None:
    _ensure_relations_aggregate_columns()
    _ensure_relation_evidence_table()
    _ensure_relation_evidence_updated_at()
    _ensure_relation_evidence_indexes()
    if _is_sqlite():
        _upgrade_relations_sqlite()
        return
    _upgrade_relations_postgres()


def _build_extraction_queue_publication_column() -> sa.Column[object]:
    if _has_table("publications"):
        return sa.Column(
            "publication_id",
            sa.Integer(),
            sa.ForeignKey("publications.id"),
            nullable=True,
        )
    return sa.Column("publication_id", sa.Integer(), nullable=True)


def _create_extraction_queue_base_indexes() -> None:
    queue_indexes = (
        ("idx_extraction_queue_publication_id", ["publication_id"]),
        ("idx_extraction_queue_pubmed_id", ["pubmed_id"]),
        ("idx_extraction_queue_source_id", ["source_id"]),
        ("idx_extraction_queue_ingestion_job_id", ["ingestion_job_id"]),
        ("idx_extraction_queue_status", ["status"]),
        ("idx_extraction_queue_extraction_version", ["extraction_version"]),
        ("idx_extraction_queue_source_type", ["source_type"]),
        ("idx_extraction_queue_source_record_id", ["source_record_id"]),
    )
    for index_name, columns in queue_indexes:
        op.create_index(index_name, "extraction_queue", columns)


def _create_extraction_queue_table() -> None:
    op.create_table(
        "extraction_queue",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        _build_extraction_queue_publication_column(),
        sa.Column("pubmed_id", sa.String(length=20), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user_data_sources.id"),
            nullable=False,
        ),
        sa.Column(
            "ingestion_job_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("ingestion_jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "failed",
                name="extraction_status_enum",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "extraction_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "queued_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_id",
            "source_record_id",
            "extraction_version",
            name="uq_extraction_queue_source_record_version",
        ),
    )
    _create_extraction_queue_base_indexes()


def _ensure_extraction_queue_source_columns() -> None:
    source_columns = (
        ("source_type", sa.String(length=32)),
        ("source_record_id", sa.String(length=255)),
    )
    for column_name, column_type in source_columns:
        if not _has_column("extraction_queue", column_name):
            op.add_column(
                "extraction_queue",
                sa.Column(column_name, column_type, nullable=True),
            )


def _backfill_extraction_queue_source_type() -> None:
    op.execute(
        """
        UPDATE extraction_queue queue
        SET source_type = COALESCE(
            (
                SELECT LOWER(CAST(source.source_type AS TEXT))
                FROM user_data_sources source
                WHERE source.id = queue.source_id
            ),
            'pubmed'
        )
        WHERE queue.source_type IS NULL OR queue.source_type = ''
        """,
    )


def _backfill_extraction_queue_source_record_id_sqlite() -> None:
    op.execute(
        """
        UPDATE extraction_queue
        SET source_record_id = COALESCE(
            NULLIF(pubmed_id, ''),
            CASE
                WHEN publication_id IS NOT NULL
                    THEN 'publication:' || CAST(publication_id AS TEXT)
                ELSE NULL
            END,
            'queue:' || CAST(id AS TEXT)
        )
        WHERE source_record_id IS NULL OR source_record_id = ''
        """,
    )


def _backfill_extraction_queue_source_record_id_postgres() -> None:
    op.execute(
        """
        UPDATE extraction_queue
        SET source_record_id = COALESCE(
            NULLIF(pubmed_id, ''),
            CASE
                WHEN publication_id IS NOT NULL
                    THEN CONCAT('publication:', publication_id::text)
                ELSE NULL
            END,
            CONCAT('queue:', id::text)
        )
        WHERE source_record_id IS NULL OR source_record_id = ''
        """,
    )


def _ensure_extraction_queue_sqlite_indexes() -> None:
    sqlite_indexes = (
        ("idx_extraction_queue_source_type", ["source_type"], False),
        ("idx_extraction_queue_source_record_id", ["source_record_id"], False),
        (
            "uq_extraction_queue_source_record_version",
            ["source_id", "source_record_id", "extraction_version"],
            True,
        ),
    )
    for index_name, columns, is_unique in sqlite_indexes:
        if not _has_index("extraction_queue", index_name):
            op.create_index(
                index_name,
                "extraction_queue",
                columns,
                unique=is_unique,
            )


def _ensure_extraction_queue_postgres_constraints_and_indexes() -> None:
    op.alter_column(
        "extraction_queue",
        "publication_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "extraction_queue",
        "source_type",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "extraction_queue",
        "source_record_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    _drop_constraint_if_exists(
        "extraction_queue",
        "uq_extraction_queue_pub_source_version",
    )
    if not _has_unique_constraint(
        "extraction_queue",
        "uq_extraction_queue_source_record_version",
    ):
        op.create_unique_constraint(
            "uq_extraction_queue_source_record_version",
            "extraction_queue",
            ["source_id", "source_record_id", "extraction_version"],
        )

    for index_name, columns in (
        ("idx_extraction_queue_source_type", ["source_type"]),
        ("idx_extraction_queue_source_record_id", ["source_record_id"]),
    ):
        if not _has_index("extraction_queue", index_name):
            op.create_index(index_name, "extraction_queue", columns)


def _upgrade_existing_extraction_queue() -> None:
    _ensure_extraction_queue_source_columns()
    _backfill_extraction_queue_source_type()
    if _is_sqlite():
        _backfill_extraction_queue_source_record_id_sqlite()
        _ensure_extraction_queue_sqlite_indexes()
        return
    _backfill_extraction_queue_source_record_id_postgres()
    _ensure_extraction_queue_postgres_constraints_and_indexes()


def _upgrade_extraction_queue() -> None:
    if not _has_table("extraction_queue"):
        _create_extraction_queue_table()
        return
    _upgrade_existing_extraction_queue()


def _upgrade_publication_extractions() -> None:
    if not _has_table("publication_extractions"):
        publication_column: sa.Column[object]
        if _has_table("publications"):
            publication_column = sa.Column(
                "publication_id",
                sa.Integer(),
                sa.ForeignKey("publications.id"),
                nullable=True,
            )
        else:
            publication_column = sa.Column(
                "publication_id",
                sa.Integer(),
                nullable=True,
            )
        op.create_table(
            "publication_extractions",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            publication_column,
            sa.Column("pubmed_id", sa.String(length=20), nullable=True),
            sa.Column(
                "source_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("user_data_sources.id"),
                nullable=False,
            ),
            sa.Column(
                "ingestion_job_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("ingestion_jobs.id"),
                nullable=False,
            ),
            sa.Column(
                "queue_item_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("extraction_queue.id"),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.Enum(
                    "completed",
                    "failed",
                    "skipped",
                    name="extraction_outcome_enum",
                ),
                nullable=False,
            ),
            sa.Column(
                "extraction_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column("processor_name", sa.String(length=120), nullable=False),
            sa.Column("processor_version", sa.String(length=50), nullable=True),
            sa.Column("text_source", sa.String(length=30), nullable=False),
            sa.Column("document_reference", sa.String(length=500), nullable=True),
            sa.Column(
                "facts",
                postgresql.JSONB,
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "metadata_payload",
                postgresql.JSONB,
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "extracted_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
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
            sa.UniqueConstraint(
                "queue_item_id",
                name="uq_publication_extractions_queue_item",
            ),
        )
        op.create_index(
            "idx_publication_extractions_publication_id",
            "publication_extractions",
            ["publication_id"],
        )
        op.create_index(
            "idx_publication_extractions_pubmed_id",
            "publication_extractions",
            ["pubmed_id"],
        )
        op.create_index(
            "idx_publication_extractions_source_id",
            "publication_extractions",
            ["source_id"],
        )
        op.create_index(
            "idx_publication_extractions_ingestion_job_id",
            "publication_extractions",
            ["ingestion_job_id"],
        )
        op.create_index(
            "idx_publication_extractions_queue_item_id",
            "publication_extractions",
            ["queue_item_id"],
        )
        op.create_index(
            "idx_publication_extractions_status",
            "publication_extractions",
            ["status"],
        )
        op.create_index(
            "idx_publication_extractions_extraction_version",
            "publication_extractions",
            ["extraction_version"],
        )
        return

    if _is_sqlite():
        return

    op.alter_column(
        "publication_extractions",
        "publication_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def upgrade() -> None:
    if _has_table("relations"):
        _upgrade_relations()

    _upgrade_extraction_queue()

    _upgrade_publication_extractions()


def _downgrade_relations() -> None:
    if not _has_column("relations", "confidence"):
        op.add_column(
            "relations",
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        )
    if not _has_column("relations", "evidence_summary"):
        op.add_column(
            "relations",
            sa.Column("evidence_summary", sa.Text(), nullable=True),
        )
    if not _has_column("relations", "evidence_tier"):
        op.add_column(
            "relations",
            sa.Column("evidence_tier", sa.String(length=32), nullable=True),
        )

    if _has_table("relation_evidence"):
        op.execute(
            """
            WITH ranked AS (
                SELECT
                    evidence.relation_id,
                    evidence.confidence,
                    evidence.evidence_summary,
                    evidence.evidence_tier,
                    ROW_NUMBER() OVER (
                        PARTITION BY evidence.relation_id
                        ORDER BY evidence.created_at DESC, evidence.id::text DESC
                    ) AS row_rank
                FROM relation_evidence evidence
            )
            UPDATE relations rel
            SET
                confidence = COALESCE(ranked.confidence, rel.aggregate_confidence, 0.5),
                evidence_summary = ranked.evidence_summary,
                evidence_tier = COALESCE(
                    ranked.evidence_tier,
                    rel.highest_evidence_tier,
                    'COMPUTATIONAL'
                )
            FROM ranked
            WHERE rel.id = ranked.relation_id
              AND ranked.row_rank = 1
            """,
        )

    _drop_constraint_if_exists("relations", "uq_relations_canonical_edge")
    _drop_index_if_exists("relations", "idx_relations_aggregate_confidence")

    if _has_column("relations", "aggregate_confidence"):
        op.drop_column("relations", "aggregate_confidence")
    if _has_column("relations", "source_count"):
        op.drop_column("relations", "source_count")
    if _has_column("relations", "highest_evidence_tier"):
        op.drop_column("relations", "highest_evidence_tier")

    if _has_table("relation_evidence"):
        op.drop_table("relation_evidence")


def downgrade() -> None:
    if _has_table("relations"):
        _downgrade_relations()

    # Extraction queue/publication extraction downgrade is intentionally lossy because
    # source-aware queue rows may not map back to a required publication_id shape.
    # Keep schema additions in place on downgrade to avoid destructive data loss.
