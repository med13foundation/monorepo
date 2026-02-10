"""Kernel ingestion endpoint scoped to research spaces."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.ingestion.pipeline import IngestionPipeline
from src.infrastructure.ingestion.types import RawRecord as PipelineRawRecord
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    require_researcher_role,
)
from src.routes.research_spaces.kernel_dependencies import get_ingestion_pipeline

from .kernel_ingestion_schemas import KernelIngestRequest, KernelIngestResponse
from .router import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)


@research_spaces_router.post(
    "/{space_id}/ingest",
    response_model=KernelIngestResponse,
    status_code=HTTP_201_CREATED,
    summary="Ingest raw records into the kernel",
    description="Runs the deterministic ingestion pipeline against submitted raw records.",
)
def ingest_kernel_records(
    space_id: UUID,
    request: KernelIngestRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    session: Session = Depends(get_session),
) -> KernelIngestResponse:
    require_researcher_role(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    entity_type_default = request.entity_type.strip() if request.entity_type else None
    if request.entity_type is not None and not entity_type_default:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="entity_type cannot be empty when provided",
        )

    record_type_default = request.record_type.strip() if request.record_type else None

    raw_records: list[PipelineRawRecord] = []
    for record in request.records:
        metadata = dict(record.metadata)

        if entity_type_default and "entity_type" not in metadata:
            metadata["entity_type"] = entity_type_default

        if record_type_default and "type" not in metadata:
            metadata["type"] = record_type_default

        raw_records.append(
            PipelineRawRecord(
                source_id=record.source_id,
                data=record.data,
                metadata=metadata,
            ),
        )

    try:
        result = pipeline.run(raw_records, research_space_id=str(space_id))
        session.commit()
        return KernelIngestResponse(
            success=bool(result.success),
            entities_created=int(result.entities_created),
            observations_created=int(result.observations_created),
            errors=[str(e) for e in result.errors],
        )
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest records: {e!s}",
        ) from e


__all__ = ["ingest_kernel_records"]
