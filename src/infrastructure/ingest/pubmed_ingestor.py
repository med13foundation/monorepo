"""
PubMed API client for MED13 Resource Library.
Fetches scientific literature and publication data from PubMed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from .base_ingestor import BaseIngestor
from .pubmed_record_parser_mixin import PubMedRecordParserMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.type_definitions.common import JSONValue, RawRecord


@dataclass(frozen=True)
class PubMedSearchPage:
    """Search-stage page metadata returned by ESearch."""

    article_ids: list[str]
    total_count: int
    retstart: int
    retmax: int

    @property
    def returned_count(self) -> int:
        """Number of IDs returned in this page."""
        return len(self.article_ids)


@dataclass(frozen=True)
class PubMedFetchPage:
    """Fetch-stage result including records and cursor metadata."""

    records: list[RawRecord]
    total_count: int
    retstart: int
    retmax: int
    returned_count: int

    @property
    def next_retstart(self) -> int:
        """Cursor offset for the next page."""
        return self.retstart + self.returned_count

    @property
    def has_more(self) -> bool:
        """Whether additional pages are available."""
        return self.next_retstart < self.total_count


class PubMedIngestor(BaseIngestor, PubMedRecordParserMixin):
    """
    PubMed API client for fetching scientific literature data.

    PubMed provides access to biomedical literature citations and abstracts.
    This ingestor focuses on publications related to MED13 gene and
    associated conditions.
    """

    def __init__(self) -> None:
        super().__init__(
            source_name="pubmed",
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            requests_per_minute=10,  # NCBI limits: 10 requests per second
            timeout_seconds=60,  # PubMed can be slow
        )

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Fetch PubMed data for specified search query.

        Args:
            query: Search query (default: MED13)
            **kwargs: Additional search parameters

        Returns:
            List of PubMed article records
        """
        page = await self.fetch_page(**kwargs)
        return page.records

    async def fetch_page(self, **kwargs: JSONValue) -> PubMedFetchPage:
        """Fetch one PubMed page with explicit cursor metadata."""
        pinned_pubmed_id_raw = kwargs.get("pinned_pubmed_id")
        if isinstance(pinned_pubmed_id_raw, str) and pinned_pubmed_id_raw.strip():
            pinned_pubmed_id = pinned_pubmed_id_raw.strip()
            records = await self._fetch_article_details([pinned_pubmed_id])
            retmax = max(self._coerce_int(kwargs.get("max_results"), 1), 1)
            total_count = 1 if records else 0
            return PubMedFetchPage(
                records=records,
                total_count=total_count,
                retstart=0,
                retmax=retmax,
                returned_count=len(records),
            )

        # Step 1: Search for publications
        query_value = kwargs.get("query")
        query = query_value if isinstance(query_value, str) else "MED13"

        search_kwargs = dict(kwargs)
        search_kwargs.pop("query", None)

        search_page = await self._search_publications(query, **search_kwargs)
        article_ids = list(search_page.article_ids)
        if not article_ids:
            return PubMedFetchPage(
                records=[],
                total_count=search_page.total_count,
                retstart=search_page.retstart,
                retmax=search_page.retmax,
                returned_count=0,
            )

        # Step 2: Fetch detailed records in batches
        all_records: list[RawRecord] = []
        batch_size = 50  # PubMed API limit

        for i in range(0, len(article_ids), batch_size):
            batch_ids = article_ids[i : i + batch_size]
            batch_records = await self._fetch_article_details(batch_ids)
            all_records.extend(batch_records)

            # Small delay between batches
            await asyncio.sleep(0.1)

        return PubMedFetchPage(
            records=all_records,
            total_count=search_page.total_count,
            retstart=search_page.retstart,
            retmax=search_page.retmax,
            returned_count=search_page.returned_count,
        )

    async def _search_publications(
        self,
        query: str,
        **kwargs: JSONValue,
    ) -> PubMedSearchPage:
        """
        Search PubMed for publications matching the query.

        Args:
            query: PubMed search query
            **kwargs: Additional search parameters

        Returns:
            List of PubMed article IDs
        """
        # Build comprehensive search query
        query_terms = [query]

        # Add filters if provided
        publication_date_from = kwargs.get("publication_date_from")
        if isinstance(publication_date_from, str):
            query_terms.append(f"{publication_date_from}[pdat]")

        publication_types = kwargs.get("publication_types")
        if isinstance(publication_types, list):
            pub_types = " OR ".join(
                f'"{pt}"[pt]' for pt in publication_types if isinstance(pt, str)
            )
            if pub_types:
                query_terms.append(f"({pub_types})")

        if self._coerce_bool(kwargs.get("open_access_only"), default=True):
            query_terms.append(
                '("open access"[filter] OR "loattrfree full text"[sb])',
            )

        full_query = " AND ".join(f"({term})" for term in query_terms)

        # Use ESearch to find relevant records
        mindate_value = kwargs.get("mindate")
        maxdate_value = kwargs.get("maxdate")

        retstart = max(self._coerce_int(kwargs.get("retstart"), 0), 0)
        retmax = max(self._coerce_int(kwargs.get("max_results"), 500), 1)
        params: dict[str, str | int | float | bool | None] = {
            "db": "pubmed",
            "term": full_query,
            "retmode": "json",
            "retstart": retstart,
            "retmax": retmax,
            "sort": "relevance",
            "datetype": "pdat",
            "mindate": mindate_value if isinstance(mindate_value, str) else None,
            "maxdate": maxdate_value if isinstance(maxdate_value, str) else None,
        }

        response = await self._make_request("GET", "esearch.fcgi", params=params)
        data = self._ensure_raw_record(response.json())

        # Extract article IDs from search results
        esearch_section = data.get("esearchresult")
        if not isinstance(esearch_section, dict):
            return PubMedSearchPage(
                article_ids=[],
                total_count=0,
                retstart=retstart,
                retmax=retmax,
            )
        response_total_count = self._coerce_int(esearch_section.get("count"), 0)
        response_retstart = self._coerce_int(esearch_section.get("retstart"), retstart)
        response_retmax = self._coerce_int(esearch_section.get("retmax"), retmax)
        id_list = esearch_section.get("idlist", [])
        if not isinstance(id_list, list):
            return PubMedSearchPage(
                article_ids=[],
                total_count=response_total_count,
                retstart=response_retstart,
                retmax=response_retmax,
            )
        return PubMedSearchPage(
            article_ids=[str(aid) for aid in id_list],
            total_count=response_total_count,
            retstart=response_retstart,
            retmax=response_retmax,
        )

    async def _fetch_article_details(
        self,
        article_ids: list[str],
    ) -> list[RawRecord]:
        """
        Fetch detailed PubMed records for given article IDs.

        Args:
            article_ids: List of PubMed article IDs

        Returns:
            List of detailed article records
        """
        if not article_ids:
            return []

        id_str = ",".join(article_ids)

        # Get detailed records using EFetch
        params = {
            "db": "pubmed",
            "id": id_str,
            "rettype": "medline",
            "retmode": "xml",
        }

        response = await self._make_request("GET", "efetch.fcgi", params=params)

        # Parse XML response
        xml_content = response.text
        records = self._parse_pubmed_xml(xml_content)

        # Add source metadata
        for record in records:
            record.update(
                {
                    "pubmed_ids": article_ids,
                    "source": "pubmed",
                    "fetched_at": response.headers.get("date", ""),
                },
            )

        return records

    async def fetch_med13_publications(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Convenience method to fetch MED13-related publications.

        Args:
            **kwargs: Additional search parameters

        Returns:
            List of MED13-related publication records
        """
        records = await self.fetch_data(query="MED13", **kwargs)

        # Filter for highly relevant publications
        relevant_records: list[RawRecord] = []
        for record in records:
            relevance = record.get("med13_relevance")
            if isinstance(relevance, dict) and relevance.get("is_relevant", False):
                relevant_records.append(record)
        return relevant_records

    async def fetch_recent_publications(
        self,
        days_back: int = 365,
        **kwargs: JSONValue,
    ) -> list[RawRecord]:
        """
        Fetch recent publications related to MED13.

        Args:
            days_back: Number of days to look back
            **kwargs: Additional search parameters

        Returns:
            List of recent publication records
        """
        # Calculate date range
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days_back)

        kwargs["mindate"] = start_date.strftime("%Y/%m/%d")
        kwargs["maxdate"] = end_date.strftime("%Y/%m/%d")

        return await self.fetch_med13_publications(**kwargs)

    @staticmethod
    def _coerce_int(value: JSONValue | None, default: int) -> int:
        """Convert JSON value to integer range."""
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return default

    @staticmethod
    def _coerce_bool(value: JSONValue | None, *, default: bool) -> bool:
        """Convert JSON value to bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default
