"""Unit tests for the SQLAlchemy graph space registry adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities.kernel.spaces import KernelSpaceRegistryEntry
from src.infrastructure.repositories.kernel.kernel_space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)
from src.models.database.kernel.spaces import GraphSpaceModel, GraphSpaceStatusEnum

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_get_by_id_returns_graph_space_registry_entry(
    db_session: Session,
) -> None:
    owner_id = uuid4()
    space_id = uuid4()
    db_session.add(
        GraphSpaceModel(
            id=space_id,
            slug=f"graph-space-{str(space_id).replace('-', '')[:8]}",
            name="Registry Test Space",
            description="Registry test space",
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings={"auto_approve": True},
            sync_source="platform_control_plane",
            sync_fingerprint="abc123",
            source_updated_at=datetime.now(UTC),
            last_synced_at=datetime.now(UTC),
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceRegistryRepository(db_session)

    entry = repository.get_by_id(space_id)

    assert entry is not None
    assert entry.id == space_id
    assert entry.slug.startswith("graph-space-")
    assert entry.name == "Registry Test Space"
    assert entry.owner_id == owner_id
    assert entry.status == "active"
    assert entry.settings["auto_approve"] is True
    assert entry.sync_source == "platform_control_plane"
    assert entry.sync_fingerprint == "abc123"


def test_list_space_ids_returns_sorted_space_ids(
    db_session: Session,
) -> None:
    first_space_id = uuid4()
    second_space_id = uuid4()
    db_session.add_all(
        [
            GraphSpaceModel(
                id=first_space_id,
                slug=f"graph-space-{str(first_space_id).replace('-', '')[:8]}",
                name="First Registry Space",
                description="First registry test space",
                owner_id=uuid4(),
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
            GraphSpaceModel(
                id=second_space_id,
                slug=f"graph-space-{str(second_space_id).replace('-', '')[:8]}",
                name="Second Registry Space",
                description="Second registry test space",
                owner_id=uuid4(),
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
        ],
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceRegistryRepository(db_session)

    assert repository.list_space_ids() == sorted([first_space_id, second_space_id])


def test_list_entries_returns_sorted_graph_space_registry_entries(
    db_session: Session,
) -> None:
    first_space_id = uuid4()
    second_space_id = uuid4()
    db_session.add_all(
        [
            GraphSpaceModel(
                id=second_space_id,
                slug="graph-b",
                name="Graph Space B",
                description=None,
                owner_id=uuid4(),
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={"review_threshold": 0.8},
            ),
            GraphSpaceModel(
                id=first_space_id,
                slug="graph-a",
                name="Graph Space A",
                description="First graph space",
                owner_id=uuid4(),
                status=GraphSpaceStatusEnum.INACTIVE,
                settings={},
            ),
        ],
    )
    db_session.flush()

    repository = SqlAlchemyKernelSpaceRegistryRepository(db_session)

    entries = repository.list_entries()

    assert [entry.id for entry in entries] == sorted([first_space_id, second_space_id])
    entries_by_slug = {entry.slug: entry for entry in entries}
    assert set(entries_by_slug) == {"graph-a", "graph-b"}
    assert entries_by_slug["graph-b"].settings["review_threshold"] == 0.8


def test_save_upserts_graph_space_registry_entry(
    db_session: Session,
) -> None:
    repository = SqlAlchemyKernelSpaceRegistryRepository(db_session)
    space_id = uuid4()
    owner_id = uuid4()
    created_at = datetime.now(UTC)
    updated_at = datetime.now(UTC)

    created = repository.save(
        KernelSpaceRegistryEntry(
            id=space_id,
            slug="graph-space",
            name="Graph Space",
            description="Initial description",
            owner_id=owner_id,
            status="active",
            settings={"review_threshold": 0.7},
            sync_source="platform_control_plane",
            sync_fingerprint="fingerprint-a",
            source_updated_at=created_at,
            last_synced_at=updated_at,
            created_at=created_at,
            updated_at=updated_at,
        ),
    )
    updated = repository.save(
        KernelSpaceRegistryEntry(
            id=space_id,
            slug="graph-space",
            name="Graph Space Updated",
            description="Updated description",
            owner_id=owner_id,
            status="suspended",
            settings={"review_threshold": 0.9},
            sync_source="platform_control_plane",
            sync_fingerprint="fingerprint-b",
            source_updated_at=created.created_at,
            last_synced_at=created.updated_at,
            created_at=created.created_at,
            updated_at=created.updated_at,
        ),
    )

    assert created.id == space_id
    assert updated.name == "Graph Space Updated"
    assert updated.description == "Updated description"
    assert updated.status == "suspended"
    assert updated.settings["review_threshold"] == 0.9
    assert updated.sync_source == "platform_control_plane"
    assert updated.sync_fingerprint == "fingerprint-b"
    assert db_session.get(GraphSpaceModel, space_id) is not None
