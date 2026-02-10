"""Shared serializer helpers."""

from __future__ import annotations

from datetime import datetime


def _require_entity_id(entity_name: str, identifier: int | None) -> int:
    if identifier is None:
        msg = f"{entity_name} must have an id before serialization"
        raise ValueError(msg)
    return identifier


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
