"""Tier-3 knowledge-extraction endpoints scoped to research spaces."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.agents.services.entity_recognition_service import (
    EntityRecognitionDocumentOutcome,
    EntityRecognitionRunSummary,
    EntityRecognitionService,
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


class KnowledgeExtractionRunRequest(BaseModel):
    """Request payload for batch Tier-3 extraction runs."""

    model_config = ConfigDict(strict=True)

    limit: int = Field(default=25, ge=1, le=200)
    source_id: UUID | None = None
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    shadow_mode: bool | None = None


class KnowledgeExtractionRunResponse(BaseModel):
    """Serialized summary for batch Tier-3 extraction runs."""

    model_config = ConfigDict(strict=True)

    requested: int
    processed: int
    extracted: int
    failed: int
    skipped: int
    review_required: int
    shadow_runs: int
    dictionary_variables_created: int
    dictionary_synonyms_created: int
    dictionary_entity_types_created: int
    ingestion_entities_created: int
    ingestion_observations_created: int
    errors: list[str]
    started_at: datetime
    completed_at: datetime


class KnowledgeExtractionDocumentRequest(BaseModel):
    """Request payload for one document Tier-3 extraction run."""

    model_config = ConfigDict(strict=True)

    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    shadow_mode: bool | None = None
    force: bool = Field(default=False)


class KnowledgeExtractionDocumentResponse(BaseModel):
    """Serialized outcome for one document Tier-3 extraction run."""

    model_config = ConfigDict(strict=True)

    document_id: UUID
    status: str
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_kernel: bool
    run_id: str | None = None
    dictionary_variables_created: int
    dictionary_synonyms_created: int
    dictionary_entity_types_created: int
    ingestion_entities_created: int
    ingestion_observations_created: int
    errors: list[str]


def get_entity_recognition_service(
    session: Session = Depends(get_session),
) -> EntityRecognitionService:
    """Dependency provider for the Tier-3 knowledge-extraction service."""
    container = get_legacy_dependency_container()
    return container.create_entity_recognition_service(session)


def _serialize_run_summary(
    summary: EntityRecognitionRunSummary,
) -> KnowledgeExtractionRunResponse:
    return KnowledgeExtractionRunResponse(
        requested=summary.requested,
        processed=summary.processed,
        extracted=summary.extracted,
        failed=summary.failed,
        skipped=summary.skipped,
        review_required=summary.review_required,
        shadow_runs=summary.shadow_runs,
        dictionary_variables_created=summary.dictionary_variables_created,
        dictionary_synonyms_created=summary.dictionary_synonyms_created,
        dictionary_entity_types_created=summary.dictionary_entity_types_created,
        ingestion_entities_created=summary.ingestion_entities_created,
        ingestion_observations_created=summary.ingestion_observations_created,
        errors=list(summary.errors),
        started_at=summary.started_at,
        completed_at=summary.completed_at,
    )


def _serialize_document_outcome(
    outcome: EntityRecognitionDocumentOutcome,
) -> KnowledgeExtractionDocumentResponse:
    return KnowledgeExtractionDocumentResponse(
        document_id=outcome.document_id,
        status=outcome.status,
        reason=outcome.reason,
        review_required=outcome.review_required,
        shadow_mode=outcome.shadow_mode,
        wrote_to_kernel=outcome.wrote_to_kernel,
        run_id=outcome.run_id,
        dictionary_variables_created=outcome.dictionary_variables_created,
        dictionary_synonyms_created=outcome.dictionary_synonyms_created,
        dictionary_entity_types_created=outcome.dictionary_entity_types_created,
        ingestion_entities_created=outcome.ingestion_entities_created,
        ingestion_observations_created=outcome.ingestion_observations_created,
        errors=list(outcome.errors),
    )


@research_spaces_router.post(
    "/{space_id}/documents/extraction/run",
    response_model=KnowledgeExtractionRunResponse,
    summary="Run Tier-3 knowledge extraction for pending documents",
)
async def run_knowledge_extraction(
    space_id: UUID,
    request: KnowledgeExtractionRunRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    entity_recognition_service: EntityRecognitionService = Depends(
        get_entity_recognition_service,
    ),
    session: Session = Depends(get_session),
) -> KnowledgeExtractionRunResponse:
    """Process pending documents through entity recognition + extraction."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        summary = await entity_recognition_service.process_pending_documents(
            limit=request.limit,
            source_id=request.source_id,
            research_space_id=space_id,
            source_type=request.source_type,
            model_id=request.model_id,
            shadow_mode=request.shadow_mode,
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
            detail=f"Knowledge extraction failed: {exc!s}",
        ) from exc


@research_spaces_router.post(
    "/{space_id}/documents/{document_id}/extraction",
    response_model=KnowledgeExtractionDocumentResponse,
    summary="Run Tier-3 knowledge extraction for one document",
)
async def run_document_knowledge_extraction(
    space_id: UUID,
    document_id: UUID,
    request: KnowledgeExtractionDocumentRequest,
    current_user: User = Depends(get_current_active_user),
    membership_service: MembershipManagementService = Depends(get_membership_service),
    entity_recognition_service: EntityRecognitionService = Depends(
        get_entity_recognition_service,
    ),
    session: Session = Depends(get_session),
) -> KnowledgeExtractionDocumentResponse:
    """Process one source document through entity recognition + extraction."""
    verify_space_membership(
        space_id,
        current_user.id,
        membership_service,
        session,
        current_user.role,
    )

    try:
        outcome = await entity_recognition_service.process_document(
            document_id=document_id,
            model_id=request.model_id,
            shadow_mode=request.shadow_mode,
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
            detail=f"Knowledge extraction failed: {exc!s}",
        ) from exc
