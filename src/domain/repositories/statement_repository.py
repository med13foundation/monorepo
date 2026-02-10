"""
Statement of Understanding repository interface - domain contract for data access.
"""

from abc import abstractmethod
from uuid import UUID

from src.domain.entities.statement import StatementOfUnderstanding
from src.domain.repositories.base import Repository
from src.type_definitions.common import QueryFilters, StatementUpdate


class StatementRepository(Repository[StatementOfUnderstanding, int, StatementUpdate]):
    """
    Domain repository interface for Statement of Understanding entities.
    """

    @abstractmethod
    def find_by_title(
        self,
        title: str,
        *,
        research_space_id: UUID,
    ) -> StatementOfUnderstanding | None:
        """Find a statement by title within a research space."""

    @abstractmethod
    def search_statements(
        self,
        query: str,
        limit: int = 10,
        filters: QueryFilters | None = None,
    ) -> list[StatementOfUnderstanding]:
        """Search statements by title/summary with optional filters."""

    @abstractmethod
    def paginate_statements(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: QueryFilters | None = None,
    ) -> tuple[list[StatementOfUnderstanding], int]:
        """Retrieve paginated statements with optional filters."""

    @abstractmethod
    def update_statement(
        self,
        statement_id: int,
        updates: StatementUpdate,
    ) -> StatementOfUnderstanding:
        """Update a statement with type-safe update parameters."""


__all__ = ["StatementRepository"]
