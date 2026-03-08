"""PubMed-specific discovery endpoints."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.application.services import (
    AuditTrailService,
    DiscoveryConfigurationService,
    PubMedDiscoveryService,
    PubmedDownloadRequest,
    RunPubmedSearchRequest,
)
from src.database.session import get_session
from src.domain.entities.user import User
from src.infrastructure.dependency_injection.dependencies import (
    get_discovery_configuration_service_dependency,
    get_pubmed_discovery_service_dependency,
)
from src.infrastructure.observability.request_context import get_audit_context
from src.routes.auth import get_current_active_user
from src.routes.data_discovery.dependencies import get_audit_trail_service
from src.type_definitions.common import AuditContext

from .mappers import (
    preset_to_response,
    search_job_to_response,
    storage_operation_to_response,
)
from .schemas import (
    CreatePubmedPresetRequestModel,
    DiscoveryPresetResponse,
    DiscoverySearchJobResponse,
    PubmedDownloadRequestModel,
    RunPubmedSearchRequestModel,
    StorageOperationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pubmed", tags=["data-discovery-pubmed"])


@router.get(
    "/presets",
    response_model=list[DiscoveryPresetResponse],
    summary="List PubMed presets",
)
def list_pubmed_presets(
    *,
    research_space_id: UUID | None = Query(
        None,
        description="Include presets shared with this space",
    ),
    service: DiscoveryConfigurationService = Depends(
        get_discovery_configuration_service_dependency,
    ),
    current_user: User = Depends(get_current_active_user),
) -> list[DiscoveryPresetResponse]:
    """List PubMed presets for the current user."""

    try:
        presets = service.list_pubmed_presets(
            current_user.id,
            research_space_id=research_space_id,
        )
        return [preset_to_response(preset) for preset in presets]
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Failed to list PubMed presets")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load PubMed presets",
        ) from exc


@router.post(
    "/presets",
    response_model=DiscoveryPresetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create PubMed preset",
)
def create_pubmed_preset(
    request: CreatePubmedPresetRequestModel,
    service: DiscoveryConfigurationService = Depends(
        get_discovery_configuration_service_dependency,
    ),
    db: Session = Depends(get_session),
    audit_service: AuditTrailService = Depends(get_audit_trail_service),
    audit_context: AuditContext = Depends(get_audit_context),
    current_user: User = Depends(get_current_active_user),
) -> DiscoveryPresetResponse:
    """Create a new PubMed preset."""

    try:
        preset = service.create_pubmed_preset(
            current_user.id,
            request.to_domain_request(),
        )

        audit_service.record_action(
            db,
            action="discovery.preset.create",
            target=("discovery_preset", str(preset.id)),
            actor_id=current_user.id,
            details={
                "name": preset.name,
                "scope": preset.scope.value,
                "space_id": (
                    str(preset.research_space_id) if preset.research_space_id else None
                ),
            },
            context=audit_context,
            success=True,
        )

        return preset_to_response(preset)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Failed to create PubMed preset")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create PubMed preset",
        ) from exc


@router.delete(
    "/presets/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete PubMed preset",
)
def delete_pubmed_preset(
    preset_id: UUID,
    service: DiscoveryConfigurationService = Depends(
        get_discovery_configuration_service_dependency,
    ),
    db: Session = Depends(get_session),
    audit_service: AuditTrailService = Depends(get_audit_trail_service),
    audit_context: AuditContext = Depends(get_audit_context),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Delete a preset owned by the current user."""

    deleted = service.delete_preset(preset_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found",
        )

    audit_service.record_action(
        db,
        action="discovery.preset.delete",
        target=("discovery_preset", str(preset_id)),
        actor_id=current_user.id,
        context=audit_context,
        success=True,
    )


@router.post(
    "/search",
    response_model=DiscoverySearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start PubMed search",
)
async def run_pubmed_search(
    request: RunPubmedSearchRequestModel,
    service: PubMedDiscoveryService = Depends(get_pubmed_discovery_service_dependency),
    db: Session = Depends(get_session),
    audit_service: AuditTrailService = Depends(get_audit_trail_service),
    audit_context: AuditContext = Depends(get_audit_context),
    current_user: User = Depends(get_current_active_user),
) -> DiscoverySearchJobResponse:
    """Start executing an advanced PubMed search."""

    domain_request = RunPubmedSearchRequest(
        session_id=request.session_id,
        parameters=request.parameters.to_domain_model(),
    )
    job = await service.run_pubmed_search(current_user.id, domain_request)

    audit_service.record_action(
        db,
        action="discovery.search.run",
        target=("discovery_search_job", str(job.id)),
        actor_id=current_user.id,
        details={
            "session_id": str(request.session_id),
            "gene_symbol": job.parameters.gene_symbol,
            "max_results": job.parameters.max_results,
        },
        context=audit_context,
        success=True,
    )

    return search_job_to_response(job)


@router.get(
    "/search/{job_id}",
    response_model=DiscoverySearchJobResponse,
    summary="Get PubMed search job details",
)
def get_pubmed_search_job(
    job_id: UUID,
    service: PubMedDiscoveryService = Depends(
        get_pubmed_discovery_service_dependency,
    ),
    current_user: User = Depends(get_current_active_user),
) -> DiscoverySearchJobResponse:
    """Return the state of a PubMed search job owned by the user."""

    job = service.get_search_job(current_user.id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Search job not found",
        )
    return search_job_to_response(job)


@router.post(
    "/download",
    response_model=StorageOperationResponse,
    summary="Download PubMed article PDF",
)
async def download_pubmed_article_pdf(
    request: PubmedDownloadRequestModel,
    service: PubMedDiscoveryService = Depends(get_pubmed_discovery_service_dependency),
    db: Session = Depends(get_session),
    audit_service: AuditTrailService = Depends(get_audit_trail_service),
    audit_context: AuditContext = Depends(get_audit_context),
    current_user: User = Depends(get_current_active_user),
) -> StorageOperationResponse:
    """Trigger PDF storage for a PubMed article."""

    try:
        record = await service.download_article_pdf(
            current_user.id,
            PubmedDownloadRequest(job_id=request.job_id, article_id=request.article_id),
        )

        audit_service.record_action(
            db,
            action="discovery.pdf.download",
            target=("storage_operation", str(record.id)),
            actor_id=current_user.id,
            details={
                "job_id": str(request.job_id),
                "article_id": request.article_id,
                "key": record.key,
            },
            context=audit_context,
            success=True,
        )

        return storage_operation_to_response(record)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
