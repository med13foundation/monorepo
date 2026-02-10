"""
Data structures for the kernel ingestion pipeline.
"""  # noqa: A005

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

    from src.type_definitions.common import JSONObject, JSONValue

    IngestedValue = JSONValue | datetime | date


@dataclass
class RawRecord:
    """Represents a raw record from an external source."""

    source_id: str
    data: JSONObject
    metadata: JSONObject = field(default_factory=dict)


@dataclass
class MappedObservation:
    """Represents an observation where the variable has been identified but value is not normalized."""

    subject_anchor: JSONObject  # e.g. {"hgnc_id": "1234"}
    variable_id: str
    value: IngestedValue
    unit: str | None  # Standardized unit
    observed_at: datetime | None
    provenance: JSONObject = field(default_factory=dict)


@dataclass
class NormalizedObservation:
    """Represents a fully normalized observation ready for resolution."""

    subject_anchor: JSONObject
    variable_id: str
    value: IngestedValue
    unit: str | None
    observed_at: datetime | None
    provenance: JSONObject = field(default_factory=dict)


@dataclass
class ResolvedEntity:
    """Represents a resolved kernel entity."""

    id: str  # UUID
    entity_type: str
    display_label: str


@dataclass
class IngestResult:
    """Result of an ingestion operation."""

    success: bool
    entities_created: int = 0
    observations_created: int = 0
    errors: list[str] = field(default_factory=list)
