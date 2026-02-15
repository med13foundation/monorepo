"""
Vector similarity mapper for the ingestion pipeline.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.infrastructure.ingestion.types import MappedObservation, RawRecord

if TYPE_CHECKING:
    from src.domain.entities.kernel.dictionary import DictionarySearchResult
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import JSONObject


def _read_similarity_threshold() -> float:
    raw_value = (
        os.getenv("MED13_VECTOR_MAPPER_SIMILARITY_THRESHOLD")
        or os.getenv("VECTOR_MAPPER_SIMILARITY_THRESHOLD")
        or "0.7"
    )
    try:
        parsed = float(raw_value)
    except ValueError:
        return 0.7
    return min(1.0, max(0.0, parsed))


def _read_top_k() -> int:
    raw_value = (
        os.getenv("MED13_VECTOR_MAPPER_TOP_K")
        or os.getenv("VECTOR_MAPPER_TOP_K")
        or "5"
    )
    try:
        parsed = int(raw_value)
    except ValueError:
        return 5
    return max(1, parsed)


VECTOR_MAPPER_SIMILARITY_THRESHOLD = _read_similarity_threshold()
VECTOR_MAPPER_TOP_K = _read_top_k()


class VectorMapper:
    """
    Maps raw records to observations using vector dictionary search fallback.
    """

    def __init__(
        self,
        dictionary_repository: DictionaryPort,
        *,
        similarity_threshold: float = VECTOR_MAPPER_SIMILARITY_THRESHOLD,
        top_k: int = VECTOR_MAPPER_TOP_K,
    ) -> None:
        self.dictionary_repo = dictionary_repository
        self.similarity_threshold = min(1.0, max(0.0, similarity_threshold))
        self.top_k = max(1, top_k)

    def map(self, record: RawRecord) -> list[MappedObservation]:
        observations: list[MappedObservation] = []
        subject_anchor = self._extract_subject_anchor(record)
        observed_at = self._extract_timestamp(record)
        domain_context = self._extract_domain_context(record)

        for key, value in record.data.items():
            if value is None or value == "":
                continue

            search_results = self.dictionary_repo.dictionary_search(
                terms=[key],
                dimensions=["variables"],
                domain_context=domain_context,
                limit=self.top_k,
            )
            vector_matches = self._select_vector_matches(search_results)
            if not vector_matches:
                continue

            best_match = max(
                vector_matches,
                key=lambda result: result.similarity_score,
            )
            observations.append(
                MappedObservation(
                    subject_anchor=subject_anchor,
                    variable_id=best_match.entry_id,
                    value=value,
                    unit=None,
                    observed_at=observed_at,
                    provenance={
                        "source_id": record.source_id,
                        "original_key": key,
                        "method": "vector_match",
                        "similarity_score": best_match.similarity_score,
                        "matched_dimension": best_match.dimension,
                        "matched_display_name": best_match.display_name,
                        "match_method": best_match.match_method,
                        "match_metadata": best_match.metadata,
                        "domain_context": best_match.domain_context,
                        "metadata": record.metadata,
                    },
                ),
            )

        return observations

    def _select_vector_matches(
        self,
        search_results: list[DictionarySearchResult],
    ) -> list[DictionarySearchResult]:
        return [
            result
            for result in search_results
            if result.dimension == "variables"
            and result.match_method == "vector"
            and result.similarity_score >= self.similarity_threshold
        ]

    def _extract_domain_context(self, record: RawRecord) -> str | None:
        for key in ("domain_context", "domain"):
            raw_value = record.metadata.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                return raw_value.strip()
        return None

    def _extract_subject_anchor(self, record: RawRecord) -> JSONObject:
        anchors: JSONObject = {}

        record_type = record.metadata.get("type")
        if isinstance(record_type, str) and record_type == "pubmed":
            for key in ["pmid", "doi", "title"]:
                if key in record.data and record.data[key] is not None:
                    anchors[key] = record.data[key]
            return anchors

        for key in ["mrn", "issuer", "patient_id", "email", "hgnc_id", "gene_symbol"]:
            if key in record.data and record.data[key] is not None:
                anchors[key] = record.data[key]
        return anchors

    def _extract_timestamp(self, record: RawRecord) -> datetime | None:
        for key in [
            "timestamp",
            "date",
            "created_at",
            "observed_at",
            "publication_date",
        ]:
            if key not in record.data:
                continue
            value = record.data[key]
            if not isinstance(value, str):
                continue
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        return None
