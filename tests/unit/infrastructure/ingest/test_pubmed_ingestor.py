"""Unit tests for PubMed ingestor open-access filtering behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.infrastructure.ingest.pubmed_ingestor import PubMedIngestor, PubMedSearchPage


@pytest.mark.asyncio
async def test_search_publications_uses_free_full_text_subset_filter() -> None:
    """Open-access search should include PubMed free-full-text subset filter."""
    ingestor = PubMedIngestor()
    ingestor._make_request = AsyncMock(
        return_value=Mock(
            json=Mock(
                return_value={
                    "esearchresult": {
                        "idlist": [],
                        "count": "0",
                        "retstart": "0",
                        "retmax": "10",
                    },
                },
            ),
        ),
    )

    await ingestor._search_publications("MED13", open_access_only=True)

    assert ingestor._make_request.await_count == 1
    call_kwargs = ingestor._make_request.await_args.kwargs
    params = call_kwargs["params"]
    assert isinstance(params, dict)
    term = params["term"]
    assert isinstance(term, str)
    assert '"free full text"[sb]' in term


@pytest.mark.asyncio
async def test_fetch_page_enforces_pmcid_for_open_access_records() -> None:
    """Open-access fetch should drop records that do not have a PMCID."""
    ingestor = PubMedIngestor()
    ingestor._search_publications = AsyncMock(
        return_value=PubMedSearchPage(
            article_ids=["100", "200"],
            total_count=2,
            retstart=0,
            retmax=2,
        ),
    )
    ingestor._fetch_article_details = AsyncMock(
        return_value=[
            {"pubmed_id": "100", "title": "No PMCID", "pmc_id": None},
            {"pubmed_id": "200", "title": "Has PMCID", "pmc_id": "PMC9999999"},
        ],
    )

    page = await ingestor.fetch_page(
        query="MED13",
        max_results=2,
        open_access_only=True,
    )

    assert page.total_count == 2
    assert page.returned_count == 2
    assert len(page.records) == 1
    assert page.records[0]["pubmed_id"] == "200"


@pytest.mark.asyncio
async def test_fetch_page_keeps_non_pmc_records_when_open_access_disabled() -> None:
    """When open-access filtering is disabled, PMCID should not be required."""
    ingestor = PubMedIngestor()
    ingestor._search_publications = AsyncMock(
        return_value=PubMedSearchPage(
            article_ids=["100", "200"],
            total_count=2,
            retstart=0,
            retmax=2,
        ),
    )
    ingestor._fetch_article_details = AsyncMock(
        return_value=[
            {"pubmed_id": "100", "title": "No PMCID", "pmc_id": None},
            {"pubmed_id": "200", "title": "Has PMCID", "pmc_id": "PMC9999999"},
        ],
    )

    page = await ingestor.fetch_page(
        query="MED13",
        max_results=2,
        open_access_only=False,
    )

    assert len(page.records) == 2


@pytest.mark.asyncio
async def test_fetch_article_details_extracts_pmcid_from_pubmed_data() -> None:
    """Parser should read PMCID/DOI from PubmedData ArticleIdList."""
    ingestor = PubMedIngestor()
    ingestor._make_request = AsyncMock(
        return_value=Mock(
            text="""<?xml version="1.0"?>
            <PubmedArticleSet>
                <PubmedArticle>
                    <MedlineCitation>
                        <PMID>12345678</PMID>
                        <Article>
                            <ArticleTitle>Sample title</ArticleTitle>
                        </Article>
                    </MedlineCitation>
                    <PubmedData>
                        <ArticleIdList>
                            <ArticleId IdType="doi">10.1000/example</ArticleId>
                            <ArticleId IdType="pmc">PMC1234567</ArticleId>
                        </ArticleIdList>
                    </PubmedData>
                </PubmedArticle>
            </PubmedArticleSet>""",
            headers={"date": "Tue, 03 Mar 2026 00:00:00 GMT"},
        ),
    )

    records = await ingestor._fetch_article_details(["12345678"])

    assert len(records) == 1
    assert records[0]["pubmed_id"] == "12345678"
    assert records[0]["doi"] == "10.1000/example"
    assert records[0]["pmc_id"] == "PMC1234567"
