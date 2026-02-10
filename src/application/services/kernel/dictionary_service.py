"""
Dictionary application service.

Provides read-only access to the kernel dictionary — variable
definitions, synonyms, relation constraints, and resolution policies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.models.database.kernel.dictionary import (
        EntityResolutionPolicyModel,
        RelationConstraintModel,
        TransformRegistryModel,
        VariableDefinitionModel,
    )

logger = logging.getLogger(__name__)


class DictionaryService:
    """
    Application service for the kernel dictionary.

    Provides a clean API over the dictionary repository for
    variable lookup, synonym resolution, and constraint checks.
    """

    def __init__(self, dictionary_repo: DictionaryRepository) -> None:
        self._dictionary = dictionary_repo

    # ── Variable operations ───────────────────────────────────────────

    def get_variable(self, variable_id: str) -> VariableDefinitionModel | None:
        """Look up a variable definition by ID."""
        return self._dictionary.get_variable(variable_id)

    def list_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
    ) -> list[VariableDefinitionModel]:
        """List variables, optionally filtered by domain and/or type."""
        return self._dictionary.find_variables(
            domain_context=domain_context,
            data_type=data_type,
        )

    def resolve_synonym(self, synonym: str) -> VariableDefinitionModel | None:
        """
        Resolve a field name to its canonical variable.

        Used during ingestion to map column headers / JSON keys
        to known variable definitions.
        """
        return self._dictionary.find_variable_by_synonym(synonym)

    # ── Relation constraint checks ────────────────────────────────────

    def is_relation_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check whether a triple is permitted by the constraint schema."""
        return self._dictionary.is_triple_allowed(
            source_type,
            relation_type,
            target_type,
        )

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
    ) -> list[RelationConstraintModel]:
        """List constraints, optionally filtered."""
        return self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
        )

    # ── Resolution policies ───────────────────────────────────────────

    def get_resolution_policy(
        self,
        entity_type: str,
    ) -> EntityResolutionPolicyModel | None:
        """Get the dedup strategy for an entity type."""
        return self._dictionary.get_resolution_policy(entity_type)

    def list_resolution_policies(self) -> list[EntityResolutionPolicyModel]:
        """List all entity resolution policies."""
        return self._dictionary.find_resolution_policies()

    # ── Transforms ────────────────────────────────────────────────────

    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
    ) -> TransformRegistryModel | None:
        """Find a unit transformation."""
        return self._dictionary.get_transform(input_unit, output_unit)

    def list_transforms(
        self,
        *,
        status: str = "ACTIVE",
    ) -> list[TransformRegistryModel]:
        """List all transforms."""
        return self._dictionary.find_transforms(status=status)


__all__ = ["DictionaryService"]
