"""SQLAlchemy adapter for graph-local source-document references."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.entities.kernel.source_documents import (
    KernelSourceDocumentReference,
)
from src.domain.ports.source_document_reference_port import (
    SourceDocumentReferencePort,
)
from src.models.database.source_document import SourceDocumentModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyKernelSourceDocumentReferenceRepository(
    SourceDocumentReferencePort,
):
    """Resolve graph-local document references from the shared document store."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(
        self,
        document_id: UUID,
    ) -> KernelSourceDocumentReference | None:
        model = self._session.get(SourceDocumentModel, str(document_id))
        if model is None:
            return None
        return KernelSourceDocumentReference(
            id=UUID(str(model.id)),
            research_space_id=(
                UUID(str(model.research_space_id))
                if model.research_space_id is not None
                else None
            ),
            source_id=UUID(str(model.source_id)),
            external_record_id=model.external_record_id,
            source_type=model.source_type,
            document_format=model.document_format,
            enrichment_status=model.enrichment_status,
            extraction_status=model.extraction_status,
            metadata=dict(model.metadata_payload or {}),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


__all__ = ["SqlAlchemyKernelSourceDocumentReferenceRepository"]
