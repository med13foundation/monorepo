"""
Dashboard API routes for the MED13 Resource Library.
Provides statistics and activity feed endpoints for the admin dashboard.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.application.services.dashboard_service import DashboardService
from src.database.session import get_session
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.models.api import ActivityFeedItem, DashboardSummary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class RecentActivitiesResponse(BaseModel):
    """Recent activity list response."""

    activities: list[ActivityFeedItem]
    total: int


def _get_dashboard_service(db: Session) -> DashboardService:
    container = get_legacy_dependency_container()
    return container.create_dashboard_service(db)


@router.get(
    "",
    summary="Get dashboard statistics",
    response_model=DashboardSummary,
)
def get_dashboard_stats(
    db: Session = Depends(get_session),
) -> DashboardSummary:
    """
    Retrieve overall dashboard statistics.

    Returns counts for tracked entities without synthetic status heuristics.
    """
    service = _get_dashboard_service(db)
    return service.get_summary()


@router.get(
    "/activities",
    summary="Get recent activity feed",
    response_model=RecentActivitiesResponse,
)
def get_recent_activities(
    db: Session = Depends(get_session),
    limit: int = 10,
) -> RecentActivitiesResponse:
    """
    Retrieve recent activities for the dashboard activity feed.
    """
    service = _get_dashboard_service(db)
    activities = list(service.get_recent_activities(limit))
    return RecentActivitiesResponse(activities=activities, total=len(activities))
