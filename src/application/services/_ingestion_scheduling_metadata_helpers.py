"""Metadata helpers for ingestion scheduling summaries and idempotency.

These helper methods isolate metadata construction and checkpoint accounting concerns
from orchestration flow in order to keep scheduling services focused.
"""

# mypy: disable-error-code="misc"

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.source_sync_state import CheckpointKind, SourceSyncState
from src.type_definitions import data_sources as data_source_types
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.entities import ingestion_job
    from src.domain.services.ingestion import IngestionRunSummary


class _IngestionSchedulingMetadataHelpers:
    """Helpers for scheduling metadata and idempotency payload construction."""

    def _build_source_metadata(
        self: IngestionSchedulingService,
        *,
        running: ingestion_job.IngestionJob,
        summary: IngestionRunSummary,
        sync_state_before: SourceSyncState | None,
        sync_state_after: SourceSyncState | None,
    ) -> data_source_types.IngestionJobMetadata:
        # running is intentionally kept generic because only one method in this class
        # needs metadata extraction and the concrete type is shared with sibling mixins.
        metadata = (
            data_source_types.IngestionJobMetadata.parse_optional(running.metadata)
            or data_source_types.IngestionJobMetadata()
        )
        executed_query = getattr(summary, "executed_query", None)
        if executed_query and isinstance(executed_query, str):
            metadata = metadata.model_copy(update={"executed_query": executed_query})

        query_generation_metadata = self._build_query_generation_metadata(summary)
        if query_generation_metadata is not None:
            metadata = metadata.model_copy(
                update={"query_generation": query_generation_metadata},
            )

        idempotency_metadata = self._build_idempotency_metadata(
            summary=summary,
            sync_state_before=sync_state_before,
            sync_state_after=sync_state_after,
        )
        if idempotency_metadata is not None:
            metadata = metadata.model_copy(update={"idempotency": idempotency_metadata})
        return metadata

    @staticmethod
    def _build_query_generation_metadata(
        summary: IngestionRunSummary,
    ) -> data_source_types.IngestionQueryGenerationMetadata | None:
        run_id = getattr(summary, "query_generation_run_id", None)
        model = getattr(summary, "query_generation_model", None)
        decision = getattr(summary, "query_generation_decision", None)
        confidence = getattr(summary, "query_generation_confidence", None)

        has_signal = any(
            value is not None for value in (run_id, model, decision, confidence)
        )
        if not has_signal:
            return None
        return data_source_types.IngestionQueryGenerationMetadata(
            run_id=run_id if isinstance(run_id, str) else None,
            model=model if isinstance(model, str) else None,
            decision=decision if isinstance(decision, str) else None,
            confidence=confidence if isinstance(confidence, float | int) else None,
        )

    def _build_idempotency_metadata(
        self: IngestionSchedulingService,
        *,
        summary: IngestionRunSummary,
        sync_state_before: SourceSyncState | None,
        sync_state_after: SourceSyncState | None,
    ) -> data_source_types.IngestionIdempotencyMetadata | None:
        query_signature = getattr(summary, "query_signature", None)
        if not isinstance(query_signature, str) or not query_signature.strip():
            query_signature = (
                sync_state_after.query_signature
                if sync_state_after is not None
                else (
                    sync_state_before.query_signature
                    if sync_state_before is not None
                    else None
                )
            )
        resolved_query_signature = (
            query_signature
            if isinstance(query_signature, str) and query_signature.strip()
            else None
        )
        resolved_checkpoint_kind = self._resolve_checkpoint_kind(
            raw_value=getattr(summary, "checkpoint_kind", None),
            fallback=(
                sync_state_after.checkpoint_kind
                if sync_state_after is not None
                else (
                    sync_state_before.checkpoint_kind
                    if sync_state_before is not None
                    else CheckpointKind.NONE
                )
            ),
        )

        checkpoint_before_raw = getattr(summary, "checkpoint_before", None)
        if isinstance(checkpoint_before_raw, dict):
            checkpoint_before = {
                str(key): to_json_value(value)
                for key, value in checkpoint_before_raw.items()
            }
        elif sync_state_before is not None:
            checkpoint_before = {
                str(key): to_json_value(value)
                for key, value in sync_state_before.checkpoint_payload.items()
            }
        else:
            checkpoint_before = None

        checkpoint_after_raw = getattr(summary, "checkpoint_after", None)
        if isinstance(checkpoint_after_raw, dict):
            checkpoint_after = {
                str(key): to_json_value(value)
                for key, value in checkpoint_after_raw.items()
            }
        elif sync_state_after is not None:
            checkpoint_after = {
                str(key): to_json_value(value)
                for key, value in sync_state_after.checkpoint_payload.items()
            }
        else:
            checkpoint_after = None

        new_records = self._int_summary_field(summary, "new_records")
        updated_records = self._int_summary_field(summary, "updated_records")
        unchanged_records = self._int_summary_field(summary, "unchanged_records")
        skipped_records = self._int_summary_field(summary, "skipped_records")

        has_signal = (
            resolved_query_signature is not None
            or resolved_checkpoint_kind != CheckpointKind.NONE
            or checkpoint_before is not None
            or checkpoint_after is not None
            or new_records > 0
            or updated_records > 0
            or unchanged_records > 0
            or skipped_records > 0
        )
        if not has_signal:
            return None

        return data_source_types.IngestionIdempotencyMetadata(
            query_signature=resolved_query_signature,
            checkpoint_kind=resolved_checkpoint_kind.value,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
            new_records=new_records,
            updated_records=updated_records,
            unchanged_records=unchanged_records,
            skipped_records=skipped_records,
        )

    @staticmethod
    def _int_summary_field(
        summary: IngestionRunSummary,
        field_name: str,
    ) -> int:
        raw_value = getattr(summary, field_name, 0)
        return raw_value if isinstance(raw_value, int) else 0
