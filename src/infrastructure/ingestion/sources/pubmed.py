"""
PubMed source adapter for the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from src.infrastructure.ingestion.types import RawRecord

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.type_definitions.common import JSONObject


class PubMedAdapter:
    """
    Adapts PubMed records to the ingestion pipeline's RawRecord format.
    """

    def to_raw_records(
        self,
        records: Iterable[JSONObject],
        source_id: str,
    ) -> list[RawRecord]:
        """
        Convert legacy PubMed records (dicts) to RawRecord dataclasses.
        """
        raw_records = []
        for record in records:
            # Generate a unique record ID if not present, but use PMID if available for stability
            record_id = str(record.get("pmid", uuid4()))

            raw_records.append(
                RawRecord(
                    source_id=record_id,
                    data=record,
                    metadata={
                        "original_source_id": source_id,
                        "type": "pubmed",
                        "pmid": record.get("pmid"),
                        "doi": record.get("doi"),
                    },
                ),
            )
        return raw_records
