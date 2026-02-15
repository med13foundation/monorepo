"""
SQLAlchemy implementation of DictionaryRepository.

Read-heavy repository for the Layer 1 dictionary tables:
variable_definitions, variable_synonyms, transform_registry,
entity_resolution_policies, relation_constraints, and first-class
dictionary type references.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import and_, select

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
from src.domain.repositories.kernel.dictionary_repository import DictionaryRepository
from src.infrastructure.repositories.kernel.dictionary_search import (
    search_dictionary_entries,
    search_dictionary_entries_by_domain,
)
from src.models.database.kernel.dictionary import (
    DictionaryChangelogModel,
    DictionaryDataTypeModel,
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    DictionarySensitivityLevelModel,
    EntityResolutionPolicyModel,
    RelationConstraintModel,
    TransformRegistryModel,
    ValueSetItemModel,
    ValueSetModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject, JSONValue

logger = logging.getLogger(__name__)

ReviewStatus = Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]
_DATA_TYPE_HINTS: dict[str, tuple[str, str]] = {
    "INTEGER": ("int", "Whole-number value"),
    "FLOAT": ("float", "Decimal numeric value"),
    "STRING": ("str", "Free-form text"),
    "DATE": ("datetime", "Date/time value"),
    "CODED": ("str", "Enumerated coded value"),
    "BOOLEAN": ("bool", "True/False value"),
    "JSON": ("dict", "Structured JSON payload"),
}
_SENSITIVITY_DESCRIPTIONS: dict[str, str] = {
    "PUBLIC": "Data suitable for broad sharing",
    "INTERNAL": "Internal-only research data",
    "PHI": "Sensitive regulated patient data",
}


def _to_json_value(value: object) -> JSONValue:  # noqa: PLR0911
    """Convert database values into JSON-compatible values."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, set):
        return [_to_json_value(item) for item in sorted(value, key=str)]
    return str(value)


def _snapshot_model(model: object) -> JSONObject:
    """Build a JSON-serializable snapshot of a SQLAlchemy model instance."""
    snapshot: JSONObject = {}
    for key, value in vars(model).items():
        if key.startswith("_"):
            continue
        snapshot[key] = _to_json_value(value)
    return snapshot


def _humanize(identifier: str) -> str:
    return " ".join(part.capitalize() for part in identifier.replace("_", " ").split())


def _normalize_synonyms(synonyms: list[str] | None) -> list[str]:
    if synonyms is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in synonyms:
        synonym = raw.strip()
        if not synonym:
            continue
        key = synonym.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(synonym)
    return normalized


class SqlAlchemyDictionaryRepository(DictionaryRepository):
    """SQLAlchemy implementation of the dictionary repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _record_change(  # noqa: PLR0913
        self,
        *,
        table_name: str,
        record_id: str,
        action: str,
        before_snapshot: JSONObject | None,
        after_snapshot: JSONObject | None,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> None:
        change = DictionaryChangelogModel(
            table_name=table_name,
            record_id=record_id,
            action=action,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            changed_by=changed_by,
            source_ref=source_ref,
        )
        self._session.add(change)

    def _ensure_data_type_reference(self, data_type: str) -> str:
        normalized = data_type.strip().upper()
        existing = self._session.get(DictionaryDataTypeModel, normalized)
        if existing is not None:
            return normalized

        python_type_hint, description = _DATA_TYPE_HINTS.get(
            normalized,
            ("str", "Autogenerated data type"),
        )
        self._session.add(
            DictionaryDataTypeModel(
                id=normalized,
                display_name=_humanize(normalized),
                python_type_hint=python_type_hint,
                description=description,
                constraint_schema={},
            ),
        )
        self._session.flush()
        return normalized

    def _ensure_domain_context_reference(self, domain_context: str) -> str:
        normalized = domain_context.strip() or "general"
        existing = self._session.get(DictionaryDomainContextModel, normalized)
        if existing is not None:
            return normalized

        self._session.add(
            DictionaryDomainContextModel(
                id=normalized,
                display_name=_humanize(normalized),
                description="Autogenerated domain context",
            ),
        )
        self._session.flush()
        return normalized

    def _ensure_sensitivity_reference(self, sensitivity: str) -> str:
        normalized = sensitivity.strip().upper()
        existing = self._session.get(DictionarySensitivityLevelModel, normalized)
        if existing is not None:
            return normalized

        self._session.add(
            DictionarySensitivityLevelModel(
                id=normalized,
                display_name=_humanize(normalized),
                description=_SENSITIVITY_DESCRIPTIONS.get(
                    normalized,
                    "Autogenerated sensitivity level",
                ),
            ),
        )
        self._session.flush()
        return normalized

    # ── Variable definitions ──────────────────────────────────────────

    def get_variable(self, variable_id: str) -> VariableDefinition | None:
        model = self._session.get(VariableDefinitionModel, variable_id)
        return VariableDefinition.model_validate(model) if model is not None else None

    def find_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
    ) -> list[VariableDefinition]:
        stmt = select(VariableDefinitionModel)
        if domain_context is not None:
            stmt = stmt.where(
                VariableDefinitionModel.domain_context == domain_context,
            )
        if data_type is not None:
            stmt = stmt.where(VariableDefinitionModel.data_type == data_type)
        stmt = stmt.order_by(VariableDefinitionModel.canonical_name)
        return [
            VariableDefinition.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_variable_by_synonym(
        self,
        synonym: str,
    ) -> VariableDefinition | None:
        normalized_synonym = synonym.strip().lower()
        stmt = (
            select(VariableDefinitionModel)
            .join(VariableSynonymModel)
            .where(VariableSynonymModel.synonym == normalized_synonym)
        )
        model = self._session.scalars(stmt).first()
        return VariableDefinition.model_validate(model) if model is not None else None

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
        review_status: ReviewStatus = "ACTIVE",
    ) -> VariableDefinition:
        normalized_data_type = self._ensure_data_type_reference(data_type)
        normalized_domain_context = self._ensure_domain_context_reference(
            domain_context,
        )
        normalized_sensitivity = self._ensure_sensitivity_reference(sensitivity)

        model = VariableDefinitionModel(
            id=variable_id,
            canonical_name=canonical_name,
            display_name=display_name,
            data_type=normalized_data_type,
            domain_context=normalized_domain_context,
            sensitivity=normalized_sensitivity,
            preferred_unit=preferred_unit,
            constraints=constraints or {},
            description=description,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=embedding_model,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=VariableDefinitionModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return VariableDefinition.model_validate(model)

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
        model = self._session.get(VariableDefinitionModel, variable_id)
        if model is None:
            msg = f"Variable '{variable_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.description_embedding = description_embedding
        model.embedded_at = embedded_at
        model.embedding_model = embedding_model
        self._session.flush()
        self._record_change(
            table_name=VariableDefinitionModel.__tablename__,
            record_id=model.id,
            action="UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=changed_by,
            source_ref=source_ref,
        )
        return VariableDefinition.model_validate(model)

    def create_synonym(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        synonym: str,
        source: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> VariableSynonym:
        normalized_synonym = synonym.strip().lower()
        if not normalized_synonym:
            msg = "synonym is required"
            raise ValueError(msg)

        normalized_source = source.strip() if isinstance(source, str) else source
        if normalized_source == "":
            normalized_source = None

        model = VariableSynonymModel(
            variable_id=variable_id,
            synonym=normalized_synonym,
            source=normalized_source,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=VariableSynonymModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return VariableSynonym.model_validate(model)

    def set_variable_review_status(
        self,
        variable_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> VariableDefinition:
        model = self._session.get(VariableDefinitionModel, variable_id)
        if model is None:
            msg = f"Variable '{variable_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.review_status = review_status
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(UTC)
        model.revocation_reason = (
            revocation_reason if review_status == "REVOKED" else None
        )
        self._session.flush()
        self._record_change(
            table_name=VariableDefinitionModel.__tablename__,
            record_id=model.id,
            action="REVOKE" if review_status == "REVOKED" else "UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return VariableDefinition.model_validate(model)

    def revoke_variable(
        self,
        variable_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> VariableDefinition:
        return self.set_variable_review_status(
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
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> ValueSet:
        normalized_value_set_id = value_set_id.strip()
        if not normalized_value_set_id:
            msg = "value_set_id is required"
            raise ValueError(msg)
        normalized_variable_id = variable_id.strip()
        if not normalized_variable_id:
            msg = "variable_id is required"
            raise ValueError(msg)
        normalized_name = name.strip()
        if not normalized_name:
            msg = "name is required"
            raise ValueError(msg)

        model = ValueSetModel(
            id=normalized_value_set_id,
            variable_id=normalized_variable_id,
            variable_data_type="CODED",
            name=normalized_name,
            description=description,
            external_ref=external_ref,
            is_extensible=is_extensible,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=ValueSetModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return ValueSet.model_validate(model)

    def get_value_set(self, value_set_id: str) -> ValueSet | None:
        normalized_value_set_id = value_set_id.strip()
        if not normalized_value_set_id:
            return None
        model = self._session.get(ValueSetModel, normalized_value_set_id)
        return ValueSet.model_validate(model) if model is not None else None

    def find_value_sets(
        self,
        *,
        variable_id: str | None = None,
    ) -> list[ValueSet]:
        stmt = select(ValueSetModel)
        if variable_id is not None:
            stmt = stmt.where(ValueSetModel.variable_id == variable_id)
        stmt = stmt.order_by(ValueSetModel.id)
        models = self._session.scalars(stmt).all()
        return [ValueSet.model_validate(model) for model in models]

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
        review_status: ReviewStatus = "ACTIVE",
    ) -> ValueSetItem:
        normalized_value_set_id = value_set_id.strip()
        if not normalized_value_set_id:
            msg = "value_set_id is required"
            raise ValueError(msg)
        normalized_code = code.strip()
        if not normalized_code:
            msg = "code is required"
            raise ValueError(msg)
        normalized_label = display_label.strip()
        if not normalized_label:
            msg = "display_label is required"
            raise ValueError(msg)

        model = ValueSetItemModel(
            value_set_id=normalized_value_set_id,
            code=normalized_code,
            display_label=normalized_label,
            synonyms=_normalize_synonyms(synonyms),
            external_ref=external_ref,
            sort_order=sort_order,
            is_active=is_active,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=ValueSetItemModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return ValueSetItem.model_validate(model)

    def find_value_set_items(
        self,
        *,
        value_set_id: str,
        include_inactive: bool = False,
    ) -> list[ValueSetItem]:
        stmt = select(ValueSetItemModel).where(
            ValueSetItemModel.value_set_id == value_set_id,
        )
        if not include_inactive:
            stmt = stmt.where(ValueSetItemModel.is_active.is_(True))
        stmt = stmt.order_by(ValueSetItemModel.sort_order, ValueSetItemModel.id)
        models = self._session.scalars(stmt).all()
        return [ValueSetItem.model_validate(model) for model in models]

    def set_value_set_item_active(
        self,
        value_set_item_id: int,
        *,
        is_active: bool,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> ValueSetItem:
        model = self._session.get(ValueSetItemModel, value_set_item_id)
        if model is None:
            msg = f"Value set item '{value_set_item_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.is_active = is_active
        model.review_status = "ACTIVE" if is_active else "REVOKED"
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(UTC)
        model.revocation_reason = revocation_reason if not is_active else None
        self._session.flush()
        self._record_change(
            table_name=ValueSetItemModel.__tablename__,
            record_id=str(model.id),
            action="UPDATE" if is_active else "REVOKE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return ValueSetItem.model_validate(model)

    # ── Entity resolution policies ────────────────────────────────────

    def get_resolution_policy(
        self,
        entity_type: str,
    ) -> EntityResolutionPolicy | None:
        model = self._session.get(EntityResolutionPolicyModel, entity_type)
        return (
            EntityResolutionPolicy.model_validate(model) if model is not None else None
        )

    def find_resolution_policies(self) -> list[EntityResolutionPolicy]:
        models = self._session.scalars(
            select(EntityResolutionPolicyModel).order_by(
                EntityResolutionPolicyModel.entity_type,
            ),
        ).all()
        return [EntityResolutionPolicy.model_validate(model) for model in models]

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
        review_status: ReviewStatus = "ACTIVE",
    ) -> DictionaryEntityType:
        normalized_entity_type = entity_type.strip().upper()
        normalized_domain_context = self._ensure_domain_context_reference(
            domain_context,
        )

        model = DictionaryEntityTypeModel(
            id=normalized_entity_type,
            display_name=display_name,
            description=description,
            domain_context=normalized_domain_context,
            external_ontology_ref=external_ontology_ref,
            expected_properties=expected_properties or {},
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=embedding_model,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=DictionaryEntityTypeModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return DictionaryEntityType.model_validate(model)

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
        normalized_entity_type = entity_type_id.strip().upper()
        model = self._session.get(DictionaryEntityTypeModel, normalized_entity_type)
        if model is None:
            msg = f"Entity type '{entity_type_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.description_embedding = description_embedding
        model.embedded_at = embedded_at
        model.embedding_model = embedding_model
        self._session.flush()
        self._record_change(
            table_name=DictionaryEntityTypeModel.__tablename__,
            record_id=model.id,
            action="UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=changed_by,
            source_ref=source_ref,
        )
        return DictionaryEntityType.model_validate(model)

    def find_entity_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> list[DictionaryEntityType]:
        stmt = select(DictionaryEntityTypeModel)
        if domain_context is not None:
            stmt = stmt.where(
                DictionaryEntityTypeModel.domain_context == domain_context,
            )
        stmt = stmt.order_by(DictionaryEntityTypeModel.id)
        models = self._session.scalars(stmt).all()
        return [DictionaryEntityType.model_validate(model) for model in models]

    def get_entity_type(self, entity_type_id: str) -> DictionaryEntityType | None:
        normalized_entity_type = entity_type_id.strip().upper()
        model = self._session.get(DictionaryEntityTypeModel, normalized_entity_type)
        return DictionaryEntityType.model_validate(model) if model is not None else None

    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> DictionaryEntityType:
        normalized_entity_type = entity_type_id.strip().upper()
        model = self._session.get(DictionaryEntityTypeModel, normalized_entity_type)
        if model is None:
            msg = f"Entity type '{entity_type_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.review_status = review_status
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(UTC)
        model.revocation_reason = (
            revocation_reason if review_status == "REVOKED" else None
        )
        self._session.flush()
        self._record_change(
            table_name=DictionaryEntityTypeModel.__tablename__,
            record_id=model.id,
            action="REVOKE" if review_status == "REVOKED" else "UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return DictionaryEntityType.model_validate(model)

    def revoke_entity_type(
        self,
        entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryEntityType:
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
        description_embedding: list[float] | None = None,
        embedded_at: datetime | None = None,
        embedding_model: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> DictionaryRelationType:
        normalized_relation_type = relation_type.strip().upper()
        normalized_domain_context = self._ensure_domain_context_reference(
            domain_context,
        )

        model = DictionaryRelationTypeModel(
            id=normalized_relation_type,
            display_name=display_name,
            description=description,
            domain_context=normalized_domain_context,
            is_directional=is_directional,
            inverse_label=inverse_label,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=embedding_model,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=DictionaryRelationTypeModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return DictionaryRelationType.model_validate(model)

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
        normalized_relation_type = relation_type_id.strip().upper()
        model = self._session.get(DictionaryRelationTypeModel, normalized_relation_type)
        if model is None:
            msg = f"Relation type '{relation_type_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.description_embedding = description_embedding
        model.embedded_at = embedded_at
        model.embedding_model = embedding_model
        self._session.flush()
        self._record_change(
            table_name=DictionaryRelationTypeModel.__tablename__,
            record_id=model.id,
            action="UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=changed_by,
            source_ref=source_ref,
        )
        return DictionaryRelationType.model_validate(model)

    def find_relation_types(
        self,
        *,
        domain_context: str | None = None,
    ) -> list[DictionaryRelationType]:
        stmt = select(DictionaryRelationTypeModel)
        if domain_context is not None:
            stmt = stmt.where(
                DictionaryRelationTypeModel.domain_context == domain_context,
            )
        stmt = stmt.order_by(DictionaryRelationTypeModel.id)
        models = self._session.scalars(stmt).all()
        return [DictionaryRelationType.model_validate(model) for model in models]

    def get_relation_type(
        self,
        relation_type_id: str,
    ) -> DictionaryRelationType | None:
        normalized_relation_type = relation_type_id.strip().upper()
        model = self._session.get(DictionaryRelationTypeModel, normalized_relation_type)
        return (
            DictionaryRelationType.model_validate(model) if model is not None else None
        )

    def set_relation_type_review_status(
        self,
        relation_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationType:
        normalized_relation_type = relation_type_id.strip().upper()
        model = self._session.get(DictionaryRelationTypeModel, normalized_relation_type)
        if model is None:
            msg = f"Relation type '{relation_type_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.review_status = review_status
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(UTC)
        model.revocation_reason = (
            revocation_reason if review_status == "REVOKED" else None
        )
        self._session.flush()
        self._record_change(
            table_name=DictionaryRelationTypeModel.__tablename__,
            record_id=model.id,
            action="REVOKE" if review_status == "REVOKED" else "UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return DictionaryRelationType.model_validate(model)

    def revoke_relation_type(
        self,
        relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryRelationType:
        return self.set_relation_type_review_status(
            relation_type_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

    def find_changelog_entries(
        self,
        *,
        table_name: str | None = None,
        record_id: str | None = None,
        limit: int = 100,
    ) -> list[DictionaryChangelog]:
        normalized_limit = max(1, min(limit, 500))
        stmt = select(DictionaryChangelogModel)
        if table_name is not None:
            stmt = stmt.where(DictionaryChangelogModel.table_name == table_name)
        if record_id is not None:
            stmt = stmt.where(DictionaryChangelogModel.record_id == record_id)
        stmt = stmt.order_by(DictionaryChangelogModel.id.desc()).limit(normalized_limit)
        models = self._session.scalars(stmt).all()
        return [DictionaryChangelog.model_validate(model) for model in models]

    def search_dictionary(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        query_embeddings: dict[str, list[float]] | None = None,
    ) -> list[DictionarySearchResult]:
        return search_dictionary_entries(
            self._session,
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=query_embeddings,
        )

    def search_dictionary_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 50,
    ) -> list[DictionarySearchResult]:
        return search_dictionary_entries_by_domain(
            self._session,
            domain_context=domain_context,
            limit=limit,
        )

    # ── Relation constraints ──────────────────────────────────────────

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
    ) -> list[RelationConstraint]:
        stmt = select(RelationConstraintModel)
        if source_type is not None:
            stmt = stmt.where(RelationConstraintModel.source_type == source_type)
        if relation_type is not None:
            stmt = stmt.where(RelationConstraintModel.relation_type == relation_type)
        return [
            RelationConstraint.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def is_triple_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        stmt = select(RelationConstraintModel).where(
            and_(
                RelationConstraintModel.source_type == source_type,
                RelationConstraintModel.relation_type == relation_type,
                RelationConstraintModel.target_type == target_type,
                RelationConstraintModel.is_allowed.is_(True),
                RelationConstraintModel.review_status == "ACTIVE",
            ),
        )
        return self._session.scalars(stmt).first() is not None

    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        stmt = select(RelationConstraintModel).where(
            and_(
                RelationConstraintModel.source_type == source_type,
                RelationConstraintModel.relation_type == relation_type,
                RelationConstraintModel.target_type == target_type,
                RelationConstraintModel.review_status == "ACTIVE",
            ),
        )
        constraint = self._session.scalars(stmt).first()
        if constraint is None:
            # If no constraint exists, default to requiring evidence
            return True
        return constraint.requires_evidence

    # ── Transform registry ────────────────────────────────────────────

    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
    ) -> TransformRegistry | None:
        stmt = select(TransformRegistryModel).where(
            and_(
                TransformRegistryModel.input_unit == input_unit,
                TransformRegistryModel.output_unit == output_unit,
                TransformRegistryModel.status == "ACTIVE",
            ),
        )
        model = self._session.scalars(stmt).first()
        return TransformRegistry.model_validate(model) if model is not None else None

    def find_transforms(
        self,
        *,
        status: str = "ACTIVE",
    ) -> list[TransformRegistry]:
        stmt = select(TransformRegistryModel).where(
            TransformRegistryModel.status == status,
        )
        return [
            TransformRegistry.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]


__all__ = ["SqlAlchemyDictionaryRepository"]
