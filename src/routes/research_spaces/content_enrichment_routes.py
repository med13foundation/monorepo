"""Tier-2 content-enrichment endpoints scoped to research spaces."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.agents.services.content_enrichment_service import (
    ContentEnrichmentDocumentOutcome,
    ContentEnrichmentRunSummary,
    ContentEnrichmentService,
)
from src.application.services.membership_management_service import (
    MembershipManagementService,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.routes.auth import get_current_active_user
from src.routes.research_spaces.dependencies import (
    get_membership_service,
    verify_space_membership,
)

from .router import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    research_spaces_router,
)


class ContentEnrichmentRunRequest(BaseModel):
    """Request payload for batch Tier-2 enrichment runs."""

    model_config = ConfigDict(strict=True)

    limit: int = Field(default=25, ge=1, le=200)
    source_id: UUID | None = None
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)


class ContentEnrichmentRunResponse(BaseModel):
    """Serialized summary for batch Tier-2 enrichment runs."""

    model_config = ConfigDict(strict=True)

    requested: int
    processed: int
    enriched: int
    skipped: int
    failed: int
    ai_runs: int
    deterministic_runs: int
    errors: list[str]
    started_at: datetime
    completed_at: datetime


class ContentEnrichmentDocumentRequest(BaseModel):
    """Request payload for one document enrichment run."""

    model_config = ConfigDict(strict=True)

    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    force: bool = Field(default=False)


class ContentEnrichmentDocumentResponse(BaseModel):
    """Serialized outcome for one document enrichment run."""

    model_config = ConfigDict(strict=True)

    document_id: UUID
    status: str
    execution_mode: str
    reason: str
    acquisition_method: str | None = None
    content_storage_key: str | None = None
    content_length_chars: int
    run_id: str | None = None
    errors: list[str]


def get_content_enrichment_service(
    session: Session = Depends(get_session),
) -> ContentEnrichmentService:
    """Dependency provider for the Tier-2 content-enrichment service."""
    container = get_legacy_dependency_container()
    return container.create_content_enrichment_service(session)


def _serialize_run_summary(
    summary: ContentEnrichmentRunSummary,
) -> ContentEnrichmentRunResponse:
    return ContentEnrichmentRunResponse(
        requested=summary.requested,
        processed=summary.processed,
        enriched=summary.enriched,
        skipped=summary.skipped,
        failed=summary.failed,
        ai_runs=summary.ai_runs,
        deterministic_runs=summary.deterministic_runs,
        errors=list(summary.errors),
        started_at=summary.started_at,
        completed_at=summary.completed_at,
    )


def _serialize_document_outcome(
    outcome: ContentEnrichmentDocumentOutcome,
) -> ContentEnrichmentDocumentResponse:
    return ContentEnrichmentDocumentResponse(
        document_id=outcome.document_id,
        status=outcome.status,
        execution_mode=outcome.execution_mode,
        reason=outcome.reason,
        acquisition_method=outcome.acquisition_method,
        content_storage_key=outcome.content_storage_key,
        content_length_chars=outcome.content_length_chars,
        run_id=outcome.run_id,
        errors=list(outcome.errors),
    )


@research_spaces_router.post(
    "/{space_id}/documents/enrichment/run",
    response_model=ContentEnrichmentRunResponse,
    summary="Run Tier-2 content enrichment for pending documents",
)
async def run_content_enrichment(
    space_id: UUID,
    request: ContentEnrichmentRunRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    content_enrichment_service: ContentEnrichmentService = Depends(
        get_content_enrichment_service,
    ),
    session: Session = Depends(get_session),
) -> ContentEnrichmentRunResponse:
    """Process pending document enrichment in one research space."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        summary = await content_enrichment_service.process_pending_documents(
            limit=request.limit,
            source_id=request.source_id,
            research_space_id=space_id,
            source_type=request.source_type,
            model_id=request.model_id,
        )
        return _serialize_run_summary(summary)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content enrichment failed: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/documents/{document_id}/enrichment",
    response_model=ContentEnrichmentDocumentResponse,
    summary="Run Tier-2 content enrichment for one document",
)
async def run_document_content_enrichment(
    space_id: UUID,
    document_id: UUID,
    request: ContentEnrichmentDocumentRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    content_enrichment_service: ContentEnrichmentService = Depends(
        get_content_enrichment_service,
    ),
    session: Session = Depends(get_session),
) -> ContentEnrichmentDocumentResponse:
    """Process one document through Tier-2 content enrichment."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        outcome = await content_enrichment_service.process_document(
            document_id=document_id,
            model_id=request.model_id,
            force=request.force,
        )
        return _serialize_document_outcome(outcome)
    except LookupError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content enrichment failed: {exc!s}",
        ) from exc
