"""Dictionary management application service.

Provides semantic-layer operations over the kernel dictionary, including
provenance-aware creation and review lifecycle management.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.domain.ports.dictionary_port import DictionaryPort

if TYPE_CHECKING:
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
    from src.domain.ports.text_embedding_port import TextEmbeddingPort
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings

logger = logging.getLogger(__name__)

ReviewStatus = Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]

_REVIEW_STATUSES: frozenset[str] = frozenset({"ACTIVE", "PENDING_REVIEW", "REVOKED"})
_ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "ACTIVE": frozenset({"ACTIVE", "PENDING_REVIEW", "REVOKED"}),
    "PENDING_REVIEW": frozenset({"ACTIVE", "PENDING_REVIEW", "REVOKED"}),
    "REVOKED": frozenset({"REVOKED", "ACTIVE"}),
}
_VECTOR_SEARCH_DIMENSIONS: frozenset[str] = frozenset(
    {"variables", "entity_types", "relation_types"},
)
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _parse_review_status(value: str) -> ReviewStatus:
    """Normalize and validate review status values without casts."""
    normalized = value.strip().upper()
    if normalized == "ACTIVE":
        return "ACTIVE"
    if normalized == "PENDING_REVIEW":
        return "PENDING_REVIEW"
    if normalized == "REVOKED":
        return "REVOKED"
    msg = f"Invalid review_status '{value}'"
    raise ValueError(msg)


class DictionaryManagementService(DictionaryPort):
    """Application service for dictionary lookup and governance operations."""

    def __init__(
        self,
        dictionary_repo: DictionaryRepository,
        embedding_provider: TextEmbeddingPort | None = None,
        default_embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self._dictionary = dictionary_repo
        self._embedding_provider = embedding_provider
        normalized_model = default_embedding_model.strip()
        self._default_embedding_model = (
            normalized_model if normalized_model else _DEFAULT_EMBEDDING_MODEL
        )

    def _resolve_embedding_model(self, model_name: str | None = None) -> str:
        if model_name is None:
            return self._default_embedding_model
        normalized = model_name.strip()
        return normalized if normalized else self._default_embedding_model

    def _embed_text(self, text: str, *, model_name: str) -> list[float] | None:
        if self._embedding_provider is None:
            return None
        normalized = text.strip()
        if not normalized:
            return None
        return self._embedding_provider.embed_text(
            normalized,
            model_name=model_name,
        )

    def _embed_description(
        self,
        description: str | None,
        *,
        model_name: str,
    ) -> tuple[list[float] | None, datetime | None, str | None]:
        if description is None:
            return None, None, None
        embedding = self._embed_text(description, model_name=model_name)
        if embedding is None:
            return None, None, None
        return embedding, datetime.now(UTC), model_name

    def _build_query_embeddings(
        self,
        terms: list[str],
        *,
        model_name: str,
    ) -> dict[str, list[float]] | None:
        if self._embedding_provider is None:
            return None

        embeddings: dict[str, list[float]] = {}
        for term in terms:
            normalized_term = term.strip().casefold()
            if not normalized_term or normalized_term in embeddings:
                continue

            embedding = self._embed_text(normalized_term, model_name=model_name)
            if embedding is None:
                continue
            embeddings[normalized_term] = embedding

        if not embeddings:
            return None
        return embeddings

    def _normalize_review_status(self, review_status: str) -> ReviewStatus:
        return _parse_review_status(review_status)

    def _normalize_created_by(self, created_by: str) -> str:
        normalized = created_by.strip()
        if not normalized:
            msg = "created_by is required"
            raise ValueError(msg)
        return normalized

    def _resolve_agent_creation_review_status(
        self,
        *,
        created_by: str,
        research_space_settings: ResearchSpaceSettings | None,
    ) -> ReviewStatus:
        if not created_by.startswith("agent:"):
            return "ACTIVE"
        if research_space_settings is None:
            return "ACTIVE"

        raw_policy = research_space_settings.get("dictionary_agent_creation_policy")
        if not isinstance(raw_policy, str):
            return "ACTIVE"

        try:
            return _parse_review_status(raw_policy)
        except ValueError:
            return "ACTIVE"

    def _validate_status_transition(
        self,
        *,
        from_status: str,
        to_status: ReviewStatus,
    ) -> None:
        allowed = _ALLOWED_STATUS_TRANSITIONS.get(
            from_status,
            frozenset({"ACTIVE", "PENDING_REVIEW", "REVOKED"}),
        )
        if to_status not in allowed:
            msg = f"Invalid review transition: {from_status} -> {to_status}"
            raise ValueError(msg)

    # ── Variable operations ───────────────────────────────────────────

    def get_variable(self, variable_id: str) -> VariableDefinition | None:
        """Look up a variable definition by ID."""
        return self._dictionary.get_variable(variable_id)

    def list_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
    ) -> list[VariableDefinition]:
        """List variables, optionally filtered by domain and/or type."""
        return self._dictionary.find_variables(
            domain_context=domain_context,
            data_type=data_type,
        )

    def resolve_synonym(self, synonym: str) -> VariableDefinition | None:
        """Resolve a field name to its canonical variable."""
        return self._dictionary.find_variable_by_synonym(synonym)

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
        """Create a new dictionary variable definition with provenance."""
        created_by_normalized = self._normalize_created_by(created_by)

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        embedding_model = self._resolve_embedding_model()
        description_embedding, embedded_at, resolved_embedding_model = (
            self._embed_description(
                description,
                model_name=embedding_model,
            )
        )

        return self._dictionary.create_variable(
            variable_id=variable_id,
            canonical_name=canonical_name,
            display_name=display_name,
            data_type=data_type,
            domain_context=domain_context,
            sensitivity=sensitivity,
            preferred_unit=preferred_unit,
            constraints=constraints,
            description=description,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=resolved_embedding_model,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

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
        """Create a synonym entry for a variable definition."""
        created_by_normalized = self._normalize_created_by(created_by)

        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            msg = f"Variable '{variable_id}' not found"
            raise ValueError(msg)

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )

        return self._dictionary.create_synonym(
            variable_id=variable_id,
            synonym=synonym,
            source=source,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def set_review_status(
        self,
        variable_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> VariableDefinition:
        """Set review state for a dictionary variable."""
        reviewed_by_normalized = reviewed_by.strip()
        if not reviewed_by_normalized:
            msg = "reviewed_by is required"
            raise ValueError(msg)

        target_status = self._normalize_review_status(review_status)
        current = self._dictionary.get_variable(variable_id)
        if current is None:
            msg = f"Variable '{variable_id}' not found"
            raise ValueError(msg)

        self._validate_status_transition(
            from_status=current.review_status,
            to_status=target_status,
        )

        normalized_reason: str | None = None
        if target_status == "REVOKED":
            if revocation_reason is None or not revocation_reason.strip():
                msg = "revocation_reason is required when setting REVOKED status"
                raise ValueError(msg)
            normalized_reason = revocation_reason.strip()
        elif revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)

        return self._dictionary.set_variable_review_status(
            variable_id,
            review_status=target_status,
            reviewed_by=reviewed_by_normalized,
            revocation_reason=normalized_reason,
        )

    def revoke_variable(
        self,
        variable_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> VariableDefinition:
        """Convenience operation for revoking a variable."""
        return self.set_review_status(
            variable_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

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
        """Create a value set for a CODED dictionary variable."""
        created_by_normalized = self._normalize_created_by(created_by)
        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            msg = f"Variable '{variable_id}' not found"
            raise ValueError(msg)
        if variable.data_type != "CODED":
            msg = (
                f"Variable '{variable_id}' has data_type '{variable.data_type}' and "
                "cannot have a value set"
            )
            raise ValueError(msg)

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )

        return self._dictionary.create_value_set(
            value_set_id=value_set_id,
            variable_id=variable_id,
            name=name,
            description=description,
            external_ref=external_ref,
            is_extensible=is_extensible,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def get_value_set(self, value_set_id: str) -> ValueSet | None:
        """Get a value set by ID."""
        return self._dictionary.get_value_set(value_set_id)

    def list_value_sets(
        self,
        *,
        variable_id: str | None = None,
    ) -> list[ValueSet]:
        """List value sets with optional variable filtering."""
        return self._dictionary.find_value_sets(variable_id=variable_id)

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
        """Create a value set item with extensibility policy checks."""
        created_by_normalized = self._normalize_created_by(created_by)
        value_set = self._dictionary.get_value_set(value_set_id)
        if value_set is None:
            msg = f"Value set '{value_set_id}' not found"
            raise ValueError(msg)
        if created_by_normalized.startswith("agent:") and not value_set.is_extensible:
            msg = (
                f"Value set '{value_set_id}' is not extensible; "
                "agent cannot add new items"
            )
            raise ValueError(msg)

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )

        return self._dictionary.create_value_set_item(
            value_set_id=value_set_id,
            code=code,
            display_label=display_label,
            synonyms=synonyms,
            external_ref=external_ref,
            sort_order=sort_order,
            is_active=is_active,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def list_value_set_items(
        self,
        *,
        value_set_id: str,
        include_inactive: bool = False,
    ) -> list[ValueSetItem]:
        """List value set items for a value set."""
        return self._dictionary.find_value_set_items(
            value_set_id=value_set_id,
            include_inactive=include_inactive,
        )

    def set_value_set_item_active(
        self,
        value_set_item_id: int,
        *,
        is_active: bool,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> ValueSetItem:
        """Activate/deactivate a value set item with audit metadata."""
        reviewed_by_normalized = reviewed_by.strip()
        if not reviewed_by_normalized:
            msg = "reviewed_by is required"
            raise ValueError(msg)

        normalized_reason: str | None = None
        if not is_active:
            if revocation_reason is None or not revocation_reason.strip():
                msg = "revocation_reason is required when deactivating a value set item"
                raise ValueError(msg)
            normalized_reason = revocation_reason.strip()
        elif revocation_reason is not None:
            msg = "revocation_reason is only valid when deactivating a value set item"
            raise ValueError(msg)

        return self._dictionary.set_value_set_item_active(
            value_set_item_id,
            is_active=is_active,
            reviewed_by=reviewed_by_normalized,
            revocation_reason=normalized_reason,
        )

    # ── Search and embeddings ────────────────────────────────────────

    def dictionary_search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
    ) -> list[DictionarySearchResult]:
        """Search dictionary entries with exact/fuzzy/vector matching."""
        normalized_terms = [term for term in terms if term.strip()]
        if not normalized_terms:
            return []

        embedding_dimensions = dimensions or list(_VECTOR_SEARCH_DIMENSIONS)
        should_embed = any(
            dimension.strip().lower() in _VECTOR_SEARCH_DIMENSIONS
            for dimension in embedding_dimensions
        )
        query_embeddings: dict[str, list[float]] | None = None
        if should_embed:
            query_embeddings = self._build_query_embeddings(
                normalized_terms,
                model_name=self._resolve_embedding_model(),
            )

        return self._dictionary.search_dictionary(
            terms=normalized_terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=query_embeddings,
        )

    def dictionary_search_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 50,
    ) -> list[DictionarySearchResult]:
        """List dictionary entries scoped to one domain context."""
        return self._dictionary.search_dictionary_by_domain(
            domain_context=domain_context,
            limit=limit,
        )

    def reembed_descriptions(  # noqa: C901,PLR0912
        self,
        *,
        model_name: str | None = None,
        limit_per_dimension: int | None = None,
        changed_by: str = "system:reembed",
        source_ref: str | None = None,
    ) -> int:
        """Recompute description embeddings for variables, entity, and relation types."""
        if self._embedding_provider is None:
            logger.warning(
                "Re-embedding requested but no embedding provider is configured",
            )
            return 0

        normalized_actor = changed_by.strip()
        if not normalized_actor:
            msg = "changed_by is required"
            raise ValueError(msg)

        normalized_limit: int | None = None
        if limit_per_dimension is not None:
            normalized_limit = max(1, limit_per_dimension)

        selected_model = self._resolve_embedding_model(model_name)
        updated_records = 0

        variables = self._dictionary.find_variables()
        if normalized_limit is not None:
            variables = variables[:normalized_limit]
        for variable in variables:
            if variable.description is None or not variable.description.strip():
                continue
            embedding = self._embed_text(
                variable.description,
                model_name=selected_model,
            )
            if embedding is None:
                continue
            self._dictionary.set_variable_embedding(
                variable.id,
                description_embedding=embedding,
                embedded_at=datetime.now(UTC),
                embedding_model=selected_model,
                changed_by=normalized_actor,
                source_ref=source_ref,
            )
            updated_records += 1

        entity_types = self._dictionary.find_entity_types()
        if normalized_limit is not None:
            entity_types = entity_types[:normalized_limit]
        for entity_type in entity_types:
            if not entity_type.description.strip():
                continue
            embedding = self._embed_text(
                entity_type.description,
                model_name=selected_model,
            )
            if embedding is None:
                continue
            self._dictionary.set_entity_type_embedding(
                entity_type.id,
                description_embedding=embedding,
                embedded_at=datetime.now(UTC),
                embedding_model=selected_model,
                changed_by=normalized_actor,
                source_ref=source_ref,
            )
            updated_records += 1

        relation_types = self._dictionary.find_relation_types()
        if normalized_limit is not None:
            relation_types = relation_types[:normalized_limit]
        for relation_type in relation_types:
            if not relation_type.description.strip():
                continue
            embedding = self._embed_text(
                relation_type.description,
                model_name=selected_model,
            )
            if embedding is None:
                continue
            self._dictionary.set_relation_type_embedding(
                relation_type.id,
                description_embedding=embedding,
                embedded_at=datetime.now(UTC),
                embedding_model=selected_model,
                changed_by=normalized_actor,
                source_ref=source_ref,
            )
            updated_records += 1

        return updated_records

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

    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check whether a triple requires evidence."""
        return self._dictionary.requires_evidence(
            source_type,
            relation_type,
            target_type,
        )

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
    ) -> list[RelationConstraint]:
        """List constraints, optionally filtered."""
        return self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
        )

    # ── Resolution policies ───────────────────────────────────────────

    def get_resolution_policy(
        self,
        entity_type: str,
    ) -> EntityResolutionPolicy | None:
        """Get the dedup strategy for an entity type."""
        return self._dictionary.get_resolution_policy(entity_type)

    def list_resolution_policies(self) -> list[EntityResolutionPolicy]:
        """List all entity resolution policies."""
        return self._dictionary.find_resolution_policies()

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
        """Create a dictionary entity type with provenance metadata."""
        created_by_normalized = self._normalize_created_by(created_by)
        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        embedding_model = self._resolve_embedding_model()
        description_embedding, embedded_at, resolved_embedding_model = (
            self._embed_description(
                description,
                model_name=embedding_model,
            )
        )
        return self._dictionary.create_entity_type(
            entity_type=entity_type,
            display_name=display_name,
            description=description,
            domain_context=domain_context,
            external_ontology_ref=external_ontology_ref,
            expected_properties=expected_properties,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=resolved_embedding_model,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def list_entity_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> list[DictionaryEntityType]:
        """List dictionary entity types."""
        return self._dictionary.find_entity_types(domain_context=domain_context)

    def get_entity_type(self, entity_type_id: str) -> DictionaryEntityType | None:
        """Get a dictionary entity type by ID."""
        return self._dictionary.get_entity_type(entity_type_id)

    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryEntityType:
        """Set review state for a dictionary entity type."""
        reviewed_by_normalized = reviewed_by.strip()
        if not reviewed_by_normalized:
            msg = "reviewed_by is required"
            raise ValueError(msg)

        target_status = self._normalize_review_status(review_status)
        current = self._dictionary.get_entity_type(entity_type_id)
        if current is None:
            msg = f"Entity type '{entity_type_id}' not found"
            raise ValueError(msg)

        self._validate_status_transition(
            from_status=current.review_status,
            to_status=target_status,
        )

        normalized_reason: str | None = None
        if target_status == "REVOKED":
            if revocation_reason is None or not revocation_reason.strip():
                msg = "revocation_reason is required when setting REVOKED status"
                raise ValueError(msg)
            normalized_reason = revocation_reason.strip()
        elif revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)

        return self._dictionary.set_entity_type_review_status(
            entity_type_id,
            review_status=target_status,
            reviewed_by=reviewed_by_normalized,
            revocation_reason=normalized_reason,
        )

    def revoke_entity_type(
        self,
        entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryEntityType:
        """Convenience operation for revoking an entity type."""
        return self.set_entity_type_review_status(
            entity_type_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

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
        """Create a dictionary relation type with provenance metadata."""
        created_by_normalized = self._normalize_created_by(created_by)
        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        embedding_model = self._resolve_embedding_model()
        description_embedding, embedded_at, resolved_embedding_model = (
            self._embed_description(
                description,
                model_name=embedding_model,
            )
        )
        return self._dictionary.create_relation_type(
            relation_type=relation_type,
            display_name=display_name,
            description=description,
            domain_context=domain_context,
            is_directional=is_directional,
            inverse_label=inverse_label,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=resolved_embedding_model,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def list_relation_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> list[DictionaryRelationType]:
        """List dictionary relation types."""
        return self._dictionary.find_relation_types(domain_context=domain_context)

    def get_relation_type(
        self,
        relation_type_id: str,
    ) -> DictionaryRelationType | None:
        """Get a dictionary relation type by ID."""
        return self._dictionary.get_relation_type(relation_type_id)

    def set_relation_type_review_status(
        self,
        relation_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationType:
        """Set review state for a dictionary relation type."""
        reviewed_by_normalized = reviewed_by.strip()
        if not reviewed_by_normalized:
            msg = "reviewed_by is required"
            raise ValueError(msg)

        target_status = self._normalize_review_status(review_status)
        current = self._dictionary.get_relation_type(relation_type_id)
        if current is None:
            msg = f"Relation type '{relation_type_id}' not found"
            raise ValueError(msg)

        self._validate_status_transition(
            from_status=current.review_status,
            to_status=target_status,
        )

        normalized_reason: str | None = None
        if target_status == "REVOKED":
            if revocation_reason is None or not revocation_reason.strip():
                msg = "revocation_reason is required when setting REVOKED status"
                raise ValueError(msg)
            normalized_reason = revocation_reason.strip()
        elif revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)

        return self._dictionary.set_relation_type_review_status(
            relation_type_id,
            review_status=target_status,
            reviewed_by=reviewed_by_normalized,
            revocation_reason=normalized_reason,
        )

    def revoke_relation_type(
        self,
        relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationType:
        """Convenience operation for revoking a relation type."""
        return self.set_relation_type_review_status(
            relation_type_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

    def list_changelog_entries(
        self,
        *,
        table_name: str | None = None,
        record_id: str | None = None,
        limit: int = 100,
    ) -> list[DictionaryChangelog]:
        """List dictionary changelog entries with optional filters."""
        return self._dictionary.find_changelog_entries(
            table_name=table_name,
            record_id=record_id,
            limit=limit,
        )

    # ── Transforms ────────────────────────────────────────────────────

    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
    ) -> TransformRegistry | None:
        """Find a unit transformation."""
        return self._dictionary.get_transform(input_unit, output_unit)

    def list_transforms(
        self,
        *,
        status: str = "ACTIVE",
    ) -> list[TransformRegistry]:
        """List all transforms."""
        return self._dictionary.find_transforms(status=status)


__all__ = ["DictionaryManagementService", "ReviewStatus"]
