"""Application-level orchestration for phenotype use cases."""

from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.entities.phenotype import Phenotype, PhenotypeCategory
from src.domain.repositories.phenotype_repository import PhenotypeRepository
from src.domain.value_objects.identifiers import PhenotypeIdentifier
from src.type_definitions.common import FilterValue, PhenotypeUpdate, QueryFilters


@dataclass
class PhenotypeHierarchy:
    """Simple structure representing a phenotype parent/child relationship."""

    phenotype: Phenotype
    children: list[Phenotype]
    parent_hpo_id: str | None


class PhenotypeApplicationService:
    """
    Application service for phenotype management use cases.

    Orchestrates domain services and repositories to implement
    phenotype-related business operations with proper dependency injection.
    """

    def __init__(self, phenotype_repository: PhenotypeRepository):
        """
        Initialize the phenotype application service.

        Args:
            phenotype_repository: Domain repository for phenotypes
        """
        self._phenotype_repository = phenotype_repository

    def create_phenotype(
        self,
        hpo_id: str,
        name: str,
        definition: str | None = None,
        category: str = PhenotypeCategory.OTHER,
        synonyms: list[str] | None = None,
    ) -> Phenotype:
        """
        Create a new phenotype.

        Args:
            hpo_id: HPO identifier
            name: Phenotype name
            definition: Phenotype definition
            category: Phenotype category
            synonyms: Alternative names

        Returns:
            Created Phenotype entity
        """
        identifiers = PhenotypeIdentifier(hpo_id=hpo_id, hpo_term=name)
        phenotype_entity = Phenotype(
            identifier=identifiers,
            name=name,
            definition=definition,
            category=PhenotypeCategory.validate(category),
            synonyms=tuple(synonyms or []),
        )

        return self._phenotype_repository.create(phenotype_entity)

    def get_phenotype_by_hpo_id(self, hpo_id: str) -> Phenotype | None:
        """Find a phenotype by its HPO ID."""
        return self._phenotype_repository.find_by_hpo_id(hpo_id)

    def search_phenotypes_by_name(
        self,
        name: str,
        *,
        fuzzy: bool = False,
    ) -> list[Phenotype]:
        """Find phenotypes by name."""
        return self._phenotype_repository.find_by_name(name, fuzzy=fuzzy)

    def get_phenotypes_by_category(self, category: str) -> list[Phenotype]:
        """Find phenotypes by category."""
        return self._phenotype_repository.find_by_category(category)

    def get_phenotype_hierarchy(self, hpo_id: str) -> PhenotypeHierarchy | None:
        """Return the target phenotype with its children."""
        phenotype = self._phenotype_repository.find_by_hpo_id(hpo_id)
        if phenotype is None:
            return None

        children = self._phenotype_repository.find_children(hpo_id)
        return PhenotypeHierarchy(
            phenotype=phenotype,
            children=children,
            parent_hpo_id=phenotype.parent_hpo_id,
        )

    def search_phenotypes(
        self,
        query: str,
        limit: int = 10,
        filters: Mapping[str, FilterValue] | QueryFilters | None = None,
    ) -> list[Phenotype]:
        """Search phenotypes with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._phenotype_repository.search_phenotypes(
            query,
            limit,
            normalized_filters,
        )

    def get_phenotypes_by_ids(
        self,
        phenotype_ids: list[int],
        filters: Mapping[str, FilterValue] | QueryFilters | None = None,
    ) -> list[Phenotype]:
        """Return phenotypes for the given IDs with optional filters."""
        if not phenotype_ids:
            return []
        normalized_filters = self._normalize_filters(filters)
        return self._phenotype_repository.find_by_ids(
            phenotype_ids,
            normalized_filters,
        )

    def list_phenotypes(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: Mapping[str, FilterValue] | QueryFilters | None = None,
    ) -> tuple[list[Phenotype], int]:
        """Retrieve paginated phenotypes with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._phenotype_repository.paginate_phenotypes(
            page,
            per_page,
            sort_by,
            sort_order,
            normalized_filters,
        )

    def update_phenotype(
        self,
        phenotype_id: int,
        updates: PhenotypeUpdate,
    ) -> Phenotype:
        """Update phenotype fields."""
        if not updates:
            msg = "No phenotype updates provided"
            raise ValueError(msg)
        return self._phenotype_repository.update(phenotype_id, updates)

    def get_phenotype_statistics(self) -> dict[str, int | float | bool | str | None]:
        """Get statistics about phenotypes in the repository."""
        return self._phenotype_repository.get_phenotype_statistics()

    def validate_phenotype_exists(self, phenotype_id: int) -> bool:
        """
        Validate that a phenotype exists.

        Args:
            phenotype_id: Phenotype ID to validate

        Returns:
            True if phenotype exists, False otherwise
        """
        return self._phenotype_repository.exists(phenotype_id)

    @staticmethod
    def _normalize_filters(
        filters: Mapping[str, FilterValue] | QueryFilters | None,
    ) -> QueryFilters | None:
        if filters is None:
            return None
        return dict(filters)


__all__ = ["PhenotypeApplicationService", "PhenotypeHierarchy"]
