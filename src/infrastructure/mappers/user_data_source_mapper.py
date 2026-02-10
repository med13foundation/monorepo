"""
Mapper for UserDataSource entities and database models.

Provides bidirectional mapping between domain entities and database models
for the Data Sources module.
"""

from datetime import UTC, datetime

from src.domain.entities.user_data_source import (
    UserDataSource,
)

# Stub for missing UserDataSourceModel
UserDataSourceModel = object


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat(timespec="seconds")


class UserDataSourceMapper:
    """
    Bidirectional mapper between UserDataSource domain entities and database models.

    Handles conversion between domain objects and database representations,
    ensuring type safety and data integrity.
    """

    @staticmethod
    def to_domain(model: UserDataSourceModel) -> UserDataSource:
        """
        Convert a database model to a domain entity.

        Args:
            model: The UserDataSourceModel to convert

        Returns:
            The corresponding UserDataSource domain entity
        """
        msg = "UserDataSourceModel has been removed."
        raise NotImplementedError(msg)

    @staticmethod
    def to_model(entity: UserDataSource) -> UserDataSourceModel:
        """
        Convert a domain entity to a database model.

        Args:
            entity: The UserDataSource entity to convert

        Returns:
            The corresponding UserDataSourceModel
        """
        msg = "UserDataSourceModel has been removed."
        raise NotImplementedError(msg)
