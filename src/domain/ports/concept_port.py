"""Domain port for Concept Manager operations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.concepts import (
    ConceptAlias,  # noqa: TC001
    ConceptDecision,  # noqa: TC001
    ConceptDecisionStatus,  # noqa: TC001
    ConceptDecisionType,  # noqa: TC001
    ConceptMember,  # noqa: TC001
    ConceptPolicy,  # noqa: TC001
    ConceptPolicyMode,  # noqa: TC001
    ConceptSet,  # noqa: TC001
)
from src.type_definitions.common import JSONObject, ResearchSpaceSettings  # noqa: TC001


class ConceptPort(ABC):
    """Domain-wide interface for Concept Manager lifecycle operations."""

    @abstractmethod
    def create_concept_set(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        name: str,
        slug: str,
        domain_context: str,
        description: str | None = None,
        created_by: str,
        source_ref: str | None = None,
    ) -> ConceptSet:
        """Create one concept set in a research space."""

    @abstractmethod
    def list_concept_sets(
        self,
        *,
        research_space_id: str,
        include_inactive: bool = False,
    ) -> list[ConceptSet]:
        """List concept sets in one research space."""

    @abstractmethod
    def create_concept_member(  # noqa: PLR0913
        self,
        *,
        concept_set_id: str,
        research_space_id: str,
        domain_context: str,
        canonical_label: str,
        normalized_label: str,
        sense_key: str = "",
        dictionary_dimension: str | None = None,
        dictionary_entry_id: str | None = None,
        is_provisional: bool = False,
        metadata_payload: JSONObject | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ConceptMember:
        """Create one concept member."""

    @abstractmethod
    def list_concept_members(
        self,
        *,
        research_space_id: str,
        concept_set_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptMember]:
        """List concept members in one research space."""

    @abstractmethod
    def create_concept_alias(  # noqa: PLR0913
        self,
        *,
        concept_member_id: str,
        research_space_id: str,
        domain_context: str,
        alias_label: str,
        alias_normalized: str,
        source: str | None = None,
        created_by: str,
        source_ref: str | None = None,
    ) -> ConceptAlias:
        """Create one alias for a concept member."""

    @abstractmethod
    def list_concept_aliases(
        self,
        *,
        research_space_id: str,
        concept_member_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptAlias]:
        """List concept aliases in one research space."""

    @abstractmethod
    def resolve_member_by_alias(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        alias_normalized: str,
        include_inactive: bool = False,
    ) -> ConceptMember | None:
        """Resolve one alias to a concept member in scope."""

    @abstractmethod
    def upsert_active_policy(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        mode: ConceptPolicyMode,
        created_by: str,
        minimum_edge_confidence: float = 0.6,
        minimum_distinct_documents: int = 1,
        allow_generic_relations: bool = True,
        max_edges_per_document: int | None = None,
        policy_payload: JSONObject | None = None,
        source_ref: str | None = None,
    ) -> ConceptPolicy:
        """Create/update the single active concept policy profile."""

    @abstractmethod
    def get_active_policy(
        self,
        *,
        research_space_id: str,
    ) -> ConceptPolicy | None:
        """Fetch the active concept policy for one research space."""

    @abstractmethod
    def propose_decision(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        decision_type: ConceptDecisionType,
        proposed_by: str,
        decision_payload: JSONObject | None = None,
        evidence_payload: JSONObject | None = None,
        confidence: float | None = None,
        rationale: str | None = None,
        concept_set_id: str | None = None,
        concept_member_id: str | None = None,
        concept_link_id: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ConceptDecision:
        """Create one governance decision and evaluate it through harness."""

    @abstractmethod
    def set_decision_status(
        self,
        decision_id: str,
        *,
        decision_status: ConceptDecisionStatus,
        decided_by: str,
    ) -> ConceptDecision:
        """Set one decision status manually."""

    @abstractmethod
    def list_decisions(
        self,
        *,
        research_space_id: str,
        decision_status: ConceptDecisionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptDecision]:
        """List concept decisions in one research space."""
