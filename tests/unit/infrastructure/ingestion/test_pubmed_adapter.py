"""Unit tests for PubMed ingestion source adapter metadata behavior."""

from src.infrastructure.ingestion.sources.pubmed import PubMedAdapter


def test_pubmed_adapter_sets_default_domain_context() -> None:
    adapter = PubMedAdapter()

    records = adapter.to_raw_records(
        [{"pmid": "30769017", "title": "Regulation of cardiac transcription"}],
        source_id="source-1",
    )

    assert len(records) == 1
    assert records[0].metadata["domain_context"] == "clinical"


def test_pubmed_adapter_uses_provided_domain_context() -> None:
    adapter = PubMedAdapter()

    records = adapter.to_raw_records(
        [{"pmid": "22541436", "title": "Systemic energy homeostasis"}],
        source_id="source-2",
        domain_context="Cardiology",
    )

    assert len(records) == 1
    assert records[0].metadata["domain_context"] == "cardiology"
