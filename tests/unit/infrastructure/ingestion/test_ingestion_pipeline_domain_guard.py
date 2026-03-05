"""Domain guard coverage for ingestion pipeline record validation."""

from __future__ import annotations

from unittest.mock import Mock

from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.type_definitions.ingestion import IngestResult, RawRecord


def _build_pipeline(*, mapper: Mock) -> IngestionPipeline:
    return IngestionPipeline(
        mapper=mapper,
        normalizer=Mock(),
        resolver=Mock(),
        validator=Mock(),
        observation_service=Mock(),
        provenance_tracker=Mock(),
    )


def test_record_without_domain_context_passes_through() -> None:
    mapper = Mock()
    mapper.map.return_value = []
    pipeline = _build_pipeline(mapper=mapper)

    result: IngestResult = pipeline.run(
        [
            RawRecord(
                source_id="record-1",
                data={"pmid": "30769017", "title": "Study"},
                metadata={"type": "pubmed", "entity_type": "PUBLICATION"},
            ),
        ],
        research_space_id="space-1",
    )

    assert result.success is True
    assert result.errors == []
    assert mapper.map.call_count == 1


def test_record_with_domain_context_passes_through() -> None:
    mapper = Mock()
    mapper.map.return_value = []
    pipeline = _build_pipeline(mapper=mapper)

    result: IngestResult = pipeline.run(
        [
            RawRecord(
                source_id="record-2",
                data={"pmid": "30769017", "title": "Study"},
                metadata={
                    "type": "pubmed",
                    "entity_type": "PUBLICATION",
                    "domain_context": "clinical",
                },
            ),
        ],
        research_space_id="space-1",
    )

    assert result.success is True
    assert result.errors == []
    assert mapper.map.call_count == 1


def test_pubmed_record_with_domain_alias_is_normalized() -> None:
    mapper = Mock()
    mapper.map.return_value = []
    pipeline = _build_pipeline(mapper=mapper)

    result: IngestResult = pipeline.run(
        [
            RawRecord(
                source_id="record-3",
                data={"pmid": "30769017", "title": "Study"},
                metadata={
                    "type": "pubmed",
                    "entity_type": "PUBLICATION",
                    "domain": " Clinical ",
                },
            ),
        ],
        research_space_id="space-1",
    )

    assert result.success is True
    assert result.errors == []
    assert mapper.map.call_count == 1
    call_record = mapper.map.call_args.args[0]
    assert call_record.metadata["domain_context"] == "clinical"
