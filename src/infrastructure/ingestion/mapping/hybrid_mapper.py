"""
Hybrid mapper that combines multiple mapping strategies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.ingestion.interfaces import Mapper
    from src.infrastructure.ingestion.types import MappedObservation, RawRecord


class HybridMapper:
    """
    Hybrid mapper that chains multiple mapping strategies (e.g., Exact -> Vector -> LLM).
    """

    def __init__(self, mappers: list[Mapper]) -> None:
        self.mappers = mappers

    def map(self, record: RawRecord) -> list[MappedObservation]:
        """
        Map a raw record using the configured mappers in sequence.

        Currently implements a simple strategy:
        1. Try the first mapper.
        2. If it produces results, return them.
        3. If not, try the next mapper.

        A more sophisticated strategy might merge results or use confidence scores.
        """
        for mapper in self.mappers:
            observations = mapper.map(record)
            if observations:
                return observations

        return []
