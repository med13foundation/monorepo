"""Unit tests for the SQLAlchemy graph space settings adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from src.infrastructure.repositories.kernel.kernel_space_settings_repository import (
    SqlAlchemyKernelSpaceSettingsRepository,
)
from src.models.database.kernel.spaces import GraphSpaceModel, GraphSpaceStatusEnum

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_get_settings_returns_space_settings(
    db_session: Session,
) -> None:
    space_id = uuid4()
    db_session.add(
        GraphSpaceModel(
            id=space_id,
            slug=f"graph-space-{str(space_id).replace('-', '')[:8]}",
            name="Settings Test Space",
            description="Settings test space",
            owner_id=uuid4(),
            status=GraphSpaceStatusEnum.ACTIVE,
            settings={
                "review_threshold": 0.72,
                "relation_review_thresholds": {"CAUSES": 0.91},
            },
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceSettingsRepository(db_session)

    settings = repository.get_settings(space_id)

    assert settings is not None
    assert settings["review_threshold"] == 0.72
    assert settings["relation_review_thresholds"] == {"CAUSES": 0.91}


def test_get_settings_returns_none_when_space_missing(
    db_session: Session,
) -> None:
    repository = SqlAlchemyKernelSpaceSettingsRepository(db_session)

    assert repository.get_settings(uuid4()) is None
