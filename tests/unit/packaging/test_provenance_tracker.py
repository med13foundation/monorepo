from __future__ import annotations

"""
Tests for ProvenanceTracker with comprehensive type safety.

Tests cover all critical business logic for data provenance tracking,
including serialization, file writing, and metadata enrichment.
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from src.application.packaging.provenance.tracker import ProvenanceTracker
from src.domain.value_objects.provenance import DataSource, Provenance

if TYPE_CHECKING:
    from pathlib import Path

    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]


class TestProvenanceTracker:
    """Comprehensive test suite for ProvenanceTracker."""

    @pytest.fixture
    def sample_provenance_records(self) -> list[Provenance]:
        """Create sample provenance records for testing."""
        return [
            Provenance(
                source=DataSource.CLINVAR,
                source_version="2024.01",
                source_url="https://www.ncbi.nlm.nih.gov/clinvar/",
                acquired_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
                acquired_by="ingestion-service",
                processing_steps=["parsed_xml", "normalized_variants"],
                quality_score=0.95,
                validation_status="validated",
                metadata={"record_count": 1234},
            ),
            Provenance(
                source=DataSource.PUBMED,
                source_version="2024.01.01",
                source_url="https://pubmed.ncbi.nlm.nih.gov/",
                acquired_at=datetime(2024, 1, 16, 14, 45, tzinfo=UTC),
                acquired_by="ingestion-service",
                processing_steps=["fetched_abstracts", "extracted_evidence"],
                quality_score=0.88,
                validation_status="validated",
                metadata={"publication_count": 567},
            ),
            Provenance(
                source=DataSource.UNIPROT,
                source_version="2024_01",
                source_url="https://www.uniprot.org/",
                acquired_at=datetime(2024, 1, 17, 9, 15, tzinfo=UTC),
                acquired_by="ingestion-service",
                processing_steps=["parsed_fasta", "mapped_sequences"],
                quality_score=None,  # Test None handling
                validation_status="pending",
                metadata={},
            ),
        ]

    @pytest.fixture
    def minimal_provenance_records(self) -> list[Provenance]:
        """Create minimal provenance records with required fields only."""
        return [
            Provenance(
                source=DataSource.CLINVAR,
                acquired_by="test-user",
                processing_steps=[],
                validation_status="pending",
            ),
            Provenance(
                source=DataSource.MANUAL,
                acquired_by="researcher",
                processing_steps=["manual_review"],
                validation_status="validated",
            ),
        ]

    class TestSerializeProvenance:
        """Test provenance serialization functionality."""

        def test_serialize_complete_provenance_records(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test serialization of complete provenance records."""
            result = ProvenanceTracker.serialize_provenance(sample_provenance_records)

            assert isinstance(result, dict)
            assert "sources" in result
            assert isinstance(result["sources"], list)
            assert len(result["sources"]) == 3

            # Check first source (ClinVar)
            clinvar_source = result["sources"][0]
            assert clinvar_source["@type"] == "DataDownload"
            assert clinvar_source["name"] == "clinvar"
            assert clinvar_source["url"] == "https://www.ncbi.nlm.nih.gov/clinvar/"
            assert clinvar_source["version"] == "2024.01"
            assert clinvar_source["datePublished"] == "2024-01-15T10:30:00+00:00"
            assert clinvar_source["processingSteps"] == [
                "parsed_xml",
                "normalized_variants",
            ]
            assert clinvar_source["qualityScore"] == 0.95
            assert clinvar_source["validationStatus"] == "validated"

            # Check second source (PubMed)
            pubmed_source = result["sources"][1]
            assert pubmed_source["@type"] == "DataDownload"
            assert pubmed_source["name"] == "pubmed"
            assert pubmed_source["url"] == "https://pubmed.ncbi.nlm.nih.gov/"
            assert pubmed_source["version"] == "2024.01.01"
            assert pubmed_source["processingSteps"] == [
                "fetched_abstracts",
                "extracted_evidence",
            ]
            assert pubmed_source["qualityScore"] == 0.88
            assert pubmed_source["validationStatus"] == "validated"

            # Check third source (UniProt) - None handling
            uniprot_source = result["sources"][2]
            assert uniprot_source["@type"] == "DataDownload"
            assert uniprot_source["name"] == "uniprot"
            assert uniprot_source["url"] == "https://www.uniprot.org/"
            assert uniprot_source["version"] == "2024_01"
            assert uniprot_source["processingSteps"] == [
                "parsed_fasta",
                "mapped_sequences",
            ]
            assert "qualityScore" not in uniprot_source  # None values should be omitted
            assert uniprot_source["validationStatus"] == "pending"

        def test_serialize_minimal_provenance_records(
            self,
            minimal_provenance_records: list[Provenance],
        ) -> None:
            """Test serialization of minimal provenance records."""
            result = ProvenanceTracker.serialize_provenance(minimal_provenance_records)

            assert isinstance(result, dict)
            assert "sources" in result
            assert len(result["sources"]) == 2

            # Check first minimal source
            source1 = result["sources"][0]
            assert source1["@type"] == "DataDownload"
            assert source1["name"] == "clinvar"
            assert "url" not in source1  # None values omitted
            assert "version" not in source1  # None values omitted
            assert "processingSteps" not in source1  # Empty lists omitted
            assert "qualityScore" not in source1  # None values omitted
            assert source1["validationStatus"] == "pending"

            # Check second minimal source
            source2 = result["sources"][1]
            assert source2["@type"] == "DataDownload"
            assert source2["name"] == "manual"
            assert source2["processingSteps"] == ["manual_review"]
            assert source2["validationStatus"] == "validated"

        def test_serialize_empty_list(self) -> None:
            """Test serialization of empty provenance list."""
            result = ProvenanceTracker.serialize_provenance([])

            assert result == {"sources": []}

        def test_serialize_with_default_timestamps(self) -> None:
            """Test serialization uses current timestamp when acquired_at is None."""
            # This would require mocking datetime.now(), but the current implementation
            # always sets acquired_at via default_factory in the Provenance model
            # So this test ensures the field is always populated
            provenance = Provenance(
                source=DataSource.CLINVAR,
                acquired_by="test-user",
                validation_status="pending",
            )

            result = ProvenanceTracker.serialize_provenance([provenance])
            source = result["sources"][0]

            # Should have a datePublished field (not None)
            assert "datePublished" in source
            assert isinstance(source["datePublished"], str)
            # Should be parseable as ISO format
            datetime.fromisoformat(
                (
                    source["datePublished"]
                    if not source["datePublished"].endswith("Z")
                    else f"{source['datePublished'][:-1]}+00:00"
                ),
            )

    class TestWriteProvenanceMetadata:
        """Test provenance metadata file writing functionality."""

        def test_write_provenance_metadata_creates_file(
            self,
            sample_provenance_records: list[Provenance],
            tmp_path: Path,
        ) -> None:
            """Test that metadata file is created and contains correct content."""
            output_path = tmp_path / "provenance.json"

            ProvenanceTracker.write_provenance_metadata(
                sample_provenance_records,
                output_path,
            )

            assert output_path.exists()

            # Verify file content
            with output_path.open("r", encoding="utf-8") as f:
                content = json.load(f)

            assert "sources" in content
            assert len(content["sources"]) == 3
            assert content["sources"][0]["name"] == "clinvar"
            assert content["sources"][1]["name"] == "pubmed"
            assert content["sources"][2]["name"] == "uniprot"

        def test_write_provenance_metadata_creates_directories(
            self,
            sample_provenance_records: list[Provenance],
            tmp_path: Path,
        ) -> None:
            """Test that parent directories are created if they don't exist."""
            output_path = tmp_path / "nested" / "deep" / "provenance.json"

            ProvenanceTracker.write_provenance_metadata(
                sample_provenance_records,
                output_path,
            )

            assert output_path.exists()
            assert output_path.parent.exists()
            assert output_path.parent.name == "deep"

        def test_write_provenance_metadata_overwrites_existing(
            self,
            sample_provenance_records: list[Provenance],
            tmp_path: Path,
        ) -> None:
            """Test that existing files are overwritten."""
            output_path = tmp_path / "provenance.json"

            # Create existing file with different content
            output_path.write_text('{"existing": "content"}')

            ProvenanceTracker.write_provenance_metadata(
                sample_provenance_records,
                output_path,
            )

            # Verify content was replaced
            with output_path.open("r", encoding="utf-8") as f:
                content = json.load(f)

            assert "existing" not in content
            assert "sources" in content

        def test_write_provenance_metadata_empty_list(self, tmp_path: Path) -> None:
            """Test writing empty provenance list."""
            output_path = tmp_path / "empty_provenance.json"

            ProvenanceTracker.write_provenance_metadata([], output_path)

            assert output_path.exists()

            with output_path.open("r", encoding="utf-8") as f:
                content = json.load(f)

            assert content == {"sources": []}

        def test_write_provenance_metadata_uses_utf8_encoding(
            self,
            tmp_path: Path,
        ) -> None:
            """Test that files are written with UTF-8 encoding."""
            # Create provenance with Unicode characters in source_url
            provenance = Provenance(
                source=DataSource.CLINVAR,
                source_url="https://example.com/data?query=ñáéíóú&lang=中文",
                acquired_by="test-user",
                validation_status="validated",
            )

            output_path = tmp_path / "unicode_provenance.json"

            ProvenanceTracker.write_provenance_metadata([provenance], output_path)

            # Verify file can be read back correctly
            with output_path.open("r", encoding="utf-8") as f:
                content = json.load(f)

            assert content["sources"][0]["name"] == "clinvar"
            # The URL field should preserve Unicode characters
            url = content["sources"][0]["url"]
            assert "ñáéíóú" in url
            assert "中文" in url

    class TestEnrichWithProvenance:
        """Test metadata enrichment with provenance functionality."""

        def test_enrich_with_provenance_simple_metadata(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching simple metadata without @graph."""
            metadata: JSONObject = {
                "name": "MED13 Dataset",
                "version": "1.0.0",
                "description": "Test dataset",
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Metadata should be unchanged since there's no @graph
            assert result == metadata

        def test_enrich_with_provenance_jsonld_without_graph(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching JSON-LD metadata without @graph array."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@type": "Dataset",
                "name": "MED13 Dataset",
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should return unchanged since no @graph array
            assert result == metadata

        def test_enrich_with_provenance_jsonld_with_empty_graph(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching JSON-LD metadata with empty @graph array."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [],
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should return unchanged since @graph is empty
            assert result == metadata

        def test_enrich_with_provenance_jsonld_with_graph_no_root(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching JSON-LD metadata with @graph but no root entity."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    {
                        "@id": "file1.txt",
                        "@type": "File",
                        "name": "Data file 1",
                    },
                    {
                        "@id": "file2.txt",
                        "@type": "File",
                        "name": "Data file 2",
                    },
                ],
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should return unchanged since no root entity (./)
            assert result == metadata

        def test_enrich_with_provenance_jsonld_with_root_entity(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching JSON-LD metadata with root entity in @graph."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    {
                        "@id": "./",
                        "@type": "Dataset",
                        "name": "MED13 Dataset",
                        "description": "Curated biomedical data",
                    },
                    {
                        "@id": "data.csv",
                        "@type": "File",
                        "name": "Variant data",
                    },
                ],
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should have added hasPart with provenance sources
            assert "@graph" in result
            graph = result["@graph"]
            assert isinstance(graph, list)

            # Find the root entity
            root_entity = None
            for entity in graph:
                if isinstance(entity, dict) and entity.get("@id") == "./":
                    root_entity = entity
                    break

            assert root_entity is not None
            assert "hasPart" in root_entity

            has_part = root_entity["hasPart"]
            assert isinstance(has_part, list)
            assert len(has_part) == 3  # Should have 3 provenance sources

            # Check that sources were added correctly
            assert has_part[0]["@type"] == "DataDownload"
            assert has_part[0]["name"] == "clinvar"
            assert has_part[1]["@type"] == "DataDownload"
            assert has_part[1]["name"] == "pubmed"
            assert has_part[2]["@type"] == "DataDownload"
            assert has_part[2]["name"] == "uniprot"

        def test_enrich_with_provenance_jsonld_root_without_has_part(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching root entity that doesn't have hasPart field."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    {
                        "@id": "./",
                        "@type": "Dataset",
                        "name": "MED13 Dataset",
                    },
                ],
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should have created hasPart field
            graph_value = result.get("@graph")
            assert isinstance(graph_value, list)
            assert graph_value
            root_entity = graph_value[0]
            assert isinstance(root_entity, dict)
            assert "hasPart" in root_entity
            has_part_value = root_entity["hasPart"]
            assert isinstance(has_part_value, list)
            assert len(has_part_value) == 3

        def test_enrich_with_provenance_jsonld_root_with_existing_has_part(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching root entity that already has hasPart field."""
            existing_files = [
                {
                    "@id": "data.csv",
                    "@type": "File",
                    "name": "Existing data file",
                },
            ]

            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    {
                        "@id": "./",
                        "@type": "Dataset",
                        "name": "MED13 Dataset",
                        "hasPart": existing_files.copy(),
                    },
                ],
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should have extended existing hasPart
            graph_value = result.get("@graph")
            assert isinstance(graph_value, list)
            assert graph_value
            root_entity = graph_value[0]
            assert isinstance(root_entity, dict)
            has_part = root_entity.get("hasPart")
            assert isinstance(has_part, list)
            assert len(has_part) == 4  # 1 existing + 3 provenance sources

            # First item should be the existing file
            assert has_part[0]["@id"] == "data.csv"
            assert has_part[0]["name"] == "Existing data file"

            # Remaining items should be provenance sources
            for i in range(1, 4):
                assert has_part[i]["@type"] == "DataDownload"
                assert has_part[i]["name"] in ["clinvar", "pubmed", "uniprot"]

        def test_enrich_with_provenance_multiple_root_entities(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching metadata with multiple entities having @id './'."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    {
                        "@id": "./",
                        "@type": "Dataset",
                        "name": "First Dataset",
                    },
                    {
                        "@id": "./",
                        "@type": "Dataset",
                        "name": "Second Dataset",  # This should be ignored
                    },
                ],
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should only enrich the first root entity found
            graph = result.get("@graph")
            assert isinstance(graph, list)
            assert len(graph) == 2

            # First entity should have hasPart
            first_entity = graph[0]
            assert isinstance(first_entity, dict)
            assert "hasPart" in first_entity
            has_part = first_entity["hasPart"]
            assert isinstance(has_part, list)
            assert len(has_part) == 3

            # Second entity should be unchanged
            second_entity = graph[1]
            assert isinstance(second_entity, dict)
            assert "hasPart" not in second_entity

        def test_enrich_with_provenance_invalid_graph_type(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching metadata with invalid @graph type."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": "invalid",  # Should be list
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should return unchanged
            assert result == metadata

        def test_enrich_with_provenance_invalid_entity_type(
            self,
            sample_provenance_records: list[Provenance],
        ) -> None:
            """Test enriching metadata with invalid entity types in @graph."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    "invalid_entity",  # Should be dict
                    {
                        "@id": "./",
                        "@type": "Dataset",
                        "name": "Valid Dataset",
                    },
                ],
            }

            result = ProvenanceTracker.enrich_with_provenance(
                metadata,
                sample_provenance_records,
            )

            # Should skip invalid entity and enrich valid one
            graph = result.get("@graph")
            assert isinstance(graph, list)
            assert len(graph) == 2
            second_entity = graph[1]
            assert isinstance(second_entity, dict)
            assert second_entity["@id"] == "./"
            assert "hasPart" in second_entity

        def test_enrich_with_provenance_empty_provenance_list(self) -> None:
            """Test enriching metadata with empty provenance list."""
            metadata: JSONObject = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [
                    {
                        "@id": "./",
                        "@type": "Dataset",
                        "name": "Test Dataset",
                    },
                ],
            }

            result = ProvenanceTracker.enrich_with_provenance(metadata, [])

            # Should add empty hasPart or leave unchanged
            # The current implementation adds hasPart even for empty provenance
            graph_value = result.get("@graph")
            assert isinstance(graph_value, list)
            assert graph_value
            root_entity = graph_value[0]
            assert isinstance(root_entity, dict)
            assert "hasPart" in root_entity
            has_part_value = root_entity["hasPart"]
            assert isinstance(has_part_value, list)
            assert has_part_value == []
