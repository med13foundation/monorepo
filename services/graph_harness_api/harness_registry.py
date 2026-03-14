"""Static harness template registry for the standalone harness service."""

from __future__ import annotations

from dataclasses import dataclass

from services.graph_harness_api.run_budget import (
    budget_to_json,
    default_continuous_learning_run_budget,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


@dataclass(frozen=True, slots=True)
class HarnessTemplate:
    """One discoverable harness template."""

    id: str
    display_name: str
    summary: str
    tool_groups: tuple[str, ...]
    outputs: tuple[str, ...]
    default_run_budget: JSONObject | None = None


_HARNESS_TEMPLATES: tuple[HarnessTemplate, ...] = (
    HarnessTemplate(
        id="graph-search",
        display_name="Graph Search Agent Run",
        summary="Run AI-backed graph search orchestration against one research space.",
        tool_groups=(
            "graph-read",
            "agent-search",
            "artifact-write",
        ),
        outputs=(
            "graph-search-result",
            "evidence-bundle",
        ),
    ),
    HarnessTemplate(
        id="graph-connections",
        display_name="Graph Connection Agent Run",
        summary="Run AI-backed graph-connection discovery against one or more seed entities.",
        tool_groups=(
            "graph-read",
            "agent-connection",
            "artifact-write",
        ),
        outputs=(
            "graph-connection-result",
            "proposed-relations",
        ),
    ),
    HarnessTemplate(
        id="hypotheses",
        display_name="Hypothesis Exploration Run",
        summary="Run AI-backed hypothesis exploration and stage candidate claims as artifacts.",
        tool_groups=(
            "graph-read",
            "agent-connection",
            "proposal-write",
            "artifact-write",
        ),
        outputs=(
            "hypothesis-candidates",
            "proposal-pack",
        ),
    ),
    HarnessTemplate(
        id="research-bootstrap",
        display_name="Research Bootstrap Harness",
        summary="Bootstrap a research space from graph, literature, and extraction tools.",
        tool_groups=(
            "graph-read",
            "literature-search",
            "source-discovery",
            "enrichment",
            "extraction",
            "proposal-write",
        ),
        outputs=(
            "research-brief",
            "graph-summary",
            "graph-context-snapshot",
            "source-inventory",
            "candidate-claim-pack",
        ),
    ),
    HarnessTemplate(
        id="graph-chat",
        display_name="Graph Chat Harness",
        summary="Answer grounded questions using deterministic graph reads and harness memory.",
        tool_groups=(
            "graph-read",
            "graph-document",
            "graph-view",
            "artifact-read",
            "literature-refresh",
        ),
        outputs=(
            "grounded-answer",
            "evidence-bundle",
            "fresh-literature",
            "chat-summary",
            "graph-write-proposals",
        ),
    ),
    HarnessTemplate(
        id="continuous-learning",
        display_name="Continuous Learning Harness",
        summary="Run scheduled research refresh cycles and stage evidence-backed proposals.",
        tool_groups=(
            "graph-read",
            "artifact-read",
            "literature-refresh",
            "comparison",
            "proposal-write",
        ),
        outputs=(
            "delta-report",
            "new-paper-list",
            "candidate-claims",
            "next-question-backlog",
        ),
        default_run_budget=budget_to_json(default_continuous_learning_run_budget()),
    ),
    HarnessTemplate(
        id="mechanism-discovery",
        display_name="Mechanism Discovery Harness",
        summary="Search for converging mechanisms using reasoning paths and discovery tools.",
        tool_groups=(
            "reasoning-read",
            "graph-connection-discovery",
            "claim-evidence-read",
            "ranking",
            "proposal-write",
        ),
        outputs=(
            "mechanism-candidates",
            "mechanism-score-report",
            "candidate-hypothesis-pack",
        ),
    ),
    HarnessTemplate(
        id="claim-curation",
        display_name="Claim Curation Harness",
        summary="Prepare governed graph updates for curator review and approval.",
        tool_groups=(
            "proposal-read",
            "claim-validation",
            "approval-gated-write",
            "graph-write",
        ),
        outputs=(
            "curation-packet",
            "review-plan",
            "approval-intent",
            "curation-summary",
            "curation-actions",
        ),
    ),
    HarnessTemplate(
        id="supervisor",
        display_name="Supervisor Harness",
        summary=(
            "Compose bootstrap, briefing chat, and governed curation into one "
            "multi-step workflow."
        ),
        tool_groups=(
            "workflow-composition",
            "graph-read",
            "artifact-read-write",
            "chat-briefing",
            "approval-gated-write",
        ),
        outputs=(
            "supervisor-plan",
            "supervisor-summary",
            "child-run-links",
        ),
    ),
)


def list_harness_templates() -> tuple[HarnessTemplate, ...]:
    """Return all registered harness templates."""
    return _HARNESS_TEMPLATES


def get_harness_template(harness_id: str) -> HarnessTemplate | None:
    """Return one harness template by identifier."""
    normalized = harness_id.strip()
    if not normalized:
        return None
    for template in _HARNESS_TEMPLATES:
        if template.id == normalized:
            return template
    return None


__all__ = ["HarnessTemplate", "get_harness_template", "list_harness_templates"]
