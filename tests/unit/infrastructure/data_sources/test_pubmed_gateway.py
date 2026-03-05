"""Tests for the PubMed source gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from src.domain.agents.contracts.pubmed_relevance import PubMedRelevanceContract
from src.domain.entities.data_source_configs import PubMedQueryConfig
from src.infrastructure.data_sources.pubmed_gateway import PubMedSourceGateway
from src.infrastructure.ingest.pubmed_ingestor import PubMedFetchPage

if TYPE_CHECKING:
    from src.domain.agents.contexts.pubmed_relevance_context import (
        PubMedRelevanceContext,
    )


class StubPubMedRelevanceAgent:
    def __init__(
        self,
        outcomes: dict[str, PubMedRelevanceContract | Exception],
    ) -> None:
        self._outcomes = outcomes

    async def classify(
        self,
        context: PubMedRelevanceContext,
        *,
        model_id: str | None = None,
    ) -> PubMedRelevanceContract:
        _ = model_id
        pubmed_id = context.pubmed_id or "unknown"
        outcome = self._outcomes.get(pubmed_id)
        if outcome is None:
            msg = f"Missing stubbed relevance outcome for PMID {pubmed_id}"
            raise AssertionError(msg)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def close(self) -> None:
        return


@dataclass(frozen=True)
class _StubFullTextFetchResult:
    attempted_sources: tuple[str, ...]
    content_text: str | None
    acquisition_method: str
    source_url: str | None


class _RescueTestGateway(PubMedSourceGateway):
    def __init__(
        self,
        *,
        ingestor: AsyncMock,
        relevance_agent: StubPubMedRelevanceAgent,
        full_text_by_pubmed_id: dict[str, _StubFullTextFetchResult],
    ) -> None:
        super().__init__(ingestor=ingestor, relevance_agent=relevance_agent)
        self._full_text_by_pubmed_id = full_text_by_pubmed_id

    async def _fetch_open_access_full_text_for_record(  # type: ignore[override]
        self,
        record: dict[str, object],
    ) -> _StubFullTextFetchResult:
        pubmed_id_value = record.get("pubmed_id")
        if not isinstance(pubmed_id_value, str):
            return _StubFullTextFetchResult(
                attempted_sources=(),
                content_text=None,
                acquisition_method="skipped",
                source_url=None,
            )
        return self._full_text_by_pubmed_id.get(
            pubmed_id_value,
            _StubFullTextFetchResult(
                attempted_sources=(),
                content_text=None,
                acquisition_method="skipped",
                source_url=None,
            ),
        )


def _relevance_contract(
    *,
    relevance: str,
    confidence: float,
    rationale: str,
    query: str,
    run_id: str | None = None,
) -> PubMedRelevanceContract:
    return PubMedRelevanceContract(
        relevance=relevance,
        confidence_score=confidence,
        rationale=rationale,
        evidence=[],
        source_type="pubmed",
        query=query,
        agent_run_id=run_id,
    )


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
async def test_gateway_falls_back_when_threshold_filters_entire_batch() -> None:
    """Gateway should not return an empty batch when all scores miss threshold."""
    ingestor = AsyncMock()
    ingestor.fetch_data.return_value = [
        {
            "pubmed_id": "1",
            "med13_relevance": {"score": 1, "is_relevant": False},
        },
        {
            "pubmed_id": "2",
            "med13_relevance": {"score": 2, "is_relevant": False},
        },
    ]
    gateway = PubMedSourceGateway(ingestor=ingestor)
    config = PubMedQueryConfig(
        query="MED13",
        date_from=None,
        date_to=None,
        relevance_threshold=10,
    )

    records = await gateway.fetch_records(config)

    assert len(records) == 2
    assert {record["pubmed_id"] for record in records} == {"1", "2"}


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
    assert result.fetched_records == 1
    assert len(result.records) == 1
    assert result.checkpoint_kind.value == "cursor"
    assert result.checkpoint_after is not None
    assert result.checkpoint_after["provider"] == "pubmed"
    assert result.checkpoint_after["retstart"] == 0
    assert result.checkpoint_after["cycle_completed"] is True


@pytest.mark.asyncio
async def test_gateway_incremental_fetch_preserves_cursor_on_empty_parsed_page() -> (
    None
):
    """If ESearch returns IDs but parser yields zero records, retain cursor."""
    ingestor = AsyncMock()
    ingestor.fetch_page.return_value = PubMedFetchPage(
        records=[],
        total_count=126,
        retstart=20,
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
        checkpoint={"provider": "pubmed", "retstart": 20},
    )

    assert result.fetched_records == 0
    assert result.checkpoint_after is not None
    assert result.checkpoint_after["retstart"] == 20
    assert result.checkpoint_after["has_more"] is True
    assert result.checkpoint_after["cycle_completed"] is False
    assert result.checkpoint_after["cursor_preserved_due_to_empty_page"] is True


@pytest.mark.asyncio
async def test_gateway_filters_with_semantic_relevance_agent() -> None:
    """Semantic relevance agent should drive threshold filtering by meaning."""
    ingestor = AsyncMock()
    ingestor.fetch_data.return_value = [
        {
            "pubmed_id": "11",
            "title": "Mechanistic links in chromatin remodeling",
            "abstract": "Detailed mechanistic evidence about the target pathway.",
        },
        {
            "pubmed_id": "12",
            "title": "Unrelated diagnostics workflow",
            "abstract": "Administrative protocol update only.",
        },
    ]
    relevance_agent = StubPubMedRelevanceAgent(
        outcomes={
            "11": _relevance_contract(
                relevance="relevant",
                confidence=0.9,
                rationale="Directly addresses the query mechanism.",
                query="chromatin remodeling mechanisms",
                run_id="run-11",
            ),
            "12": _relevance_contract(
                relevance="non_relevant",
                confidence=0.9,
                rationale="No mechanistic relevance to the query.",
                query="chromatin remodeling mechanisms",
                run_id="run-12",
            ),
        },
    )
    gateway = PubMedSourceGateway(ingestor=ingestor, relevance_agent=relevance_agent)
    config = PubMedQueryConfig(
        query="chromatin remodeling mechanisms",
        date_from=None,
        date_to=None,
        relevance_threshold=5,
    )

    records = await gateway.fetch_records(config)

    assert len(records) == 1
    assert records[0]["pubmed_id"] == "11"
    semantic_relevance_raw = records[0].get("semantic_relevance")
    assert isinstance(semantic_relevance_raw, dict)
    assert semantic_relevance_raw.get("label") == "relevant"
    assert semantic_relevance_raw.get("agent_run_id") == "run-11"


@pytest.mark.asyncio
async def test_gateway_semantic_checkpoint_includes_filtered_pubmed_ids() -> None:
    """Incremental checkpoint should expose PMIDs filtered by semantic relevance."""
    ingestor = AsyncMock()
    ingestor.fetch_page.return_value = PubMedFetchPage(
        records=[
            {
                "pubmed_id": "111",
                "title": "Core pathway evidence",
                "abstract": "Direct support for the topic.",
            },
            {
                "pubmed_id": "222",
                "title": "Off-topic systems note",
                "abstract": "Irrelevant domain operational details.",
            },
        ],
        total_count=2,
        retstart=0,
        retmax=2,
        returned_count=2,
    )
    relevance_agent = StubPubMedRelevanceAgent(
        outcomes={
            "111": _relevance_contract(
                relevance="relevant",
                confidence=0.8,
                rationale="Directly aligned with requested topic.",
                query="query",
                run_id="run-111",
            ),
            "222": _relevance_contract(
                relevance="non_relevant",
                confidence=0.95,
                rationale="Does not address requested topic.",
                query="query",
                run_id="run-222",
            ),
        },
    )
    gateway = PubMedSourceGateway(
        ingestor=ingestor,
        relevance_agent=relevance_agent,
    )
    config = PubMedQueryConfig(
        query="query",
        date_from=None,
        date_to=None,
        relevance_threshold=5,
        max_results=2,
    )

    result = await gateway.fetch_records_incremental(config, checkpoint=None)

    assert len(result.records) == 1
    assert result.records[0]["pubmed_id"] == "111"
    assert result.checkpoint_after is not None
    assert result.checkpoint_after["semantic_relevance_filtering"] is True
    assert result.checkpoint_after["filtered_out_count"] == 1
    assert result.checkpoint_after["filtered_out_pubmed_ids"] == ["222"]


@pytest.mark.asyncio
async def test_gateway_semantic_relevance_rescue_lane_reinstates_full_text_hits() -> (
    None
):
    """Low-relevance records should be rescued when full text matches anchor terms."""
    ingestor = AsyncMock()
    ingestor.fetch_page.return_value = PubMedFetchPage(
        records=[
            {
                "pubmed_id": "111",
                "title": "Core MED13 findings",
                "abstract": "Directly relevant to MED13 signaling.",
                "pmc_id": "PMC1111111",
            },
            {
                "pubmed_id": "222",
                "title": "General uterine biology review",
                "abstract": "Broad review with limited abstract-level target detail.",
                "pmc_id": "PMC2222222",
            },
        ],
        total_count=2,
        retstart=0,
        retmax=2,
        returned_count=2,
    )
    relevance_agent = StubPubMedRelevanceAgent(
        outcomes={
            "111": _relevance_contract(
                relevance="relevant",
                confidence=0.9,
                rationale="Directly addresses MED13.",
                query="MED13",
                run_id="run-111",
            ),
            "222": _relevance_contract(
                relevance="non_relevant",
                confidence=0.95,
                rationale="Abstract appears tangential.",
                query="MED13",
                run_id="run-222",
            ),
        },
    )
    gateway = _RescueTestGateway(
        ingestor=ingestor,
        relevance_agent=relevance_agent,
        full_text_by_pubmed_id={
            "222": _StubFullTextFetchResult(
                attempted_sources=("pmc_oa:PMC2222222",),
                content_text="... discussion of MED13 in the kinase module ...",
                acquisition_method="pmc_oa",
                source_url="https://example.org/pmc2222222",
            ),
        },
    )
    config = PubMedQueryConfig(
        query="MED13",
        date_from=None,
        date_to=None,
        relevance_threshold=5,
        max_results=2,
    )

    result = await gateway.fetch_records_incremental(config, checkpoint=None)

    assert len(result.records) == 2
    assert {record["pubmed_id"] for record in result.records} == {"111", "222"}
    assert result.checkpoint_after is not None
    assert result.checkpoint_after["pre_rescue_filtered_out_count"] == 1
    assert result.checkpoint_after["filtered_out_count"] == 0
    assert result.checkpoint_after["full_text_rescue_attempted_count"] == 1
    assert result.checkpoint_after["full_text_rescued_count"] == 1
    assert result.checkpoint_after["full_text_rescued_pubmed_ids"] == ["222"]
