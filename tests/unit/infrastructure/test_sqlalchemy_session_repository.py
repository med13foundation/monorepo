from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.entities.session import SessionStatus
from src.infrastructure.repositories.sqlalchemy_session_repository import (
    SqlAlchemySessionRepository,
)
from src.models.database.base import Base
from src.models.database.session import SessionModel
from src.models.database.user import UserModel


@pytest.mark.asyncio
async def test_get_by_access_token_prefers_newest_active_duplicate() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    repository = SqlAlchemySessionRepository(
        _session_context_factory(session_factory),
    )

    async with session_factory() as session:
        user = UserModel(
            id=uuid4(),
            email="session-test@example.com",
            username="session-test",
            full_name="Session Test",
            hashed_password="hashed",
            role="admin",
            status="active",
        )
        session.add(user)

        now = datetime.now(UTC)
        session.add_all(
            [
                SessionModel(
                    id=uuid4(),
                    user_id=user.id,
                    session_token=repository._hash_token("duplicate-access-token"),
                    refresh_token=repository._hash_token("refresh-old"),
                    status=SessionStatus.ACTIVE,
                    expires_at=now + timedelta(minutes=15),
                    refresh_expires_at=now + timedelta(days=7),
                    created_at=now,
                    last_activity=now,
                ),
                SessionModel(
                    id=uuid4(),
                    user_id=user.id,
                    session_token=repository._hash_token("duplicate-access-token"),
                    refresh_token=repository._hash_token("refresh-new"),
                    status=SessionStatus.ACTIVE,
                    expires_at=now + timedelta(minutes=15),
                    refresh_expires_at=now + timedelta(days=7),
                    created_at=now + timedelta(seconds=1),
                    last_activity=now + timedelta(seconds=1),
                ),
            ],
        )
        await session.commit()

    loaded = await repository.get_by_access_token("duplicate-access-token")

    assert loaded is not None
    assert loaded.refresh_token == repository._hash_token("refresh-new")

    await engine.dispose()


def _session_context_factory(session_factory):
    @asynccontextmanager
    async def _session_context():
        async with session_factory() as session:
            yield session

    return _session_context
