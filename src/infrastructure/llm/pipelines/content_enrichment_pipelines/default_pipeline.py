"""Default Flujo pipeline for Tier-2 content-enrichment executions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from flujo import Flujo, Pipeline
from flujo.domain.dsl import ConditionalStep, GranularStep, Step
from flujo.domain.models import UsageLimits as FlujoUsageLimits

from src.domain.agents.contexts.content_enrichment_context import (
    ContentEnrichmentContext,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.content_enrichment import ContentEnrichmentContract
from src.infrastructure.llm.config.governance import GovernanceConfig, UsageLimits
from src.infrastructure.llm.content_enrichment_full_text import (
    fetch_pubmed_open_access_full_text,
)
from src.infrastructure.llm.factories.content_enrichment_agent_factory import (
    create_content_enrichment_agent,
)

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

_FULL_TEXT_METHODS = frozenset({"pmc_oa", "europe_pmc", "publisher_pdf"})


async def _run_deterministic_full_text_fetch(
    _input_text: str,
    *,
    context: ContentEnrichmentContext,
) -> ContentEnrichmentContract:
    source_type = context.source_type.strip().lower()
    if source_type != "pubmed":
        return ContentEnrichmentContract(
            decision="skipped",
            confidence_score=1.0,
            rationale=(
                "Deterministic full-text retrieval is configured for PubMed "
                "documents only."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"document:{context.document_id}",
                    excerpt=(
                        f"Source type '{context.source_type}' bypasses deterministic "
                        "PubMed full-text retrieval."
                    ),
                    relevance=1.0,
                ),
            ],
            document_id=context.document_id,
            source_type=context.source_type,
            acquisition_method="skipped",
            content_format="text",
            content_length_chars=0,
            content_text=None,
            content_payload=None,
            warning="Deterministic full-text retrieval skipped for non-PubMed source.",
            agent_run_id=None,
        )

    fetch_result = await asyncio.to_thread(
        fetch_pubmed_open_access_full_text,
        context.existing_metadata,
    )
    if fetch_result.found and isinstance(fetch_result.content_text, str):
        content_text = fetch_result.content_text.strip()
        if content_text:
            method = fetch_result.acquisition_method
            return ContentEnrichmentContract(
                decision="enriched",
                confidence_score=0.99,
                rationale=(
                    "Deterministic open-access full-text retrieval succeeded before "
                    "agent execution."
                ),
                evidence=[
                    EvidenceItem(
                        source_type="web",
                        locator=fetch_result.source_url or "open_access_endpoint",
                        excerpt=(
                            f"Retrieved full text via {method} "
                            f"({len(content_text)} chars)."
                        ),
                        relevance=0.99,
                    ),
                ],
                document_id=context.document_id,
                source_type=context.source_type,
                acquisition_method=method,
                content_format="text",
                content_length_chars=len(content_text),
                content_text=content_text,
                content_payload=None,
                warning=fetch_result.warning,
                agent_run_id=None,
            )

    attempted_sources = ", ".join(fetch_result.attempted_sources) or "none"
    warning = fetch_result.warning or "No deterministic open-access full text found."
    return ContentEnrichmentContract(
        decision="skipped",
        confidence_score=0.6,
        rationale=(
            "Deterministic open-access full-text retrieval did not return a usable "
            "article body; routing to agent fallback."
        ),
        evidence=[
            EvidenceItem(
                source_type="web",
                locator=fetch_result.source_url or "open_access_endpoint",
                excerpt=f"Deterministic attempts: {attempted_sources}.",
                relevance=0.6,
            ),
        ],
        document_id=context.document_id,
        source_type=context.source_type,
        acquisition_method="skipped",
        content_format="text",
        content_length_chars=0,
        content_text=None,
        content_payload=None,
        warning=warning,
        agent_run_id=None,
    )


def _route_content_enrichment_step(
    output: object,
    _ctx: ContentEnrichmentContext | None,
) -> str:
    if (
        isinstance(output, ContentEnrichmentContract)
        and output.decision == "enriched"
        and output.acquisition_method in _FULL_TEXT_METHODS
        and output.content_length_chars > 0
    ):
        return "done"
    return "agent"


def create_content_enrichment_pipeline(
    state_backend: StateBackend,
    *,
    model: str | None = None,
    usage_limits: UsageLimits | None = None,
    tools: list[object] | None = None,
) -> Flujo[str, ContentEnrichmentContract, ContentEnrichmentContext]:
    """Create a content-enrichment pipeline with deterministic full-text prefetch."""
    governance = GovernanceConfig.from_environment()
    limits = usage_limits or governance.usage_limits
    agent = create_content_enrichment_agent(
        model=model,
        tools=tools,
    )
    deterministic_step = Step.from_callable(
        _run_deterministic_full_text_fetch,
        name="deterministic_pubmed_full_text_fetch",
    )
    route_step: ConditionalStep[ContentEnrichmentContext] = ConditionalStep(
        name="route_content_enrichment_execution",
        condition_callable=_route_content_enrichment_step,
        branches={
            "done": Pipeline(steps=[]),
            "agent": Pipeline(
                steps=[
                    GranularStep(
                        name="run_content_enrichment",
                        agent=agent,
                        enforce_idempotency=True,
                        history_max_tokens=8192,
                    ),
                ],
            ),
        },
    )

    return Flujo(
        Pipeline(steps=[deterministic_step, route_step]),
        context_model=ContentEnrichmentContext,
        state_backend=state_backend,
        persist_state=True,
        usage_limits=_to_flujo_usage_limits(limits),
    )


def _to_flujo_usage_limits(limits: UsageLimits) -> FlujoUsageLimits:
    return FlujoUsageLimits(
        total_cost_usd_limit=limits.total_cost_usd,
        total_tokens_limit=limits.max_tokens,
    )
