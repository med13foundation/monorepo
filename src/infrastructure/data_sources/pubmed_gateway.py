"""Infrastructure gateway for PubMed data sources."""

from __future__ import annotations

from src.domain.entities.data_source_configs import PubMedQueryConfig  # noqa: TCH001
from src.domain.entities.source_sync_state import CheckpointKind
from src.domain.services.pubmed_ingestion import PubMedGateway, PubMedGatewayFetchResult
from src.infrastructure.ingest.pubmed_ingestor import PubMedIngestor
from src.type_definitions.common import JSONObject, JSONValue, RawRecord  # noqa: TCH001


class PubMedSourceGateway(PubMedGateway):
    """Adapter that executes PubMed queries per data source configuration."""

    def __init__(self, ingestor: PubMedIngestor | None = None) -> None:
        self._ingestor = ingestor or PubMedIngestor()

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

        raw_records = await self._ingestor.fetch_data(**params)
        return self._apply_relevance_threshold(raw_records, config.relevance_threshold)

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

        if hasattr(self._ingestor, "fetch_page"):
            page = await self._ingestor.fetch_page(**params)
            fetched_records = page.returned_count
            next_retstart = page.next_retstart if page.has_more else 0
            raw_records = list(page.records)
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

        filtered_records = self._apply_relevance_threshold(
            raw_records,
            config.relevance_threshold,
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
        }
        return PubMedGatewayFetchResult(
            records=filtered_records,
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

    def _apply_relevance_threshold(
        self,
        records: list[RawRecord],
        threshold: int,
    ) -> list[RawRecord]:
        if threshold <= 0:
            return records

        filtered: list[RawRecord] = []
        for record in records:
            relevance = record.get("med13_relevance")
            score = None
            if isinstance(relevance, dict):
                score_value = relevance.get("score")
                if isinstance(score_value, int | float):
                    score = int(score_value)
            if score is None or score >= threshold:
                filtered.append(record)
        return filtered
