"""
Interfaces for the kernel ingestion pipeline components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.infrastructure.ingestion.types import (
        MappedObservation,
        NormalizedObservation,
        RawRecord,
        ResolvedEntity,
    )
    from src.type_definitions.common import JSONObject


@runtime_checkable
class Mapper(Protocol):
    """Maps raw records to observations with identified variables."""

    def map(self, record: RawRecord) -> list[MappedObservation]:
        """Map a raw record to a list of observations."""
        ...


@runtime_checkable
class Normalizer(Protocol):
    """Normalizes values and units of mapped observations."""

    def normalize(self, observation: MappedObservation) -> NormalizedObservation:
        """Normalize the value and unit of an observation."""
        ...


@runtime_checkable
class Resolver(Protocol):
    """Resolves entity anchors to kernel entities."""

    def resolve(
        self,
        anchor: JSONObject,
        entity_type: str,
        research_space_id: str,
    ) -> ResolvedEntity:
        """Resolve an entity anchor to a kernel entity."""
        ...


@runtime_checkable
class Validator(Protocol):
    """Validates observations and relations against constraints."""

    def validate(self, observation: NormalizedObservation) -> bool:
        """Validate an observation against variable constraints."""
        ...
