"""
Resolution strategies for the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.models.database.kernel.entities import EntityModel
    from src.type_definitions.common import JSONObject


class ResolutionStrategy(Protocol):
    """Protocol for entity resolution strategies."""

    def resolve(
        self,
        identifiers: JSONObject,
        entity_type: str,
        study_id: str,
    ) -> EntityModel | None:
        """Resolve an entity based on identifiers."""
        ...


class StrictMatchStrategy:
    """
    Resolves entities by looking up exact identifier matches.
    """

    def __init__(self, entity_repository: KernelEntityRepository) -> None:
        self.entity_repo = entity_repository

    def resolve(
        self,
        identifiers: JSONObject,
        entity_type: str,
        study_id: str,
    ) -> EntityModel | None:
        # Use the repository's resolve method which handles identifier lookup
        # We assume 'identifiers' dictionary keys correspond to namespaces (e.g. 'mrn', 'hgnc_id')
        # and values are the identifier strings.

        # Cast values to strings as identifiers are stored as strings
        string_identifiers = {k: str(v) for k, v in identifiers.items()}

        return self.entity_repo.resolve(
            study_id=study_id,
            entity_type=entity_type,
            identifiers=string_identifiers,
        )


class LookupStrategy:
    """
    Placeholder for Lookup strategy (might be same as Strict Match for now).
    """

    def __init__(self, entity_repository: KernelEntityRepository) -> None:
        self.entity_repo = entity_repository

    def resolve(
        self,
        identifiers: JSONObject,
        entity_type: str,
        study_id: str,
    ) -> EntityModel | None:
        # For now, behaves like strict match on supported keys
        return StrictMatchStrategy(self.entity_repo).resolve(
            identifiers,
            entity_type,
            study_id,
        )


class FuzzyStrategy:
    """
    Placeholder for Fuzzy implementation.
    """

    def __init__(self, entity_repository: KernelEntityRepository) -> None:
        self.entity_repo = entity_repository

    def resolve(
        self,
        _identifiers: JSONObject,
        _entity_type: str,
        _study_id: str,
    ) -> EntityModel | None:
        # Placeholder
        return None
