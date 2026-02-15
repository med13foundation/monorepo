"""
Dictionary repository interface.

Defines the abstract contract for reads/writes to the Layer 1
dictionary tables: variable_definitions, variable_synonyms,
transform_registry, entity_resolution_policies, and relation_constraints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

    from src.domain.entities.kernel.dictionary import (
        DictionaryChangelog,
        DictionaryEntityType,
        DictionaryRelationType,
        DictionarySearchResult,
        EntityResolutionPolicy,
        RelationConstraint,
        TransformRegistry,
        ValueSet,
        ValueSetItem,
        VariableDefinition,
        VariableSynonym,
    )
    from src.type_definitions.common import JSONObject


class DictionaryRepository(ABC):
    """
    Read/write interface for the kernel dictionary (Layer 1).

    The dictionary is the single source of truth for what data elements
    are allowed, how they relate, and how entities are deduplicated.
    """

    # ── Variable definitions ──────────────────────────────────────────

    @abstractmethod
    def get_variable(self, variable_id: str) -> VariableDefinition | None:
        """Retrieve a single variable definition by ID."""

    @abstractmethod
    def find_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
    ) -> list[VariableDefinition]:
        """List variable definitions, optionally filtered by domain and/or type."""

    @abstractmethod
    def find_variable_by_synonym(
        self,
        synonym: str,
    ) -> VariableDefinition | None:
        """
        Resolve a field name to its canonical variable definition.

        Looks up the synonym in ``variable_synonyms`` and returns
        the parent ``VariableDefinition`` if found.
        """

    @abstractmethod
    def create_variable(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        domain_context: str = "general",
        sensitivity: str = "INTERNAL",
        preferred_unit: str | None = None,
        constraints: JSONObject | None = None,
        description: str | None = None,
        description_embedding: list[float] | None = None,
        embedded_at: datetime | None = None,
        embedding_model: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE",
    ) -> VariableDefinition:
        """Create a new variable definition."""

    @abstractmethod
    def set_variable_embedding(  # noqa: PLR0913
        self,
        variable_id: str,
        *,
        description_embedding: list[float] | None,
        embedded_at: datetime,
        embedding_model: str,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> VariableDefinition:
        """Update embedding metadata for a variable definition."""

    @abstractmethod
    def create_synonym(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        synonym: str,
        source: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE",
    ) -> VariableSynonym:
        """Create a synonym entry for a variable definition."""

    @abstractmethod
    def set_variable_review_status(
        self,
        variable_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> VariableDefinition:
        """Set review state and metadata for a variable definition."""

    @abstractmethod
    def revoke_variable(
        self,
        variable_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> VariableDefinition:
        """Revoke a variable definition with a mandatory reason."""

    @abstractmethod
    def create_value_set(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        variable_id: str,
        name: str,
        description: str | None = None,
        external_ref: str | None = None,
        is_extensible: bool = False,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE",
    ) -> ValueSet:
        """Create a value set for a CODED variable."""

    @abstractmethod
    def get_value_set(self, value_set_id: str) -> ValueSet | None:
        """Retrieve a single value set by ID."""

    @abstractmethod
    def find_value_sets(
        self,
        *,
        variable_id: str | None = None,
    ) -> list[ValueSet]:
        """List value sets, optionally filtered by variable."""

    @abstractmethod
    def create_value_set_item(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        code: str,
        display_label: str,
        synonyms: list[str] | None = None,
        external_ref: str | None = None,
        sort_order: int = 0,
        is_active: bool = True,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE",
    ) -> ValueSetItem:
        """Create a value set item for a value set."""

    @abstractmethod
    def find_value_set_items(
        self,
        *,
        value_set_id: str,
        include_inactive: bool = False,
    ) -> list[ValueSetItem]:
        """List value set items for a value set."""

    @abstractmethod
    def set_value_set_item_active(
        self,
        value_set_item_id: int,
        *,
        is_active: bool,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> ValueSetItem:
        """Activate/deactivate a value set item."""

    # ── Entity resolution policies ────────────────────────────────────

    @abstractmethod
    def get_resolution_policy(
        self,
        entity_type: str,
    ) -> EntityResolutionPolicy | None:
        """Get the resolution policy for a given entity type."""

    @abstractmethod
    def find_resolution_policies(self) -> list[EntityResolutionPolicy]:
        """List all entity resolution policies."""

    @abstractmethod
    def create_entity_type(  # noqa: PLR0913
        self,
        *,
        entity_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        external_ontology_ref: str | None = None,
        expected_properties: JSONObject | None = None,
        description_embedding: list[float] | None = None,
        embedded_at: datetime | None = None,
        embedding_model: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE",
    ) -> DictionaryEntityType:
        """Create a first-class entity type."""

    @abstractmethod
    def set_entity_type_embedding(  # noqa: PLR0913
        self,
        entity_type_id: str,
        *,
        description_embedding: list[float] | None,
        embedded_at: datetime,
        embedding_model: str,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryEntityType:
        """Update embedding metadata for an entity type."""

    @abstractmethod
    def find_entity_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> list[DictionaryEntityType]:
        """List entity types with optional domain filtering."""

    @abstractmethod
    def get_entity_type(self, entity_type_id: str) -> DictionaryEntityType | None:
        """Retrieve a single dictionary entity type by ID."""

    @abstractmethod
    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> DictionaryEntityType:
        """Set review state and metadata for a dictionary entity type."""

    @abstractmethod
    def revoke_entity_type(
        self,
        entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryEntityType:
        """Revoke a dictionary entity type with a mandatory reason."""

    @abstractmethod
    def create_relation_type(  # noqa: PLR0913
        self,
        *,
        relation_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        is_directional: bool = True,
        inverse_label: str | None = None,
        description_embedding: list[float] | None = None,
        embedded_at: datetime | None = None,
        embedding_model: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] = "ACTIVE",
    ) -> DictionaryRelationType:
        """Create a first-class relation type."""

    @abstractmethod
    def set_relation_type_embedding(  # noqa: PLR0913
        self,
        relation_type_id: str,
        *,
        description_embedding: list[float] | None,
        embedded_at: datetime,
        embedding_model: str,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryRelationType:
        """Update embedding metadata for a relation type."""

    @abstractmethod
    def find_relation_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> list[DictionaryRelationType]:
        """List relation types with optional domain filtering."""

    @abstractmethod
    def get_relation_type(
        self,
        relation_type_id: str,
    ) -> DictionaryRelationType | None:
        """Retrieve a single dictionary relation type by ID."""

    @abstractmethod
    def set_relation_type_review_status(
        self,
        relation_type_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationType:
        """Set review state and metadata for a dictionary relation type."""

    @abstractmethod
    def revoke_relation_type(
        self,
        relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryRelationType:
        """Revoke a dictionary relation type with a mandatory reason."""

    @abstractmethod
    def find_changelog_entries(
        self,
        *,
        table_name: str | None = None,
        record_id: str | None = None,
        limit: int = 100,
    ) -> list[DictionaryChangelog]:
        """List changelog entries with optional table/record filters."""

    @abstractmethod
    def search_dictionary(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        query_embeddings: dict[str, list[float]] | None = None,
    ) -> list[DictionarySearchResult]:
        """Search dictionary dimensions with exact/fuzzy/vector matching."""

    @abstractmethod
    def search_dictionary_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 50,
    ) -> list[DictionarySearchResult]:
        """List dictionary entries scoped to a single domain context."""

    # ── Relation constraints ──────────────────────────────────────────

    @abstractmethod
    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
    ) -> list[RelationConstraint]:
        """List relation constraints, optionally filtered."""

    @abstractmethod
    def is_triple_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check if a (source_type, relation_type, target_type) triple is allowed."""

    @abstractmethod
    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check if the given triple requires evidence."""

    # ── Transform registry ────────────────────────────────────────────

    @abstractmethod
    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
    ) -> TransformRegistry | None:
        """Find a unit transformation between input and output units."""

    @abstractmethod
    def find_transforms(
        self,
        *,
        status: str = "ACTIVE",
    ) -> list[TransformRegistry]:
        """List all transforms, optionally filtered by status."""


__all__ = ["DictionaryRepository"]
