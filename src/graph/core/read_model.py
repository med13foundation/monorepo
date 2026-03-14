"""Graph-core read-model contracts and ownership rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class GraphReadModelOwner(StrEnum):
    """Ownership scope for one read-model definition."""

    GRAPH_CORE = "graph_core"
    DOMAIN_PACK = "domain_pack"


class GraphReadModelAuthoritativeSource(StrEnum):
    """Authoritative stores from which read models may be derived."""

    CLAIM_LEDGER = "claim_ledger"
    CANONICAL_GRAPH = "canonical_graph"
    PROJECTION_LINEAGE = "projection_lineage"


class GraphReadModelTrigger(StrEnum):
    """Events that can refresh one read model."""

    CLAIM_CHANGE = "claim_change"
    PROJECTION_CHANGE = "projection_change"
    FULL_REBUILD = "full_rebuild"


@dataclass(frozen=True)
class GraphReadModelDefinition:
    """One graph query read model owned by graph-core or a domain pack."""

    name: str
    description: str
    owner: GraphReadModelOwner
    authoritative_sources: tuple[GraphReadModelAuthoritativeSource, ...]
    triggers: tuple[GraphReadModelTrigger, ...]
    is_truth_source: bool = False

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            msg = "Read-model name is required"
            raise ValueError(msg)
        if normalized_name != self.name:
            msg = "Read-model names must already be normalized"
            raise ValueError(msg)
        if not self.authoritative_sources:
            msg = f"Read model '{self.name}' must declare authoritative sources"
            raise ValueError(msg)
        if GraphReadModelTrigger.FULL_REBUILD not in self.triggers:
            msg = f"Read model '{self.name}' must support full rebuild"
            raise ValueError(msg)
        if self.is_truth_source:
            msg = f"Read model '{self.name}' cannot be marked as a truth source"
            raise ValueError(msg)

    @property
    def supports_incremental_updates(self) -> bool:
        """Return whether the read model can be refreshed incrementally."""
        return any(
            trigger in self.triggers
            for trigger in (
                GraphReadModelTrigger.CLAIM_CHANGE,
                GraphReadModelTrigger.PROJECTION_CHANGE,
            )
        )


@dataclass(frozen=True)
class GraphReadModelUpdate:
    """One incremental or rebuild update request for a read model."""

    model_name: str
    trigger: GraphReadModelTrigger
    claim_ids: tuple[str, ...] = ()
    relation_ids: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()
    space_id: str | None = None


@runtime_checkable
class GraphReadModelProjector(Protocol):
    """Runtime contract for one rebuildable graph read-model projector."""

    @property
    def definition(self) -> GraphReadModelDefinition:
        """Return the read-model definition owned by this projector."""

    def rebuild(self, *, space_id: str | None = None) -> int:
        """Rebuild the whole read model and return the affected row count."""

    def apply_update(self, update: GraphReadModelUpdate) -> int:
        """Apply one incremental update and return the affected row count."""


@runtime_checkable
class GraphReadModelUpdateDispatcher(Protocol):
    """Runtime contract for dispatching read-model refresh intents."""

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        """Dispatch one read-model update and return the affected row count."""

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        """Dispatch multiple updates and return the total affected row count."""


@dataclass
class NullGraphReadModelUpdateDispatcher:
    """No-op dispatcher used until physical read models are implemented."""

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        del update
        return 0

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        del updates
        return 0


@dataclass
class ProjectorBackedGraphReadModelUpdateDispatcher:
    """Dispatcher that routes updates to registered read-model projectors."""

    projectors: dict[str, GraphReadModelProjector]

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        projector = self.projectors.get(update.model_name)
        if projector is None:
            return 0
        if update.trigger == GraphReadModelTrigger.FULL_REBUILD:
            return projector.rebuild(space_id=update.space_id)
        return projector.apply_update(update)

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        return sum(self.dispatch(update) for update in updates)


@dataclass
class GraphReadModelRegistry:
    """Registry of graph read models owned by one runtime."""

    _definitions: dict[str, GraphReadModelDefinition] = field(default_factory=dict)

    def register(self, definition: GraphReadModelDefinition) -> None:
        """Register one read-model definition, rejecting duplicates."""
        if definition.name in self._definitions:
            msg = f"Read model '{definition.name}' is already registered"
            raise ValueError(msg)
        self._definitions[definition.name] = definition

    def get(self, name: str) -> GraphReadModelDefinition | None:
        """Return one read-model definition by name."""
        return self._definitions.get(name)

    def list(
        self,
        *,
        owner: GraphReadModelOwner | None = None,
    ) -> tuple[GraphReadModelDefinition, ...]:
        """List registered definitions, optionally filtered by owner."""
        definitions = tuple(self._definitions.values())
        if owner is None:
            return definitions
        return tuple(
            definition for definition in definitions if definition.owner == owner
        )


ENTITY_NEIGHBORS_READ_MODEL = GraphReadModelDefinition(
    name="entity_neighbors",
    description="Fast neighborhood reads derived from canonical relations and lineage.",
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CANONICAL_GRAPH,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

ENTITY_RELATION_SUMMARY_READ_MODEL = GraphReadModelDefinition(
    name="entity_relation_summary",
    description="Per-entity relation counts and summary metrics for graph browsing.",
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CANONICAL_GRAPH,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

ENTITY_CLAIM_SUMMARY_READ_MODEL = GraphReadModelDefinition(
    name="entity_claim_summary",
    description="Per-entity claim-backed summary metrics for evidence-oriented reads.",
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CLAIM_LEDGER,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.CLAIM_CHANGE,
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

ENTITY_MECHANISM_PATHS_READ_MODEL = GraphReadModelDefinition(
    name="entity_mechanism_paths",
    description=(
        "Per-seed mechanism-path candidates derived from grounded reasoning paths "
        "for hypothesis and mechanism-oriented reads."
    ),
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CLAIM_LEDGER,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.CLAIM_CHANGE,
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

CORE_GRAPH_READ_MODELS = (
    ENTITY_NEIGHBORS_READ_MODEL,
    ENTITY_RELATION_SUMMARY_READ_MODEL,
    ENTITY_CLAIM_SUMMARY_READ_MODEL,
    ENTITY_MECHANISM_PATHS_READ_MODEL,
)


def build_core_graph_read_model_registry() -> GraphReadModelRegistry:
    """Build the baseline graph-core read-model registry."""
    registry = GraphReadModelRegistry()
    for definition in CORE_GRAPH_READ_MODELS:
        registry.register(definition)
    return registry


__all__ = [
    "CORE_GRAPH_READ_MODELS",
    "ENTITY_CLAIM_SUMMARY_READ_MODEL",
    "ENTITY_MECHANISM_PATHS_READ_MODEL",
    "ENTITY_NEIGHBORS_READ_MODEL",
    "ENTITY_RELATION_SUMMARY_READ_MODEL",
    "GraphReadModelAuthoritativeSource",
    "GraphReadModelDefinition",
    "GraphReadModelOwner",
    "GraphReadModelProjector",
    "GraphReadModelRegistry",
    "GraphReadModelTrigger",
    "GraphReadModelUpdateDispatcher",
    "GraphReadModelUpdate",
    "NullGraphReadModelUpdateDispatcher",
    "ProjectorBackedGraphReadModelUpdateDispatcher",
    "build_core_graph_read_model_registry",
]
