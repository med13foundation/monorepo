"""Concept Manager repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.concepts import (
    ConceptAlias,  # noqa: TC001
    ConceptDecision,  # noqa: TC001
    ConceptDecisionStatus,  # noqa: TC001
    ConceptDecisionType,  # noqa: TC001
    ConceptHarnessOutcome,  # noqa: TC001
    ConceptHarnessResult,  # noqa: TC001
    ConceptLink,  # noqa: TC001
    ConceptMember,  # noqa: TC001
    ConceptPolicy,  # noqa: TC001
    ConceptPolicyMode,  # noqa: TC001
    ConceptSet,  # noqa: TC001
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class ConceptRepository(ABC):
    """Read/write contract for Concept Manager tables."""

    @abstractmethod
    def create_concept_set(  # noqa: PLR0913
        self,
        *,
        set_id: str,
        research_space_id: str,
        name: str,
        slug: str,
        domain_context: str,
        description: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptSet:
        """Create one concept set."""

    @abstractmethod
    def get_concept_set(self, set_id: str) -> ConceptSet | None:
        """Fetch one concept set by ID."""

    @abstractmethod
    def find_concept_sets(
        self,
        *,
        research_space_id: str,
        include_inactive: bool = False,
    ) -> list[ConceptSet]:
        """List concept sets in one research space."""

    @abstractmethod
    def find_concept_members(
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
    def create_concept_member(  # noqa: PLR0913
        self,
        *,
        member_id: str,
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
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptMember:
        """Create one concept member."""

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
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptAlias:
        """Create one concept alias."""

    @abstractmethod
    def find_concept_aliases(
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
        """Resolve an alias to one concept member in scope."""

    @abstractmethod
    def create_concept_link(  # noqa: PLR0913
        self,
        *,
        link_id: str,
        research_space_id: str,
        source_member_id: str,
        target_member_id: str,
        link_type: str,
        confidence: float = 1.0,
        metadata_payload: JSONObject | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptLink:
        """Create one typed link between concept members."""

    @abstractmethod
    def deactivate_active_policies(
        self,
        *,
        research_space_id: str,
    ) -> int:
        """Deactivate all currently active policy rows in one space."""

    @abstractmethod
    def create_concept_policy(  # noqa: PLR0913
        self,
        *,
        policy_id: str,
        research_space_id: str,
        mode: ConceptPolicyMode,
        created_by: str = "seed",
        profile_name: str = "default",
        minimum_edge_confidence: float = 0.6,
        minimum_distinct_documents: int = 1,
        allow_generic_relations: bool = True,
        max_edges_per_document: int | None = None,
        policy_payload: JSONObject | None = None,
        source_ref: str | None = None,
        is_active: bool = True,
    ) -> ConceptPolicy:
        """Create one concept policy row."""

    @abstractmethod
    def get_active_policy(
        self,
        *,
        research_space_id: str,
    ) -> ConceptPolicy | None:
        """Return the active policy for one research space."""

    @abstractmethod
    def create_decision(  # noqa: PLR0913
        self,
        *,
        decision_id: str,
        research_space_id: str,
        decision_type: ConceptDecisionType,
        decision_status: ConceptDecisionStatus,
        proposed_by: str,
        concept_set_id: str | None = None,
        concept_member_id: str | None = None,
        concept_link_id: str | None = None,
        confidence: float | None = None,
        rationale: str | None = None,
        evidence_payload: JSONObject | None = None,
        decision_payload: JSONObject | None = None,
        harness_outcome: ConceptHarnessOutcome | None = None,
        decided_by: str | None = None,
    ) -> ConceptDecision:
        """Create one decision row."""

    @abstractmethod
    def set_decision_status(
        self,
        decision_id: str,
        *,
        decision_status: ConceptDecisionStatus,
        decided_by: str,
        harness_outcome: ConceptHarnessOutcome | None = None,
    ) -> ConceptDecision:
        """Set decision state and metadata."""

    @abstractmethod
    def find_decisions(
        self,
        *,
        research_space_id: str,
        decision_status: ConceptDecisionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptDecision]:
        """List concept decisions in one research space."""

    @abstractmethod
    def create_harness_result(  # noqa: PLR0913
        self,
        *,
        result_id: str,
        research_space_id: str,
        harness_name: str,
        outcome: ConceptHarnessOutcome,
        checks_payload: JSONObject | None = None,
        errors_payload: list[str] | None = None,
        metadata_payload: JSONObject | None = None,
        decision_id: str | None = None,
        harness_version: str | None = None,
        run_id: str | None = None,
    ) -> ConceptHarnessResult:
        """Persist one harness execution result row."""
