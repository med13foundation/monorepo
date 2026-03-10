"""
Entity resolver engine for the ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, TypeGuard

from src.domain.services.ingestion import IngestionProgressUpdate
from src.infrastructure.ingestion.resolution.strategies import (
    FuzzyStrategy,
    LookupStrategy,
    ResolutionStrategy,
    StrictMatchStrategy,
)
from src.infrastructure.ingestion.types import ResolvedEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.entities.kernel.dictionary import EntityResolutionPolicy
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.domain.services.ingestion import IngestionProgressCallback
    from src.type_definitions.common import JSONObject


class _ResolutionPolicyEnsurer(Protocol):
    def ensure_resolution_policy_for_entity_type(
        self,
        *,
        entity_type: str,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: object | None = None,
    ) -> EntityResolutionPolicy | None: ...


def _is_resolution_policy(value: object) -> TypeGuard[EntityResolutionPolicy]:
    return hasattr(value, "policy_strategy") and hasattr(value, "required_anchors")


def _get_resolution_policy_ensurer(
    repository: object,
) -> _ResolutionPolicyEnsurer | None:
    ensure_policy = getattr(
        repository,
        "ensure_resolution_policy_for_entity_type",
        None,
    )
    if not callable(ensure_policy):
        return None
    ensure_policy_fn: Callable[..., object] = ensure_policy

    class _RepositoryResolutionPolicyEnsurer:
        def ensure_resolution_policy_for_entity_type(
            self,
            *,
            entity_type: str,
            created_by: str,
            source_ref: str | None = None,
            research_space_settings: object | None = None,
        ) -> EntityResolutionPolicy | None:
            result = ensure_policy_fn(
                entity_type=entity_type,
                created_by=created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            if result is None or _is_resolution_policy(result):
                return result
            return None

    return _RepositoryResolutionPolicyEnsurer()


logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Resolves entity anchors to kernel entities using configured policies.
    """

    def __init__(
        self,
        dictionary_repository: DictionaryPort,
        entity_repository: KernelEntityRepository,
    ) -> None:
        self.dict_repo = dictionary_repository
        self.entity_repo = entity_repository

        # Initialize strategies
        self.strategies: dict[str, ResolutionStrategy] = {
            "STRICT_MATCH": StrictMatchStrategy(entity_repository),
            "LOOKUP": LookupStrategy(entity_repository),
            "FUZZY": FuzzyStrategy(entity_repository),
            "NONE": StrictMatchStrategy(entity_repository),  # Default/Fallback
        }

    @staticmethod
    def _normalize_entity_type(entity_type: str) -> str:
        normalized = entity_type.strip().upper()
        return normalized.replace("-", "_").replace("/", "_").replace(" ", "_")

    def _ensure_resolution_policy(
        self,
        *,
        entity_type: str,
        source_record_id: str | None,
    ) -> EntityResolutionPolicy | None:
        resolution_policy_ensurer = _get_resolution_policy_ensurer(self.dict_repo)
        if resolution_policy_ensurer is None:
            return None
        source_ref = (
            f"source_record:{source_record_id.strip()}"
            if isinstance(source_record_id, str) and source_record_id.strip()
            else None
        )
        try:
            return resolution_policy_ensurer.ensure_resolution_policy_for_entity_type(
                entity_type=entity_type,
                created_by="system:entity_resolver",
                source_ref=source_ref,
                research_space_settings=None,
            )
        except Exception:  # noqa: BLE001 - resolver must degrade to warning path
            logger.exception(
                "Failed to auto-provision resolution policy for entity_type=%s",
                entity_type,
            )
            return None

    def _resolve_policy_for_entity_type(
        self,
        *,
        entity_type: str,
        anchor: JSONObject,
        source_record_id: str | None,
        progress_callback: IngestionProgressCallback | None,
    ) -> EntityResolutionPolicy | None:
        policy = self.dict_repo.get_resolution_policy(entity_type)
        if policy is not None:
            return policy
        ensured_policy = self._ensure_resolution_policy(
            entity_type=entity_type,
            source_record_id=source_record_id,
        )
        if ensured_policy is not None:
            return ensured_policy
        self._emit_missing_policy_warning(
            entity_type=entity_type,
            anchor=anchor,
            source_record_id=source_record_id,
            progress_callback=progress_callback,
        )
        return None

    def _activate_entity_type(
        self,
        *,
        entity_type_id: str,
    ) -> str:
        try:
            activated_entity_type = self.dict_repo.set_entity_type_review_status(
                entity_type_id,
                review_status="ACTIVE",
                reviewed_by="system:entity_resolver",
            )
        except ValueError:
            logger.exception(
                "Failed to activate dictionary entity type=%s",
                entity_type_id,
            )
            return entity_type_id
        return activated_entity_type.id

    def _ensure_active_entity_type(
        self,
        *,
        entity_type: str,
        source_record_id: str | None,
    ) -> str:
        normalized_entity_type = self._normalize_entity_type(entity_type)
        existing_entity_type = self.dict_repo.get_entity_type(
            normalized_entity_type,
            include_inactive=True,
        )
        if existing_entity_type is not None:
            if (
                existing_entity_type.is_active
                and existing_entity_type.review_status == "ACTIVE"
            ):
                return existing_entity_type.id
            return self._activate_entity_type(entity_type_id=existing_entity_type.id)

        source_ref = (
            f"source_record:{source_record_id.strip()}"
            if isinstance(source_record_id, str) and source_record_id.strip()
            else None
        )
        try:
            created_entity_type = self.dict_repo.create_entity_type(
                entity_type=normalized_entity_type,
                display_name=normalized_entity_type.replace("_", " ").title(),
                description=(
                    "Auto-created dictionary entity type for resolver-backed "
                    "kernel persistence."
                ),
                domain_context="general",
                created_by="system:entity_resolver",
                source_ref=source_ref,
                research_space_settings={
                    "dictionary_agent_creation_policy": "ACTIVE",
                },
            )
        except ValueError:
            logger.exception(
                "Failed to bootstrap dictionary entity type=%s",
                normalized_entity_type,
            )
            return normalized_entity_type

        if (
            created_entity_type.is_active
            and created_entity_type.review_status == "ACTIVE"
        ):
            return created_entity_type.id
        return self._activate_entity_type(entity_type_id=created_entity_type.id)

    @staticmethod
    def _emit_missing_policy_warning(
        *,
        entity_type: str,
        anchor: JSONObject,
        source_record_id: str | None,
        progress_callback: IngestionProgressCallback | None,
    ) -> None:
        warning_message = (
            "No resolution policy configured for "
            f"entity_type={entity_type}; falling back to "
            "STRICT_MATCH with best-effort anchors."
        )
        logger.warning(warning_message)
        if progress_callback is None:
            return

        warning_payload: JSONObject = {
            "entity_type": entity_type,
            "fallback_strategy": "STRICT_MATCH",
            "reason": "missing_resolution_policy",
            "anchor_keys": sorted(anchor.keys()),
        }
        if isinstance(source_record_id, str) and source_record_id.strip():
            warning_payload["source_record_id"] = source_record_id.strip()
        progress_callback(
            IngestionProgressUpdate(
                event_type="resolver_warning",
                message=warning_message,
                payload=warning_payload,
            ),
        )

    def resolve(
        self,
        anchor: JSONObject,
        entity_type: str,
        research_space_id: str,
        *,
        source_record_id: str | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> ResolvedEntity:
        """
        Resolve an entity anchor to a kernel entity.
        If resolution fails or no entity exists, creates a new one (if policy allows)
        or returns a provisional entity structure.

        NOTE: This implementation currently only TRYES to resolve.
        It does NOT create new entities yet. The creation logic might belong here
        or in the service layer using the resolver.
        For the pipeline, we need a ResolvedEntity ID to link observations.

        If not found, we effectively create a "new" entity ID to be persisted.
        """

        normalized_entity_type = self._ensure_active_entity_type(
            entity_type=entity_type,
            source_record_id=source_record_id,
        )
        policy = self._resolve_policy_for_entity_type(
            entity_type=normalized_entity_type,
            anchor=anchor,
            source_record_id=source_record_id,
            progress_callback=progress_callback,
        )
        strategy_name = "STRICT_MATCH"
        if policy:
            strategy_name = policy.policy_strategy

        strategy = self.strategies.get(strategy_name, self.strategies["STRICT_MATCH"])

        required_anchors: list[str] = (
            policy.required_anchors
            if policy and isinstance(policy.required_anchors, list)
            else []
        )
        missing_required = []
        for anchor_key in required_anchors:
            if anchor_key not in anchor:
                missing_required.append(anchor_key)
                continue
            value = anchor[anchor_key]
            if value is None:
                missing_required.append(anchor_key)
                continue
            if isinstance(value, str) and not value.strip():
                missing_required.append(anchor_key)

        existing_entity = None
        if missing_required:
            logger.info(
                "Missing required anchors %s for %s; using create-new fallback.",
                missing_required,
                normalized_entity_type,
            )
        else:
            existing_entity = strategy.resolve(
                anchor,
                normalized_entity_type,
                research_space_id,
            )

        if existing_entity:
            return ResolvedEntity(
                id=str(existing_entity.id),
                entity_type=existing_entity.entity_type,
                display_label=existing_entity.display_label or "Unknown",
                created=False,
            )

        # If not found, we generate a new ID and basic info
        # The pipeline will likely need to persist this new entity.
        # For now, we return a ResolvedEntity with a special flag or just new UUID?
        # The ResolvedEntity dataclass expects an ID.
        # If we return a new UUID here, the caller needs to know it's new to save it.
        # This interaction implies the Resolver might need to CREATE the entity if strictly necessary
        # or we update ResolvedEntity to indicate "is_new".

        # Taking a pragmatic approach: The resolution engine ensures we have an ID.
        # If it doesn't exist, we create it in the database immediately?
        # Or we return a "Draft" entity.

        # Let's create it immediately for simplicity in this pipeline context,
        # or delegated to a service.
        # Given this is "Infrastructure", calling Repo.create is fine.

        # Construct display label from anchor if possible
        display_label = self._derive_label(anchor, normalized_entity_type)

        new_entity = self.entity_repo.create(
            research_space_id=research_space_id,
            entity_type=normalized_entity_type,
            display_label=display_label,
            metadata=anchor,
        )

        # We should also add the identifiers from the anchor so it can be resolved next time
        for k, v in anchor.items():
            # Heuristic: verify if key look likes a namespace
            # For now add all anchor keys as identifiers
            self.entity_repo.add_identifier(
                entity_id=str(new_entity.id),
                namespace=k,
                identifier_value=str(v),
            )

        return ResolvedEntity(
            id=str(new_entity.id),
            entity_type=new_entity.entity_type,
            display_label=new_entity.display_label or "New Entity",
            created=True,
        )

    def _derive_label(self, anchor: JSONObject, entity_type: str) -> str:
        # heuristics for label
        for key in ["name", "symbol", "title", "label", "id"]:
            if key in anchor:
                return str(anchor[key])
        # Fallback
        return f"{entity_type} {list(anchor.values())[0] if anchor else 'Unknown'}"
