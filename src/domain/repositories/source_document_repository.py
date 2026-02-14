"""Repository interface for source document lifecycle persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID  # noqa: TC003

from src.domain.entities.source_document import SourceDocument  # noqa: TC001


class SourceDocumentRepository(ABC):
    """Abstract persistence contract for Document Store records."""

    @abstractmethod
    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        """Fetch a source document by its primary id."""

    @abstractmethod
    def get_by_source_external_record(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceDocument | None:
        """Fetch a source document by source + upstream record identifier."""

    @abstractmethod
    def upsert(self, document: SourceDocument) -> SourceDocument:
        """Create or update a source document using source/external id identity."""

    @abstractmethod
    def upsert_many(
        self,
        documents: list[SourceDocument],
    ) -> list[SourceDocument]:
        """Create or update one or more source documents."""

    @abstractmethod
    def list_pending_enrichment(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
    ) -> list[SourceDocument]:
        """List documents waiting for enrichment."""

    @abstractmethod
    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
    ) -> list[SourceDocument]:
        """List documents waiting for extraction."""

    @abstractmethod
    def delete_by_source(self, source_id: UUID) -> int:
        """Delete all document rows for the given source and return affected rows."""

    @abstractmethod
    def count_for_source(self, source_id: UUID) -> int:
        """Count source documents for a given source."""
