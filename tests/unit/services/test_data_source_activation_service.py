"""Tests for DataSourceActivationService."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.application.services.data_source_activation_service import (
    DataSourceActivationService,
)
from src.domain.entities.data_source_activation import (
    ActivationScope,
    DataSourceActivation,
    PermissionLevel,
)
from src.domain.repositories.data_source_activation_repository import (
    DataSourceActivationRepository,
)


class InMemoryActivationRepository(DataSourceActivationRepository):
    """Simple in-memory repository for testing."""

    def __init__(self) -> None:
        self._rules: dict[
            tuple[str, ActivationScope, UUID | None],
            DataSourceActivation,
        ] = {}

    def _key(
        self,
        catalog_entry_id: str,
        scope: ActivationScope,
        research_space_id: UUID | None,
    ) -> tuple[str, ActivationScope, UUID | None]:
        return (catalog_entry_id, scope, research_space_id)

    def get_rule(
        self,
        catalog_entry_id: str,
        scope: ActivationScope,
        research_space_id: UUID | None = None,
    ) -> DataSourceActivation | None:
        return self._rules.get(self._key(catalog_entry_id, scope, research_space_id))

    def list_rules_for_source(
        self,
        catalog_entry_id: str,
    ) -> list[DataSourceActivation]:
        return [rule for key, rule in self._rules.items() if key[0] == catalog_entry_id]

    def list_rules_for_sources(
        self,
        catalog_entry_ids: list[str],
    ) -> dict[str, list[DataSourceActivation]]:
        rules_by_source: dict[str, list[DataSourceActivation]] = {
            entry_id: [] for entry_id in catalog_entry_ids
        }
        for (catalog_entry_id, _scope, _space_id), rule in self._rules.items():
            if catalog_entry_id in rules_by_source:
                rules_by_source[catalog_entry_id].append(rule)
        return rules_by_source

    def set_rule(
        self,
        *,
        catalog_entry_id: str,
        scope: ActivationScope,
        permission_level: PermissionLevel,
        updated_by: UUID,
        research_space_id: UUID | None = None,
    ) -> DataSourceActivation:
        existing = self.get_rule(catalog_entry_id, scope, research_space_id)
        now = datetime.now(UTC)
        if existing:
            rule = existing.model_copy(
                update={
                    "permission_level": permission_level,
                    "updated_by": updated_by,
                    "updated_at": now,
                },
            )
        else:
            rule = DataSourceActivation(
                id=uuid4(),
                catalog_entry_id=catalog_entry_id,
                scope=scope,
                permission_level=permission_level,
                research_space_id=research_space_id,
                updated_by=updated_by,
                created_at=now,
                updated_at=now,
            )
        self._rules[self._key(catalog_entry_id, scope, research_space_id)] = rule
        return rule

    def delete_rule(
        self,
        *,
        catalog_entry_id: str,
        scope: ActivationScope,
        research_space_id: UUID | None = None,
    ) -> None:
        self._rules.pop(self._key(catalog_entry_id, scope, research_space_id), None)


@pytest.fixture
def service() -> DataSourceActivationService:
    return DataSourceActivationService(InMemoryActivationRepository())


def test_default_permissions_block_all_except_pubmed_and_clinvar(
    service: DataSourceActivationService,
) -> None:
    assert service.is_source_active("pubmed") is True
    assert service.is_source_active("pubmed", uuid4()) is True
    assert service.is_source_active("clinvar") is True
    assert service.is_source_active("clinvar", uuid4()) is True


def test_global_rule_controls_default(service: DataSourceActivationService) -> None:
    source_id = "catalog-2"
    admin_id = uuid4()
    service.set_global_activation(
        catalog_entry_id=source_id,
        permission_level=PermissionLevel.BLOCKED,
        updated_by=admin_id,
    )
    assert service.is_source_active(source_id) is False
    summary = service.get_availability_summary(source_id)
    assert summary.global_rule is not None
    assert summary.global_rule.is_active is False


def test_project_override_takes_precedence(
    service: DataSourceActivationService,
) -> None:
    source_id = "catalog-3"
    space_id = uuid4()
    admin_id = uuid4()
    service.set_global_activation(
        catalog_entry_id=source_id,
        permission_level=PermissionLevel.BLOCKED,
        updated_by=admin_id,
    )
    service.set_project_activation(
        catalog_entry_id=source_id,
        research_space_id=space_id,
        permission_level=PermissionLevel.AVAILABLE,
        updated_by=admin_id,
    )
    assert service.is_source_active(source_id, space_id) is True
    assert service.is_source_active(source_id) is False


def test_clearing_rules_reverts_to_default(
    service: DataSourceActivationService,
) -> None:
    source_id = "catalog-4"
    admin_id = uuid4()
    service.set_global_activation(
        catalog_entry_id=source_id,
        permission_level=PermissionLevel.BLOCKED,
        updated_by=admin_id,
    )
    service.clear_global_activation(source_id)
    assert service.is_source_active(source_id) is False
    service.set_global_activation(
        catalog_entry_id="pubmed",
        permission_level=PermissionLevel.BLOCKED,
        updated_by=admin_id,
    )
    service.clear_global_activation("pubmed")
    assert service.is_source_active("pubmed") is True


def test_bulk_summary_preserves_order(
    service: DataSourceActivationService,
) -> None:
    admin_id = uuid4()
    ids = ["catalog-5", "catalog-6"]
    service.set_global_activation(
        catalog_entry_id=ids[0],
        permission_level=PermissionLevel.BLOCKED,
        updated_by=admin_id,
    )
    service.set_project_activation(
        catalog_entry_id=ids[1],
        research_space_id=uuid4(),
        permission_level=PermissionLevel.BLOCKED,
        updated_by=admin_id,
    )

    summaries = service.get_availability_summaries([ids[1], ids[0]])
    assert [summary.catalog_entry_id for summary in summaries] == [ids[1], ids[0]]
    assert summaries[0].effective_is_active is False
    assert summaries[1].effective_is_active is False
