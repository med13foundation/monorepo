"""Tests for the ClinVar ingestion application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from src.application.services.clinvar_ingestion_service import ClinVarIngestionService
from src.domain.entities.user_data_source import (
    SourceConfiguration,
    SourceType,
    UserDataSource,
)
from src.domain.services.clinvar_ingestion import ClinVarGateway
from src.type_definitions.ingestion import IngestResult

if TYPE_CHECKING:
    from src.domain.entities.data_source_configs import ClinVarQueryConfig
    from src.type_definitions.common import RawRecord
    from src.type_definitions.ingestion import RawRecord as PipelineRawRecord


class StubGateway(ClinVarGateway):
    """Simple stub gateway returning pre-defined records."""

    def __init__(self, records: list[RawRecord]) -> None:
        self.records = records
        self.called = 0

    async def fetch_records(self, config: ClinVarQueryConfig) -> list[RawRecord]:
        assert config.gene_symbol == "MED13"
        self.called += 1
        return self.records


class StubPipeline:
    """In-memory ingestion pipeline test double."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[PipelineRawRecord], str]] = []

    def run(
        self,
        records: list[PipelineRawRecord],
        research_space_id: str,
    ) -> IngestResult:
        self.calls.append((records, research_space_id))
        return IngestResult(success=True, observations_created=len(records))


def _build_source() -> UserDataSource:
    return UserDataSource(
        id=uuid4(),
        owner_id=uuid4(),
        research_space_id=uuid4(),
        name="ClinVar Source",
        description="",
        source_type=SourceType.CLINVAR,
        template_id=None,
        configuration=SourceConfiguration(
            metadata={
                "query": "MED13 pathogenic variant",
                "gene_symbol": "MED13",
                "max_results": 5,
            },
        ),
        tags=[],
    )


@pytest.mark.asyncio
async def test_ingest_runs_pipeline_and_returns_summary() -> None:
    gateway = StubGateway(
        records=[
            {
                "clinvar_id": "1001",
                "parsed_data": {
                    "gene_symbol": "MED13",
                    "clinical_significance": "pathogenic",
                },
            },
            {
                "clinvar_id": "1002",
                "parsed_data": {
                    "gene_symbol": "MED13",
                    "clinical_significance": "likely_pathogenic",
                },
            },
        ],
    )
    pipeline = StubPipeline()
    service = ClinVarIngestionService(gateway=gateway, pipeline=pipeline)

    source = _build_source()
    summary = await service.ingest(source)

    assert gateway.called == 1
    assert len(pipeline.calls) == 1
    assert summary.source_id == source.id
    assert summary.fetched_records == 2
    assert summary.parsed_publications == 2
    assert summary.created_publications == 2
    assert summary.updated_publications == 0
    assert summary.executed_query == "MED13 pathogenic variant"


@pytest.mark.asyncio
async def test_rejects_non_clinvar_source() -> None:
    gateway = StubGateway(records=[])
    pipeline = StubPipeline()
    service = ClinVarIngestionService(gateway=gateway, pipeline=pipeline)

    source = _build_source().model_copy(update={"source_type": SourceType.API})

    with pytest.raises(ValueError):
        await service.ingest(source)
