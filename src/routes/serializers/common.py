"""Shared serializer builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from src.models.api import common as api_common

from .utils import _serialize_datetime

if TYPE_CHECKING:
    from datetime import datetime

ActivityFeedItem = api_common.ActivityFeedItem
DashboardSummary = api_common.DashboardSummary


def build_dashboard_summary(
    entity_counts: Mapping[str, int],
    *,
    pending_count: int,
    approved_count: int,
    rejected_count: int,
) -> DashboardSummary:
    """Construct the typed dashboard summary DTO."""
    total_items = sum(entity_counts.values())
    return DashboardSummary(
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        total_items=total_items,
        entity_counts=dict(entity_counts),
    )


def build_activity_feed_item(
    message: str,
    *,
    category: str,
    timestamp: datetime,
    icon: str | None = None,
) -> ActivityFeedItem:
    """Construct a typed activity feed item."""
    return ActivityFeedItem(
        message=message,
        category=category,
        icon=icon,
        created_at=_serialize_datetime(timestamp) or "",
    )


__all__ = [
    "build_activity_feed_item",
    "build_dashboard_summary",
]
