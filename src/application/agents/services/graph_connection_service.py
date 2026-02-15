"""Application service for graph-connection agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.application.agents.services.governance_service import (
    GovernanceDecision,
    GovernanceService,
)
from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext

if TYPE_CHECKING:
    from src.domain.agents.contracts.graph_connection import GraphConnectionContract
    from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
    from src.domain.repositories.kernel.relation_repository import (
        KernelRelationRepository,
    )
    from src.type_definitions.common import ResearchSpaceSettings


@dataclass(frozen=True)
class GraphConnectionServiceDependencies:
    """Dependencies required by graph-connection orchestration."""

    graph_connection_agent: GraphConnectionPort
    relation_repository: KernelRelationRepository
    governance_service: GovernanceService | None = None


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
    ) -> GraphConnectionOutcome:
        """Run one graph-connection discovery pass for a seed entity."""
        requested_shadow_mode = shadow_mode if isinstance(shadow_mode, bool) else False
        context = GraphConnectionContext(
            seed_entity_id=seed_entity_id,
            source_type=source_type,
            research_space_id=research_space_id,
            research_space_settings=research_space_settings or {},
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
            research_space_settings=research_space_settings,
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
                )
                persisted_count += 1
            except (TypeError, ValueError) as exc:
                persistence_errors.append(str(exc))

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
