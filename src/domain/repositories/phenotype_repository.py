"""
Phenotype repository interface - domain contract for phenotype data access.

Defines the operations available for phenotype entities without specifying
the underlying implementation.
"""

from abc import abstractmethod

from src.domain.entities.phenotype import Phenotype
from src.domain.repositories.base import Repository
from src.type_definitions.common import PhenotypeUpdate, QueryFilters


class PhenotypeRepository(Repository[Phenotype, int, PhenotypeUpdate]):
    """
    Domain repository interface for Phenotype entities.

    Defines all operations available for phenotype data access, maintaining
    domain purity by not exposing infrastructure details.
    """

    @abstractmethod
    def find_by_hpo_id(self, hpo_id: str) -> Phenotype | None:
        """Find a phenotype by its HPO ID."""

    @abstractmethod
    def find_by_name(self, name: str, *, fuzzy: bool = False) -> list[Phenotype]:
        """Find phenotypes by name (exact or fuzzy match)."""

    @abstractmethod
    def find_by_gene_associations(self, gene_id: int) -> list[Phenotype]:
        """Find phenotypes associated with a gene."""

    @abstractmethod
    def find_by_variant_associations(self, variant_id: int) -> list[Phenotype]:
        """Find phenotypes associated with a variant."""

    @abstractmethod
    def find_by_category(self, category: str) -> list[Phenotype]:
        """Find phenotypes by category."""

    @abstractmethod
    def find_children(self, parent_hpo_id: str) -> list[Phenotype]:
        """Find child phenotypes for a given HPO ID."""

    @abstractmethod
    def search_phenotypes(
        self,
        query: str,
        limit: int = 10,
        filters: QueryFilters | None = None,
    ) -> list[Phenotype]:
        """Search phenotypes with optional filters."""

    @abstractmethod
    def find_by_ids(
        self,
        phenotype_ids: list[int],
        filters: QueryFilters | None = None,
    ) -> list[Phenotype]:
        """Find phenotypes by ID list with optional filters."""

    @abstractmethod
    def paginate_phenotypes(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: QueryFilters | None = None,
    ) -> tuple[list[Phenotype], int]:
        """Retrieve paginated phenotypes with optional filters."""

    @abstractmethod
    def get_phenotype_statistics(self) -> dict[str, int | float | bool | str | None]:
        """Get statistics about phenotypes in the repository."""

    @abstractmethod
    def find_by_ontology_term(self, term_id: str) -> Phenotype | None:
        """Find a phenotype by ontology term ID."""

    @abstractmethod
    def update_phenotype(
        self,
        phenotype_id: int,
        updates: PhenotypeUpdate,
    ) -> Phenotype:
        """Update a phenotype with type-safe update parameters."""


__all__ = ["PhenotypeRepository"]
