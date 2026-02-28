"""Domain port for dictionary semantic-layer operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.domain.entities.kernel.dictionary import (
        DictionaryChangelog,
        DictionaryEntityType,
        DictionaryRelationType,
        DictionarySearchResult,
        EntityResolutionPolicy,
        RelationConstraint,
        TransformRegistry,
        TransformVerificationResult,
        ValueSet,
        ValueSetItem,
        VariableDefinition,
        VariableSynonym,
    )
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings


class DictionaryPort(ABC):
    """Domain-wide interface for dictionary management and lookup."""

    @abstractmethod
    def get_variable(self, variable_id: str) -> VariableDefinition | None:
        """Return a variable definition by ID."""

    @abstractmethod
    def list_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[VariableDefinition]:
        """List variable definitions with optional filters."""

    @abstractmethod
    def resolve_synonym(
        self,
        synonym: str,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> VariableDefinition | None:
        """Resolve a synonym to its canonical variable definition."""

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
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> VariableDefinition:
        """Create a new variable definition with provenance metadata."""

    @abstractmethod
    def create_synonym(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        synonym: str,
        source: str | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> VariableSynonym:
        """Create a variable synonym with provenance metadata."""

    @abstractmethod
    def set_review_status(
        self,
        variable_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> VariableDefinition:
        """Update review status for a variable definition."""

    @abstractmethod
    def revoke_variable(
        self,
        variable_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> VariableDefinition:
        """Revoke a variable definition with an audit reason."""

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
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ValueSet:
        """Create a value set with provenance metadata."""

    @abstractmethod
    def get_value_set(self, value_set_id: str) -> ValueSet | None:
        """Return a value set by ID."""

    @abstractmethod
    def list_value_sets(
        self,
        *,
        variable_id: str | None = None,
    ) -> list[ValueSet]:
        """List value sets."""

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
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ValueSetItem:
        """Create a value set item with provenance metadata."""

    @abstractmethod
    def list_value_set_items(
        self,
        *,
        value_set_id: str,
        include_inactive: bool = False,
    ) -> list[ValueSetItem]:
        """List value set items."""

    @abstractmethod
    def set_value_set_item_active(
        self,
        value_set_item_id: int,
        *,
        is_active: bool,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> ValueSetItem:
        """Activate/deactivate a value set item."""

    @abstractmethod
    def dictionary_search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        """Search dictionary entries across semantic dimensions."""

    @abstractmethod
    def dictionary_search_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        """List dictionary entries filtered by domain context."""

    @abstractmethod
    def reembed_descriptions(
        self,
        *,
        model_name: str | None = None,
        limit_per_dimension: int | None = None,
        changed_by: str = "system:reembed",
        source_ref: str | None = None,
    ) -> int:
        """Recompute description embeddings across dictionary dimensions."""

    @abstractmethod
    def is_relation_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check whether a relation triple is allowed."""

    @abstractmethod
    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check whether a relation triple requires evidence."""

    @abstractmethod
    def create_relation_constraint(  # noqa: PLR0913
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
        is_allowed: bool = True,
        requires_evidence: bool = True,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> RelationConstraint:
        """Create a relation-constraint triple with provenance metadata."""

    @abstractmethod
    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[RelationConstraint]:
        """List relation constraints."""

    @abstractmethod
    def get_resolution_policy(
        self,
        entity_type: str,
        *,
        include_inactive: bool = False,
    ) -> EntityResolutionPolicy | None:
        """Return the deduplication policy for an entity type."""

    @abstractmethod
    def list_resolution_policies(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[EntityResolutionPolicy]:
        """List all entity-resolution policies."""

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
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> DictionaryEntityType:
        """Create a first-class dictionary entity type."""

    @abstractmethod
    def list_entity_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryEntityType]:
        """List dictionary entity types."""

    @abstractmethod
    def get_entity_type(
        self,
        entity_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryEntityType | None:
        """Return a dictionary entity type by ID."""

    @abstractmethod
    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryEntityType:
        """Update review status for an entity type."""

    @abstractmethod
    def revoke_entity_type(
        self,
        entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryEntityType:
        """Revoke an entity type with an audit reason."""

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
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> DictionaryRelationType:
        """Create a first-class dictionary relation type."""

    @abstractmethod
    def list_relation_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryRelationType]:
        """List dictionary relation types."""

    @abstractmethod
    def get_relation_type(
        self,
        relation_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryRelationType | None:
        """Return a dictionary relation type by ID."""

    @abstractmethod
    def set_relation_type_review_status(
        self,
        relation_type_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationType:
        """Update review status for a relation type."""

    @abstractmethod
    def revoke_relation_type(
        self,
        relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationType:
        """Revoke a relation type with an audit reason."""

    @abstractmethod
    def list_changelog_entries(
        self,
        *,
        table_name: str | None = None,
        record_id: str | None = None,
        limit: int = 100,
    ) -> list[DictionaryChangelog]:
        """List dictionary changelog entries with optional filters."""

    @abstractmethod
    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
        *,
        include_inactive: bool = False,
        require_production: bool = False,
    ) -> TransformRegistry | None:
        """Return an active transform for the given unit pair."""

    @abstractmethod
    def list_transforms(
        self,
        *,
        status: str = "ACTIVE",
        include_inactive: bool = False,
        production_only: bool = False,
    ) -> list[TransformRegistry]:
        """List transforms filtered by status."""

    @abstractmethod
    def verify_transform(self, transform_id: str) -> TransformVerificationResult:
        """Verify one transform against its test fixtures."""

    @abstractmethod
    def verify_all_transforms(
        self,
        *,
        status: str = "ACTIVE",
        include_inactive: bool = False,
    ) -> list[TransformVerificationResult]:
        """Verify all transforms with test fixtures."""

    @abstractmethod
    def promote_transform(
        self,
        transform_id: str,
        *,
        reviewed_by: str,
    ) -> TransformRegistry:
        """Mark a transform as production-allowed after verification."""

    @abstractmethod
    def merge_variable_definition(
        self,
        source_variable_id: str,
        target_variable_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> VariableDefinition:
        """Supersede one variable with another while preserving audit lineage."""

    @abstractmethod
    def merge_entity_type(
        self,
        source_entity_type_id: str,
        target_entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryEntityType:
        """Supersede one entity type with another while preserving audit lineage."""

    @abstractmethod
    def merge_relation_type(
        self,
        source_relation_type_id: str,
        target_relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationType:
        """Supersede one relation type with another while preserving audit lineage."""
