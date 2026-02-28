"""Infrastructure gateway for PubMed data sources."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.entities.data_source_configs import PubMedQueryConfig  # noqa: TCH001
from src.domain.entities.source_sync_state import CheckpointKind
from src.domain.services.pubmed_ingestion import PubMedGateway, PubMedGatewayFetchResult
from src.infrastructure.ingest.pubmed_ingestor import PubMedIngestor
from src.type_definitions.common import JSONObject, JSONValue, RawRecord  # noqa: TCH001

if TYPE_CHECKING:
    from src.domain.agents.contracts.pubmed_relevance import PubMedRelevanceContract
    from src.domain.agents.ports.pubmed_relevance_port import PubMedRelevancePort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RelevanceFilterOutcome:
    records: list[RawRecord]
    filtered_out_pubmed_ids: list[str]
    semantic_filtering_enabled: bool


class PubMedSourceGateway(PubMedGateway):
    """Adapter that executes PubMed queries per data source configuration."""

    def __init__(
        self,
        ingestor: PubMedIngestor | None = None,
        *,
        relevance_agent: PubMedRelevancePort | None = None,
        relevance_model_id: str | None = None,
    ) -> None:
        self._ingestor = ingestor or PubMedIngestor()
        self._relevance_agent = relevance_agent
        self._relevance_model_id = relevance_model_id

    async def fetch_records(self, config: PubMedQueryConfig) -> list[RawRecord]:
        """Fetch PubMed records using per-source query parameters."""
        params: dict[str, JSONValue] = {
            "query": config.query,
            "publication_types": config.publication_types,
            "mindate": config.date_from,
            "maxdate": config.date_to,
            "publication_date_from": config.date_from,
            "max_results": config.max_results,
            "open_access_only": config.open_access_only,
        }
        if isinstance(config.pinned_pubmed_id, str) and config.pinned_pubmed_id.strip():
            params["pinned_pubmed_id"] = config.pinned_pubmed_id.strip()

        raw_records = await self._ingestor.fetch_data(**params)
        outcome = await self._apply_relevance_threshold(
            raw_records,
            config=config,
        )
        return outcome.records

    async def fetch_records_incremental(
        self,
        config: PubMedQueryConfig,
        *,
        checkpoint: JSONObject | None = None,
    ) -> PubMedGatewayFetchResult:
        """Fetch PubMed records with cursor-aware checkpoint semantics."""
        retstart = self._extract_retstart(checkpoint)
        params: dict[str, JSONValue] = {
            "query": config.query,
            "publication_types": config.publication_types,
            "mindate": config.date_from,
            "maxdate": config.date_to,
            "publication_date_from": config.date_from,
            "max_results": config.max_results,
            "retstart": retstart,
            "open_access_only": config.open_access_only,
        }
        if isinstance(config.pinned_pubmed_id, str) and config.pinned_pubmed_id.strip():
            params["pinned_pubmed_id"] = config.pinned_pubmed_id.strip()

        if hasattr(self._ingestor, "fetch_page"):
            page = await self._ingestor.fetch_page(**params)
            next_retstart = page.next_retstart if page.has_more else 0
            raw_records = list(page.records)
            fetched_records = len(raw_records)
            total_count = page.total_count
            page_size = page.retmax
            has_more = page.has_more
            returned_count = page.returned_count
        else:
            raw_records = await self._ingestor.fetch_data(**params)
            fetched_records = len(raw_records)
            total_count = fetched_records
            page_size = max(config.max_results, 1)
            next_retstart = retstart + fetched_records if fetched_records else 0
            has_more = False
            returned_count = fetched_records

        outcome = await self._apply_relevance_threshold(
            raw_records,
            config=config,
        )
        checkpoint_after: JSONObject = {
            "provider": "pubmed",
            "cursor_type": "retstart",
            "retstart": next_retstart,
            "retmax": page_size,
            "total_count": total_count,
            "returned_count": returned_count,
            "has_more": has_more,
            "cycle_completed": not has_more,
            "relevance_threshold": config.relevance_threshold,
            "open_access_only": config.open_access_only,
            "semantic_relevance_filtering": outcome.semantic_filtering_enabled,
            "filtered_out_count": len(outcome.filtered_out_pubmed_ids),
            "filtered_out_pubmed_ids": outcome.filtered_out_pubmed_ids,
        }
        return PubMedGatewayFetchResult(
            records=outcome.records,
            fetched_records=fetched_records,
            checkpoint_after=checkpoint_after,
            checkpoint_kind=CheckpointKind.CURSOR,
        )

    @staticmethod
    def _extract_retstart(checkpoint: JSONObject | None) -> int:
        """Resolve provider cursor from checkpoint payload."""
        if checkpoint is None:
            return 0
        provider = checkpoint.get("provider")
        if isinstance(provider, str) and provider.lower() != "pubmed":
            return 0
        retstart_raw = checkpoint.get("retstart")
        if isinstance(retstart_raw, int) and retstart_raw >= 0:
            return retstart_raw
        if isinstance(retstart_raw, float):
            candidate = int(retstart_raw)
            return max(candidate, 0)
        if isinstance(retstart_raw, str) and retstart_raw.isdigit():
            return int(retstart_raw)
        return 0

    async def _apply_relevance_threshold(
        self,
        records: list[RawRecord],
        *,
        config: PubMedQueryConfig,
    ) -> _RelevanceFilterOutcome:
        threshold = config.relevance_threshold
        if self._relevance_agent is not None and threshold > 0:
            return await self._apply_semantic_relevance_threshold(
                records=records,
                threshold=threshold,
                config=config,
            )

        if threshold <= 0:
            return _RelevanceFilterOutcome(
                records=records,
                filtered_out_pubmed_ids=[],
                semantic_filtering_enabled=False,
            )

        filtered: list[RawRecord] = []
        filtered_out_pubmed_ids: list[str] = []
        for record in records:
            relevance = record.get("med13_relevance")
            score = None
            if isinstance(relevance, dict):
                score_value = relevance.get("score")
                if isinstance(score_value, int | float):
                    score = int(score_value)
            if score is None or score >= threshold:
                filtered.append(record)
            else:
                pubmed_id = self._extract_pubmed_id(record)
                if pubmed_id is not None:
                    filtered_out_pubmed_ids.append(pubmed_id)
        if filtered:
            return _RelevanceFilterOutcome(
                records=filtered,
                filtered_out_pubmed_ids=filtered_out_pubmed_ids,
                semantic_filtering_enabled=False,
            )
        logger.warning(
            (
                "PubMed relevance threshold removed all fetched records; "
                "falling back to unfiltered records"
            ),
            extra={
                "threshold": threshold,
                "raw_record_count": len(records),
                "filtered_out_pubmed_ids": filtered_out_pubmed_ids,
            },
        )
        return _RelevanceFilterOutcome(
            records=records,
            filtered_out_pubmed_ids=filtered_out_pubmed_ids,
            semantic_filtering_enabled=False,
        )

    async def _apply_semantic_relevance_threshold(
        self,
        *,
        records: list[RawRecord],
        threshold: int,
        config: PubMedQueryConfig,
    ) -> _RelevanceFilterOutcome:
        classification_tasks = [
            self._classify_record_relevance(record=record, config=config)
            for record in records
        ]
        classification_results = await asyncio.gather(
            *classification_tasks,
            return_exceptions=True,
        )

        filtered_records: list[RawRecord] = []
        filtered_out_pubmed_ids: list[str] = []
        classification_errors = 0
        classification_error_pubmed_ids: list[str] = []

        for index, record in enumerate(records):
            outcome = classification_results[index]
            if isinstance(outcome, BaseException):
                classification_errors += 1
                pubmed_id = self._extract_pubmed_id(record)
                if pubmed_id is not None:
                    classification_error_pubmed_ids.append(pubmed_id)
                self._set_semantic_relevance_metadata(
                    record=record,
                    label="unclassified",
                    confidence=0.0,
                    rationale=f"classification_failed:{type(outcome).__name__}",
                    agent_run_id=None,
                )
                filtered_records.append(record)
                continue

            label = outcome.relevance
            confidence = max(0.0, min(1.0, float(outcome.confidence_score)))
            score = self._semantic_relevance_score(label=label, confidence=confidence)
            self._set_semantic_relevance_metadata(
                record=record,
                label=label,
                confidence=confidence,
                rationale=outcome.rationale,
                agent_run_id=outcome.agent_run_id,
            )
            if score >= threshold:
                filtered_records.append(record)
                continue

            pubmed_id = self._extract_pubmed_id(record)
            if pubmed_id is not None:
                filtered_out_pubmed_ids.append(pubmed_id)

        if filtered_records:
            logger.info(
                "PubMed semantic relevance filtering completed",
                extra={
                    "threshold": threshold,
                    "raw_record_count": len(records),
                    "kept_count": len(filtered_records),
                    "filtered_out_count": len(filtered_out_pubmed_ids),
                    "classification_errors": classification_errors,
                    "classification_error_pubmed_ids": classification_error_pubmed_ids,
                },
            )
            return _RelevanceFilterOutcome(
                records=filtered_records,
                filtered_out_pubmed_ids=filtered_out_pubmed_ids,
                semantic_filtering_enabled=True,
            )

        logger.warning(
            (
                "PubMed semantic relevance filtering removed all fetched records; "
                "falling back to unfiltered records"
            ),
            extra={
                "threshold": threshold,
                "raw_record_count": len(records),
                "filtered_out_pubmed_ids": filtered_out_pubmed_ids,
                "classification_errors": classification_errors,
                "classification_error_pubmed_ids": classification_error_pubmed_ids,
            },
        )
        return _RelevanceFilterOutcome(
            records=records,
            filtered_out_pubmed_ids=filtered_out_pubmed_ids,
            semantic_filtering_enabled=True,
        )

    async def _classify_record_relevance(
        self,
        *,
        record: RawRecord,
        config: PubMedQueryConfig,
    ) -> PubMedRelevanceContract:
        if self._relevance_agent is None:
            msg = "Semantic relevance classifier is not configured."
            raise RuntimeError(msg)
        title_raw = record.get("title")
        abstract_raw = record.get("abstract")
        title = title_raw.strip() if isinstance(title_raw, str) else ""
        abstract = abstract_raw.strip() if isinstance(abstract_raw, str) else ""
        if not title and not abstract:
            msg = "Record has neither title nor abstract for semantic relevance."
            raise ValueError(msg)

        from src.domain.agents.contexts.pubmed_relevance_context import (
            PubMedRelevanceContext,
        )

        context = PubMedRelevanceContext(
            source_type="pubmed",
            query=config.query,
            title=title or None,
            abstract=abstract or None,
            domain_context=config.domain_context,
            pubmed_id=self._extract_pubmed_id(record),
        )
        return await self._relevance_agent.classify(
            context,
            model_id=self._relevance_model_id,
        )

    @staticmethod
    def _semantic_relevance_score(*, label: str, confidence: float) -> int:
        if label != "relevant":
            return 0
        normalized_confidence = max(0.0, min(1.0, confidence))
        return int(round(normalized_confidence * 10.0))

    @staticmethod
    def _set_semantic_relevance_metadata(
        *,
        record: RawRecord,
        label: str,
        confidence: float,
        rationale: str,
        agent_run_id: str | None,
    ) -> None:
        record["semantic_relevance"] = {
            "label": label,
            "confidence": confidence,
            "rationale": rationale,
            "agent_run_id": agent_run_id,
        }

    @staticmethod
    def _extract_pubmed_id(record: RawRecord) -> str | None:
        for key in ("pmid", "pubmed_id"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
        return None
