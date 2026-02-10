"""
Entity resolver engine for the ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.infrastructure.ingestion.resolution.strategies import (
    FuzzyStrategy,
    LookupStrategy,
    ResolutionStrategy,
    StrictMatchStrategy,
)
from src.infrastructure.ingestion.types import ResolvedEntity

if TYPE_CHECKING:
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )
    from src.domain.repositories.kernel.entity_repository import KernelEntityRepository
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Resolves entity anchors to kernel entities using configured policies.
    """

    def __init__(
        self,
        dictionary_repository: DictionaryRepository,
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

    def resolve(
        self,
        anchor: JSONObject,
        entity_type: str,
        research_space_id: str,
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

        policy = self.dict_repo.get_resolution_policy(entity_type)
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
            logger.warning(
                "Missing required anchors %s for %s; skipping resolution",
                missing_required,
                entity_type,
            )
        else:
            existing_entity = strategy.resolve(anchor, entity_type, research_space_id)

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
        display_label = self._derive_label(anchor, entity_type)

        new_entity = self.entity_repo.create(
            research_space_id=research_space_id,
            entity_type=entity_type,
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
