"""Tests for the PubMed source gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.domain.entities.data_source_configs import PubMedQueryConfig
from src.infrastructure.data_sources.pubmed_gateway import PubMedSourceGateway
from src.infrastructure.ingest.pubmed_ingestor import PubMedFetchPage


@pytest.mark.asyncio
async def test_gateway_passes_query_parameters() -> None:
    """Gateway should forward per-source configuration to the ingestor."""
    ingestor = AsyncMock()
    ingestor.fetch_data.return_value = []
    gateway = PubMedSourceGateway(ingestor=ingestor)
    config = PubMedQueryConfig(
        query="BRCA1",
        date_from="2023/01/01",
        date_to="2024/01/01",
        publication_types=["journal_article"],
        max_results=123,
        relevance_threshold=3,
    )

    await gateway.fetch_records(config)

    ingestor.fetch_data.assert_awaited_once_with(
        query="BRCA1",
        publication_types=["journal_article"],
        mindate="2023/01/01",
        maxdate="2024/01/01",
        publication_date_from="2023/01/01",
        max_results=123,
        open_access_only=True,
    )


@pytest.mark.asyncio
async def test_gateway_filters_by_relevance_threshold() -> None:
    """Records below the per-source relevance threshold should be excluded."""
    ingestor = AsyncMock()
    ingestor.fetch_data.return_value = [
        {
            "pubmed_id": "1",
            "med13_relevance": {"score": 2, "is_relevant": False},
        },
        {
            "pubmed_id": "2",
            "med13_relevance": {"score": 7, "is_relevant": True},
        },
    ]
    gateway = PubMedSourceGateway(ingestor=ingestor)
    config = PubMedQueryConfig(
        query="MED13",
        date_from=None,
        date_to=None,
        relevance_threshold=5,
    )

    records = await gateway.fetch_records(config)

    assert len(records) == 1
    assert records[0]["pubmed_id"] == "2"


@pytest.mark.asyncio
async def test_gateway_incremental_fetch_uses_cursor_checkpoint() -> None:
    """Incremental fetch should use retstart and return cursor checkpoint metadata."""
    ingestor = AsyncMock()
    ingestor.fetch_page.return_value = PubMedFetchPage(
        records=[
            {
                "pubmed_id": "11",
                "med13_relevance": {"score": 8, "is_relevant": True},
            },
        ],
        total_count=15,
        retstart=10,
        retmax=5,
        returned_count=5,
    )
    gateway = PubMedSourceGateway(ingestor=ingestor)
    config = PubMedQueryConfig(
        query="MED13",
        date_from=None,
        date_to=None,
        relevance_threshold=0,
        max_results=5,
    )

    result = await gateway.fetch_records_incremental(
        config,
        checkpoint={"provider": "pubmed", "retstart": 10},
    )

    ingestor.fetch_page.assert_awaited_once_with(
        query="MED13",
        publication_types=None,
        mindate=None,
        maxdate=None,
        publication_date_from=None,
        max_results=5,
        retstart=10,
        open_access_only=True,
    )
    assert result.fetched_records == 5
    assert len(result.records) == 1
    assert result.checkpoint_kind.value == "cursor"
    assert result.checkpoint_after is not None
    assert result.checkpoint_after["provider"] == "pubmed"
    assert result.checkpoint_after["retstart"] == 0
    assert result.checkpoint_after["cycle_completed"] is True
