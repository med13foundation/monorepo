"""Graph-local source-document reference lookup port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.kernel.source_documents import (
    KernelSourceDocumentReference,
)


class SourceDocumentReferencePort(ABC):
    """Lookup contract for graph-local source-document references."""

    @abstractmethod
    def get_by_id(
        self,
        document_id: UUID,
    ) -> KernelSourceDocumentReference | None:
        """Fetch one source-document reference by external document id."""


__all__ = ["SourceDocumentReferencePort"]
