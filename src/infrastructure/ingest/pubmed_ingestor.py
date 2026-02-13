"""
PubMed API client for MED13 Resource Library.
Fetches scientific literature and publication data from PubMed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from defusedxml import ElementTree

from .base_ingestor import BaseIngestor

if TYPE_CHECKING:  # pragma: no cover - typing only
    from xml.etree.ElementTree import Element  # nosec B405

    from src.type_definitions.common import JSONValue, RawRecord

# Relevance threshold constant
RELEVANCE_THRESHOLD: int = 5


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


class PubMedIngestor(BaseIngestor):
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

    def _parse_pubmed_xml(self, xml_content: str) -> list[RawRecord]:
        """
        Parse PubMed XML response into structured data.

        Args:
            xml_content: Raw XML response

        Returns:
            List of parsed article records
        """
        try:
            root = ElementTree.fromstring(xml_content)
            records: list[RawRecord] = []

            # PubMed XML structure: MedlineCitation elements
            for citation in root.findall(".//MedlineCitation"):
                record = self._parse_single_citation(citation)
                if record:
                    records.append(record)

        except Exception as e:  # noqa: BLE001
            # Return error record for debugging
            return [
                {
                    "parsing_error": str(e),
                    "raw_xml": xml_content[:1000],  # First 1000 chars for debugging
                },
            ]
        else:
            return records

    def _parse_single_citation(self, citation: Element) -> RawRecord | None:
        """
        Parse a single MedlineCitation element.

        Args:
            citation: XML element containing citation data

        Returns:
            Parsed article record
        """
        try:
            # Extract PMID
            pmid_elem = citation.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else None

            if not pmid:
                return None

            # Extract basic metadata
            record: RawRecord = {
                "pubmed_id": pmid,
                "title": self._extract_text(citation, ".//ArticleTitle"),
                "abstract": self._extract_text(citation, ".//AbstractText"),
                "journal": self._extract_journal_info(citation),
                "authors": self._extract_authors(citation),
                "publication_date": self._extract_publication_date(citation),
                "publication_types": self._extract_publication_types(citation),
                "keywords": self._extract_keywords(citation),
                "doi": self._extract_doi(citation),
                "pmc_id": self._extract_pmc_id(citation),
            }

            # Extract MED13-specific information
            record["med13_relevance"] = self._assess_med13_relevance(record)

        except Exception:  # noqa: BLE001
            return None
        else:
            return record

    def _extract_text(self, element: Element, xpath: str) -> str | None:
        """Extract text content from XML element."""
        elem = element.find(xpath)
        return elem.text.strip() if elem is not None and elem.text else None

    def _extract_journal_info(
        self,
        citation: Element,
    ) -> dict[str, str | None] | None:
        """Extract journal information."""
        journal_elem = citation.find(".//Journal")
        if journal_elem is None:
            return None

        return {
            "title": self._extract_text(journal_elem, ".//Title"),
            "iso_abbreviation": self._extract_text(journal_elem, ".//ISOAbbreviation"),
            "issn": self._extract_text(journal_elem, ".//ISSN"),
        }

    def _extract_authors(self, citation: Element) -> list[dict[str, str | None]]:
        """Extract author information."""
        authors: list[dict[str, str | None]] = []
        for author_elem in citation.findall(".//Author"):
            author = {
                "last_name": self._extract_text(author_elem, ".//LastName"),
                "first_name": self._extract_text(author_elem, ".//ForeName"),
                "initials": self._extract_text(author_elem, ".//Initials"),
                "affiliation": self._extract_text(
                    author_elem,
                    ".//AffiliationInfo/Affiliation",
                ),
            }
            if author["last_name"]:  # Only include if we have at least a last name
                authors.append(author)

        return authors

    def _extract_publication_date(self, citation: Element) -> str | None:
        """Extract publication date."""
        # Try different date fields in order of preference
        date_fields = [
            ".//PubDate",
            ".//Article/Journal/JournalIssue/PubDate",
        ]

        for xpath in date_fields:
            date_elem = citation.find(xpath)
            if date_elem is not None:
                # Extract year, month, day
                year = self._extract_text(date_elem, ".//Year")
                month = self._extract_text(date_elem, ".//Month")
                day = self._extract_text(date_elem, ".//Day")

                if year:
                    date_parts = [year]
                    if month:
                        date_parts.append(month)
                    if day:
                        date_parts.append(day)
                    return "-".join(date_parts)

        return None

    def _extract_publication_types(self, citation: Element) -> list[str]:
        """Extract publication types."""
        return [
            type_elem.text.strip()
            for type_elem in citation.findall(".//PublicationType")
            if type_elem.text
        ]

    def _extract_keywords(self, citation: Element) -> list[str]:
        """Extract keywords."""
        return [
            kw_elem.text.strip()
            for kw_elem in citation.findall(".//Keyword")
            if kw_elem.text
        ]

    def _extract_doi(self, citation: Element) -> str | None:
        """Extract DOI if available."""
        # DOI is typically in ArticleId elements
        for id_elem in citation.findall(".//ArticleId"):
            id_type = id_elem.get("IdType")
            if id_type == "doi" and id_elem.text:
                return id_elem.text.strip()
        return None

    def _extract_pmc_id(self, citation: Element) -> str | None:
        """Extract PMC ID if available."""
        for id_elem in citation.findall(".//ArticleId"):
            id_type = id_elem.get("IdType")
            if id_type == "pmc" and id_elem.text:
                return id_elem.text.strip()
        return None

    def _assess_med13_relevance(self, record: RawRecord) -> RawRecord:
        """
        Assess how relevant this publication is to MED13 research.

        Args:
            record: Parsed publication record

        Returns:
            Relevance assessment
        """
        relevance_score = 0
        reasons = []

        # Check title for MED13 mentions
        title_value = record.get("title") or ""
        title = (
            title_value.lower()
            if isinstance(title_value, str)
            else str(title_value).lower()
        )
        if "med13" in title:
            relevance_score += 10
            reasons.append("MED13 in title")

        # Check abstract for MED13 mentions
        abstract_value = record.get("abstract") or ""
        abstract = (
            abstract_value.lower()
            if isinstance(abstract_value, str)
            else str(abstract_value).lower()
        )
        if "med13" in abstract:
            relevance_score += 5
            reasons.append("MED13 in abstract")

        # Check keywords
        keywords: list[str] = []
        keywords_raw = record.get("keywords")
        if isinstance(keywords_raw, list):
            keywords = [kw.lower() for kw in keywords_raw if isinstance(kw, str)]
        med13_keywords = [kw for kw in keywords if "med13" in kw]
        if med13_keywords:
            relevance_score += 3
            reasons.append(f"MED13 keywords: {', '.join(med13_keywords)}")

        return {
            "score": relevance_score,
            "reasons": reasons,
            "is_relevant": relevance_score >= RELEVANCE_THRESHOLD,
        }

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
