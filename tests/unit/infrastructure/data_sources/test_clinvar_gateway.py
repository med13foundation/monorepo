"""Tests for the ClinVar source gateway."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast
from unittest.mock import AsyncMock

import pytest

from src.domain.entities.data_source_configs import ClinVarQueryConfig
from src.infrastructure.data_sources.clinvar_gateway import ClinVarSourceGateway
from src.infrastructure.ingest.clinvar_ingestor import ClinVarFetchPage

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from src.infrastructure.ingest import ClinVarIngestor


class _StubIngestor:
    def __init__(self) -> None:
        self.fetch_data = AsyncMock(return_value=[])
        self.fetch_page = AsyncMock(
            return_value=ClinVarFetchPage(
                records=[{"clinvar_id": "1001"}],
                total_count=20,
                retstart=10,
                retmax=5,
                returned_count=5,
            ),
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, tb)


@pytest.mark.asyncio
async def test_gateway_passes_query_parameters() -> None:
    """Gateway should forward ClinVar configuration to the ingestor."""
    ingestor = _StubIngestor()
    ingestor_factory = cast("Callable[[], ClinVarIngestor]", lambda: ingestor)
    gateway = ClinVarSourceGateway(ingestor_factory=ingestor_factory)
    config = ClinVarQueryConfig(
        query="MED13 pathogenic variant",
        gene_symbol="MED13",
        variation_types=["single nucleotide variant"],
        clinical_significance=["Pathogenic"],
        max_results=77,
    )

    await gateway.fetch_records(config)

    ingestor.fetch_data.assert_awaited_once_with(
        gene_symbol="MED13",
        max_results=77,
        variation_type="single nucleotide variant",
        clinical_significance="Pathogenic",
    )


@pytest.mark.asyncio
async def test_gateway_incremental_fetch_uses_cursor_checkpoint() -> None:
    """Incremental fetch should use retstart and emit cursor checkpoint payload."""
    ingestor = _StubIngestor()
    ingestor_factory = cast("Callable[[], ClinVarIngestor]", lambda: ingestor)
    gateway = ClinVarSourceGateway(ingestor_factory=ingestor_factory)
    config = ClinVarQueryConfig(max_results=5)

    result = await gateway.fetch_records_incremental(
        config,
        checkpoint={"provider": "clinvar", "retstart": 10},
    )

    ingestor.fetch_page.assert_awaited_once_with(
        gene_symbol="MED13",
        max_results=5,
        retstart=10,
    )
    assert result.fetched_records == 5
    assert len(result.records) == 1
    assert result.checkpoint_kind.value == "cursor"
    assert result.checkpoint_after is not None
    assert result.checkpoint_after["provider"] == "clinvar"
    assert result.checkpoint_after["retstart"] == 15
    assert result.checkpoint_after["cycle_completed"] is False
