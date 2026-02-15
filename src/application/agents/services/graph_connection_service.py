"""Application service for graph-connection agent orchestration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from src.application.agents.services.governance_service import (
    GovernanceDecision,
    GovernanceService,
)
from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.agents.contracts.graph_connection import GraphConnectionContract
    from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )
    from src.type_definitions.common import ResearchSpaceSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphConnectionServiceDependencies:
    """Dependencies required by graph-connection orchestration."""

    graph_connection_agent: GraphConnectionPort
    relation_repository: KernelRelationRepository
    governance_service: GovernanceService | None = None
    research_space_repository: ResearchSpaceRepository | None = None
    review_queue_submitter: Callable[[str, str, str | None, str], None] | None = None


@dataclass(frozen=True)
class GraphConnectionOutcome:
    """Outcome of one graph-connection discovery run."""

    seed_entity_id: str
    research_space_id: str
    status: Literal["discovered", "failed"]
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_graph: bool
    run_id: str | None = None
    proposed_relations_count: int = 0
    persisted_relations_count: int = 0
    rejected_candidates_count: int = 0
    errors: tuple[str, ...] = ()


class GraphConnectionService:
    """Coordinate Graph Connection Agent -> Governance -> relation upsert."""

    def __init__(self, dependencies: GraphConnectionServiceDependencies) -> None:
        self._agent = dependencies.graph_connection_agent
        self._relations = dependencies.relation_repository
        self._governance = dependencies.governance_service or GovernanceService()
        self._research_spaces = dependencies.research_space_repository
        self._review_queue_submitter = dependencies.review_queue_submitter

    async def discover_connections_for_seed(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        source_type: str = "clinvar",
        research_space_settings: ResearchSpaceSettings | None = None,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
    ) -> GraphConnectionOutcome:
        """Run one graph-connection discovery pass for a seed entity."""
        resolved_settings = self._resolve_research_space_settings(
            research_space_id=research_space_id,
            provided_settings=research_space_settings,
        )
        requested_shadow_mode = shadow_mode if isinstance(shadow_mode, bool) else False
        context = GraphConnectionContext(
            seed_entity_id=seed_entity_id,
            source_type=source_type,
            research_space_id=research_space_id,
            research_space_settings=resolved_settings or {},
            relation_types=relation_types,
            max_depth=max_depth,
            shadow_mode=requested_shadow_mode,
        )
        contract = await self._agent.discover(context, model_id=model_id)
        run_id = self._resolve_run_id(contract)
        governance = self._governance.evaluate(
            confidence_score=contract.confidence_score,
            evidence_count=len(contract.evidence),
            decision=contract.decision,
            requested_shadow_mode=requested_shadow_mode,
            research_space_settings=resolved_settings,
            relation_types=self._resolve_relation_types(contract),
        )
        if governance.requires_review:
            self._submit_review_item(
                research_space_id=contract.research_space_id,
                seed_entity_id=contract.seed_entity_id,
                reason=governance.reason,
            )

        if governance.shadow_mode:
            return self._build_outcome(
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_graph=False,
                reason="shadow_mode_enabled",
            )

        if not governance.allow_write:
            return self._build_outcome(
                contract=contract,
                governance=governance,
                run_id=run_id,
                wrote_to_graph=False,
                reason=governance.reason,
                errors=(governance.reason,),
            )

        persisted_count = 0
        persistence_errors: list[str] = []
        for relation in contract.proposed_relations:
            try:
                self._relations.create(
                    research_space_id=research_space_id,
                    source_id=relation.source_id,
                    relation_type=relation.relation_type,
                    target_id=relation.target_id,
                    confidence=relation.confidence,
                    evidence_summary=relation.evidence_summary,
                    evidence_tier=relation.evidence_tier,
                    provenance_id=(
                        relation.supporting_provenance_ids[0]
                        if relation.supporting_provenance_ids
                        else None
                    ),
                    agent_run_id=run_id,
                )
                persisted_count += 1
                logger.info(
                    "Graph relation persisted from connection discovery",
                    extra={
                        "research_space_id": research_space_id,
                        "seed_entity_id": seed_entity_id,
                        "pipeline_run_id": pipeline_run_id,
                        "graph_connection_run_id": run_id,
                        "relation_type": relation.relation_type,
                        "relation_source_id": relation.source_id,
                        "relation_target_id": relation.target_id,
                    },
                )
            except (TypeError, ValueError) as exc:
                persistence_errors.append(str(exc))
                logger.warning(
                    "Graph relation persistence failed",
                    extra={
                        "research_space_id": research_space_id,
                        "seed_entity_id": seed_entity_id,
                        "pipeline_run_id": pipeline_run_id,
                        "graph_connection_run_id": run_id,
                        "relation_type": relation.relation_type,
                        "relation_source_id": relation.source_id,
                        "relation_target_id": relation.target_id,
                        "error": str(exc),
                    },
                )

        wrote_to_graph = persisted_count > 0
        reason = "processed" if wrote_to_graph else "no_relations_persisted"
        if persistence_errors and not wrote_to_graph:
            reason = "relation_persistence_failed"

        return self._build_outcome(
            contract=contract,
            governance=governance,
            run_id=run_id,
            wrote_to_graph=wrote_to_graph,
            reason=reason,
            persisted_relations_count=persisted_count,
            errors=tuple(persistence_errors),
        )

    async def close(self) -> None:
        """Release resources held by the underlying graph-connection adapter."""
        await self._agent.close()

    def _resolve_research_space_settings(
        self,
        *,
        research_space_id: str,
        provided_settings: ResearchSpaceSettings | None,
    ) -> ResearchSpaceSettings | None:
        if provided_settings is not None:
            return provided_settings
        if self._research_spaces is None:
            return None
        try:
            space_uuid = UUID(research_space_id)
        except ValueError:
            return None
        space = self._research_spaces.find_by_id(space_uuid)
        if space is None:
            return None
        return self._normalize_research_space_settings(space.settings)

    @staticmethod
    def _normalize_research_space_settings(  # noqa: C901
        raw_settings: Mapping[str, object],
    ) -> ResearchSpaceSettings:
        settings: ResearchSpaceSettings = {}

        auto_approve = raw_settings.get("auto_approve")
        if isinstance(auto_approve, bool):
            settings["auto_approve"] = auto_approve

        require_review = raw_settings.get("require_review")
        if isinstance(require_review, bool):
            settings["require_review"] = require_review

        review_threshold = raw_settings.get("review_threshold")
        if isinstance(review_threshold, float | int):
            settings["review_threshold"] = max(0.0, min(float(review_threshold), 1.0))

        relation_default_review_threshold = raw_settings.get(
            "relation_default_review_threshold",
        )
        if isinstance(relation_default_review_threshold, float | int):
            settings["relation_default_review_threshold"] = max(
                0.0,
                min(float(relation_default_review_threshold), 1.0),
            )

        raw_relation_thresholds = raw_settings.get("relation_review_thresholds")
        if isinstance(raw_relation_thresholds, Mapping):
            relation_thresholds: dict[str, float] = {}
            for raw_relation_type, raw_threshold in raw_relation_thresholds.items():
                if not isinstance(raw_relation_type, str):
                    continue
                normalized_relation_type = raw_relation_type.strip().upper()
                if not normalized_relation_type:
                    continue
                if isinstance(raw_threshold, float | int):
                    relation_thresholds[normalized_relation_type] = max(
                        0.0,
                        min(float(raw_threshold), 1.0),
                    )
            if relation_thresholds:
                settings["relation_review_thresholds"] = relation_thresholds

        return settings

    @staticmethod
    def _resolve_relation_types(
        contract: GraphConnectionContract,
    ) -> tuple[str, ...] | None:
        relation_types: list[str] = []
        for relation in contract.proposed_relations:
            normalized = relation.relation_type.strip().upper()
            if not normalized or normalized in relation_types:
                continue
            relation_types.append(normalized)
        return tuple(relation_types) if relation_types else None

    def _submit_review_item(
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        reason: str,
    ) -> None:
        submitter = self._review_queue_submitter
        if submitter is None:
            return
        try:
            submitter(
                "graph_connection_seed",
                seed_entity_id,
                research_space_id,
                self._review_priority_for_reason(reason),
            )
        except Exception as exc:  # noqa: BLE001 - do not block graph writes
            logger.warning(
                "Failed to enqueue graph-connection review item for seed=%s: %s",
                seed_entity_id,
                exc,
            )

    @staticmethod
    def _review_priority_for_reason(reason: str) -> str:
        if reason in {"agent_requested_escalation", "evidence_required"}:
            return "high"
        if reason == "confidence_below_threshold":
            return "medium"
        return "low"

    @staticmethod
    def _resolve_run_id(contract: GraphConnectionContract) -> str | None:
        run_id = contract.agent_run_id
        if not isinstance(run_id, str):
            return None
        normalized = run_id.strip()
        return normalized or None

    @staticmethod
    def _build_outcome(  # noqa: PLR0913
        *,
        contract: GraphConnectionContract,
        governance: GovernanceDecision,
        run_id: str | None,
        wrote_to_graph: bool,
        reason: str,
        persisted_relations_count: int = 0,
        errors: tuple[str, ...] = (),
    ) -> GraphConnectionOutcome:
        status: Literal["discovered", "failed"] = (
            "discovered" if wrote_to_graph or governance.shadow_mode else "failed"
        )
        return GraphConnectionOutcome(
            seed_entity_id=contract.seed_entity_id,
            research_space_id=contract.research_space_id,
            status=status,
            reason=reason,
            review_required=governance.requires_review,
            shadow_mode=governance.shadow_mode,
            wrote_to_graph=wrote_to_graph,
            run_id=run_id,
            proposed_relations_count=len(contract.proposed_relations),
            persisted_relations_count=persisted_relations_count,
            rejected_candidates_count=len(contract.rejected_candidates),
            errors=errors,
        )


__all__ = [
    "GraphConnectionOutcome",
    "GraphConnectionService",
    "GraphConnectionServiceDependencies",
]
