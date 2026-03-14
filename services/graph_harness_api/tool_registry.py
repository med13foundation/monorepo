"""Typed Artana tool registry for graph-harness kernel workflows."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid5

from artana.ports.tool import LocalToolRegistry, ToolExecutionContext

from services.graph_harness_api.graph_client import GraphApiGateway
from services.graph_harness_api.tool_catalog import (
    get_graph_harness_tool_spec,
    list_graph_harness_tool_specs,
)
from src.application.services.pubmed_discovery_service import RunPubmedSearchRequest
from src.database.session import SessionLocal, set_session_rls_context
from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,
    PubMedSortOption,
)
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.type_definitions.graph_service_contracts import (
    CreateManualHypothesisRequest,
    KernelGraphDocumentRequest,
    KernelRelationClaimCreateRequest,
    KernelRelationSuggestionRequest,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import date

    from artana.ports.tool import ToolPort
    from pydantic import BaseModel

    from src.application.services.pubmed_discovery_service import PubMedDiscoveryService


def _json_result(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _scoped_graph_gateway() -> GraphApiGateway:
    return GraphApiGateway()


def _scoped_pubmed_service() -> Generator[PubMedDiscoveryService]:
    session = SessionLocal()
    set_session_rls_context(session, bypass_rls=True)
    try:
        yield get_legacy_dependency_container().create_pubmed_discovery_service(session)
    finally:
        session.close()


def _owner_id_from_context(context: ToolExecutionContext) -> UUID:
    return uuid5(NAMESPACE_URL, f"harness-owner:{context.tenant_id}")


async def get_graph_document(
    space_id: str,
    seed_entity_ids: list[str],
    depth: int = 2,
    top_k: int = 25,
) -> str:
    """Fetch one graph document for deterministic read-side grounding."""
    gateway = _scoped_graph_gateway()
    try:
        document = gateway.get_graph_document(
            space_id=space_id,
            request=KernelGraphDocumentRequest(
                mode="seeded" if seed_entity_ids else "starter",
                seed_entity_ids=[
                    UUID(seed_entity_id) for seed_entity_id in seed_entity_ids
                ],
                depth=depth,
                top_k=top_k,
                include_claims=True,
                include_evidence=True,
                max_claims=max(25, top_k * 2),
                evidence_limit_per_claim=3,
            ),
        )
        return _json_result(document.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_graph_claims(
    space_id: str,
    claim_status: str | None = None,
    limit: int = 50,
) -> str:
    """List graph claims for one research space."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claims(
            space_id=space_id,
            claim_status=claim_status,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_graph_hypotheses(
    space_id: str,
    limit: int = 50,
) -> str:
    """List graph hypotheses for one research space."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_hypotheses(
            space_id=space_id,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def suggest_relations(  # noqa: PLR0913
    space_id: str,
    source_entity_ids: list[str],
    allowed_relation_types: list[str] | None = None,
    target_entity_types: list[str] | None = None,
    limit_per_source: int = 5,
    min_score: float = 0.0,
) -> str:
    """Suggest dictionary-constrained relations for one or more source entities."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.suggest_relations(
            space_id=space_id,
            request=KernelRelationSuggestionRequest(
                source_entity_ids=[UUID(entity_id) for entity_id in source_entity_ids],
                limit_per_source=limit_per_source,
                min_score=min_score,
                allowed_relation_types=allowed_relation_types,
                target_entity_types=target_entity_types,
                exclude_existing_relations=True,
            ),
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def capture_graph_snapshot(
    space_id: str,
    seed_entity_ids: list[str],
    depth: int = 2,
    top_k: int = 25,
) -> str:
    """Capture one graph-context snapshot payload for later harness artifacts."""
    gateway = _scoped_graph_gateway()
    try:
        document = gateway.get_graph_document(
            space_id=space_id,
            request=KernelGraphDocumentRequest(
                mode="seeded" if seed_entity_ids else "starter",
                seed_entity_ids=[
                    UUID(seed_entity_id) for seed_entity_id in seed_entity_ids
                ],
                depth=depth,
                top_k=top_k,
                include_claims=True,
                include_evidence=True,
                max_claims=max(25, top_k * 2),
                evidence_limit_per_claim=3,
            ),
        )
        payload = document.model_dump(mode="json")
        payload["snapshot_hash"] = str(
            uuid5(
                NAMESPACE_URL,
                json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str),
            ),
        )
        return _json_result(payload)
    finally:
        gateway.close()


async def run_pubmed_search(  # noqa: PLR0913
    search_term: str,
    gene_symbol: str | None = None,
    additional_terms: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    max_results: int = 25,
    artana_context: ToolExecutionContext | None = None,
) -> str:
    """Run one scoped PubMed discovery search and return the persisted job payload."""
    owner_id = (
        _owner_id_from_context(artana_context)
        if artana_context is not None
        else uuid5(NAMESPACE_URL, "harness-owner:pubmed")
    )
    request = RunPubmedSearchRequest(
        parameters=AdvancedQueryParameters(
            search_term=search_term,
            gene_symbol=gene_symbol,
            additional_terms=additional_terms,
            date_from=date_from,
            date_to=date_to,
            max_results=max_results,
            sort_by=PubMedSortOption.RELEVANCE,
        ),
    )
    service_generator = _scoped_pubmed_service()
    service = next(service_generator)
    try:
        job = await service.run_pubmed_search(owner_id=owner_id, request=request)
        return _json_result(job.model_dump(mode="json"))
    finally:
        with suppress(StopIteration):
            next(service_generator)


async def list_reasoning_paths(  # noqa: PLR0913
    space_id: str,
    start_entity_id: str | None = None,
    end_entity_id: str | None = None,
    status: str | None = None,
    path_kind: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List reasoning paths for one graph space."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_reasoning_paths(
            space_id=space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
            offset=offset,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def get_reasoning_path(
    space_id: str,
    path_id: str,
) -> str:
    """Fetch one explained reasoning path."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.get_reasoning_path(
            space_id=space_id,
            path_id=path_id,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_claims_by_entity(
    space_id: str,
    entity_id: str,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List graph claims connected to one entity."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claims_by_entity(
            space_id=space_id,
            entity_id=entity_id,
            offset=offset,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_claim_participants(
    space_id: str,
    claim_id: str,
) -> str:
    """List participants for one graph claim."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claim_participants(
            space_id=space_id,
            claim_id=claim_id,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_claim_evidence(
    space_id: str,
    claim_id: str,
) -> str:
    """List evidence rows for one graph claim."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claim_evidence(
            space_id=space_id,
            claim_id=claim_id,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_relation_conflicts(
    space_id: str,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List mixed-polarity canonical relation conflicts."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_relation_conflicts(
            space_id=space_id,
            offset=offset,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def create_graph_claim(  # noqa: PLR0913
    space_id: str,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    claim_text: str,
    source_document_ref: str,
    confidence: float,
    evidence_summary: str,
    artana_context: ToolExecutionContext,
) -> str:
    """Create one unresolved graph claim through the governed graph-service path."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.create_claim(
            space_id=space_id,
            request=KernelRelationClaimCreateRequest(
                source_entity_id=UUID(source_entity_id),
                target_entity_id=UUID(target_entity_id),
                relation_type=relation_type,
                confidence=confidence,
                claim_text=claim_text,
                evidence_summary=evidence_summary,
                source_document_ref=source_document_ref,
                agent_run_id=artana_context.run_id,
                metadata={
                    "artana_idempotency_key": artana_context.idempotency_key,
                },
            ),
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def create_manual_hypothesis(  # noqa: PLR0913
    space_id: str,
    statement: str,
    rationale: str,
    seed_entity_ids: list[str],
    source_type: str,
    artana_context: ToolExecutionContext,
) -> str:
    """Create one manual graph hypothesis through the graph-service path."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.create_manual_hypothesis(
            space_id=space_id,
            request=CreateManualHypothesisRequest(
                statement=statement,
                rationale=rationale,
                seed_entity_ids=seed_entity_ids,
                source_type=source_type,
                metadata={
                    "artana_idempotency_key": artana_context.idempotency_key,
                    "artana_run_id": artana_context.run_id,
                },
            ),
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


_REGISTERED_FUNCTIONS = {
    "get_graph_document": get_graph_document,
    "list_graph_claims": list_graph_claims,
    "list_graph_hypotheses": list_graph_hypotheses,
    "suggest_relations": suggest_relations,
    "capture_graph_snapshot": capture_graph_snapshot,
    "run_pubmed_search": run_pubmed_search,
    "list_reasoning_paths": list_reasoning_paths,
    "get_reasoning_path": get_reasoning_path,
    "list_claims_by_entity": list_claims_by_entity,
    "list_claim_participants": list_claim_participants,
    "list_claim_evidence": list_claim_evidence,
    "list_relation_conflicts": list_relation_conflicts,
    "create_graph_claim": create_graph_claim,
    "create_manual_hypothesis": create_manual_hypothesis,
}


def build_graph_harness_tool_registry() -> ToolPort:
    """Register the typed graph and discovery tools exposed to harness runs."""
    registry = LocalToolRegistry()
    for spec in list_graph_harness_tool_specs():
        function = _REGISTERED_FUNCTIONS[spec.name]
        registry.register(
            function,
            requires_capability=spec.required_capability,
            side_effect=spec.side_effect,
            tool_version=spec.tool_version,
            schema_version=spec.schema_version,
            risk_level=spec.risk_level,
        )
    return registry


def tool_argument_model(tool_name: str) -> type[BaseModel]:
    """Return the declared Pydantic argument model for one tool name."""
    spec = get_graph_harness_tool_spec(tool_name)
    if spec is None:
        msg = f"Unknown graph-harness tool {tool_name!r}."
        raise KeyError(msg)
    return spec.input_model


__all__ = [
    "build_graph_harness_tool_registry",
    "tool_argument_model",
]
