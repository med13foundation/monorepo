"""Domain-neutral feature-flag contracts for graph domain packs."""

from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class FeatureFlagDefinition:
    """Runtime env contract for one graph-domain-pack feature."""

    primary_env_name: str
    legacy_env_name: str | None = None
    default_enabled: bool = False

    @property
    def default_value(self) -> str:
        return "1" if self.default_enabled else "0"

    @property
    def env_display_name(self) -> str:
        if self.legacy_env_name is None:
            return f"{self.primary_env_name}=1"
        return f"{self.primary_env_name}=1 (legacy alias: {self.legacy_env_name}=1)"


@dataclass(frozen=True)
class GraphFeatureFlags:
    """Feature-flag definitions exposed by one graph domain pack."""

    entity_embeddings: FeatureFlagDefinition
    relation_suggestions: FeatureFlagDefinition
    hypothesis_generation: FeatureFlagDefinition
    search_agent: FeatureFlagDefinition


def is_flag_enabled(definition: FeatureFlagDefinition) -> bool:
    """Resolve one graph-domain-pack feature flag from env."""
    value = os.getenv(definition.primary_env_name)
    if value is not None:
        return value.strip().lower() in _TRUE_VALUES

    if definition.legacy_env_name is not None:
        legacy_value = os.getenv(definition.legacy_env_name)
        if legacy_value is not None:
            return legacy_value.strip().lower() in _TRUE_VALUES

    return definition.default_value in {"1", "true", "yes", "on"}
