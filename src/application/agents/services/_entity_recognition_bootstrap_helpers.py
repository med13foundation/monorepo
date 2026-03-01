"""Cold-start dictionary bootstrap helpers for entity-recognition orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.agents.services._entity_recognition_bootstrap_constants import (
    _DEFAULT_BOOTSTRAP_RELATION_TYPE,
    _DEFAULT_INTERACTION_RELATION_TYPE,
    _MIN_BOOTSTRAP_ENTITY_TYPES_FOR_RELATION,
    _PUBMED_METADATA_VARIABLE_SPECS,
    _PUBMED_PUBLICATION_BASELINE_CONSTRAINTS,
    _PUBMED_PUBLICATION_BASELINE_ENTITY_TYPES,
    _PUBMED_PUBLICATION_BASELINE_RELATION_TYPES,
)
from src.domain.services.domain_context_resolver import DomainContextResolver

if TYPE_CHECKING:
    from src.application.agents.services._entity_recognition_bootstrap_protocols import (
        _EntityRecognitionBootstrapContext,
    )
    from src.type_definitions.common import JSONValue, ResearchSpaceSettings


class _EntityRecognitionBootstrapHelpers:
    """Mixin with domain cold-start bootstrap support."""

    def _ensure_domain_bootstrap(  # noqa: PLR0913, C901
        self: _EntityRecognitionBootstrapContext,
        *,
        source_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int]:
        if not self._is_domain_bootstrap_enabled(research_space_settings):
            return 0, 0

        bootstrap_review_settings = self._bootstrap_review_settings(
            research_space_settings,
        )
        domain_context = self._infer_domain_context(source_type)
        has_existing_entries = bool(
            self._dictionary.dictionary_search_by_domain(
                domain_context=domain_context,
                limit=1,
                include_inactive=False,
            ),
        )
        created_entity_types = 0
        entity_types = self._bootstrap_entity_types_for_domain(domain_context)
        if not has_existing_entries:
            for entity_type_id in entity_types:
                if self._dictionary.get_entity_type(entity_type_id) is not None:
                    continue
                self._dictionary.create_entity_type(
                    entity_type=entity_type_id,
                    display_name=self._to_display_name(entity_type_id),
                    description=(
                        f"Bootstrap entity type for domain '{domain_context}' "
                        f"generated from source type '{source_type}'."
                    ),
                    domain_context=domain_context,
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )
                created_entity_types += 1

        bootstrap_variable_id = self._bootstrap_variable_id(domain_context)
        created_variables = 0
        if (
            not has_existing_entries
            and self._dictionary.get_variable(bootstrap_variable_id) is None
        ):
            self._dictionary.create_variable(
                variable_id=bootstrap_variable_id,
                canonical_name=f"{domain_context}_evidence_signal",
                display_name=f"{self._to_display_name(domain_context)} Evidence Signal",
                data_type="STRING",
                domain_context=domain_context,
                sensitivity="INTERNAL",
                description=(
                    f"Bootstrap variable for domain '{domain_context}' used to "
                    "establish minimal dictionary coverage."
                ),
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )
            created_variables += 1

        if not has_existing_entries:
            if (
                self._dictionary.get_relation_type(_DEFAULT_BOOTSTRAP_RELATION_TYPE)
                is None
            ):
                self._dictionary.create_relation_type(
                    relation_type=_DEFAULT_BOOTSTRAP_RELATION_TYPE,
                    display_name="Associated With",
                    description=(
                        "Generic bootstrap relation for domain initialization and "
                        "cross-entity linkage."
                    ),
                    domain_context=domain_context,
                    is_directional=True,
                    inverse_label="ASSOCIATED_WITH",
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )
            if (
                self._dictionary.get_relation_type(_DEFAULT_INTERACTION_RELATION_TYPE)
                is None
            ):
                self._dictionary.create_relation_type(
                    relation_type=_DEFAULT_INTERACTION_RELATION_TYPE,
                    display_name="Physically Interacts With",
                    description=(
                        "Physical interaction relation for molecular entities "
                        "derived from curated evidence."
                    ),
                    domain_context=domain_context,
                    is_directional=False,
                    inverse_label="PHYSICALLY_INTERACTS_WITH",
                    created_by=self._agent_created_by,
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )

            if len(entity_types) >= _MIN_BOOTSTRAP_ENTITY_TYPES_FOR_RELATION:
                self._ensure_relation_constraint(
                    source_type=entity_types[0],
                    target_type=entity_types[1],
                    source_ref=source_ref,
                    research_space_settings=bootstrap_review_settings,
                )

            for interaction_entity_type in ("GENE", "PROTEIN"):
                if self._dictionary.get_entity_type(interaction_entity_type) is None:
                    self._dictionary.create_entity_type(
                        entity_type=interaction_entity_type,
                        display_name=self._to_display_name(interaction_entity_type),
                        description=(
                            "Bootstrap molecular entity type used for interaction "
                            "relation constraints."
                        ),
                        domain_context=domain_context,
                        created_by=self._agent_created_by,
                        source_ref=source_ref,
                        research_space_settings=bootstrap_review_settings,
                    )
                    created_entity_types += 1

            self._ensure_relation_constraint_for_type(
                relation_triplet=("GENE", _DEFAULT_INTERACTION_RELATION_TYPE, "GENE"),
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )
            self._ensure_relation_constraint_for_type(
                relation_triplet=(
                    "PROTEIN",
                    _DEFAULT_INTERACTION_RELATION_TYPE,
                    "PROTEIN",
                ),
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )

        normalized_source_type = DomainContextResolver.normalize(source_type)
        if normalized_source_type == "pubmed":
            (
                pubmed_entity_types_created,
                pubmed_variables_created,
            ) = self._ensure_pubmed_publication_baseline(
                domain_context=domain_context,
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )
            created_entity_types += pubmed_entity_types_created
            created_variables += pubmed_variables_created

        return created_variables, created_entity_types

    def _ensure_relation_constraint(
        self: _EntityRecognitionBootstrapContext,
        *,
        source_type: str,
        target_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> None:
        self._dictionary.create_relation_constraint(
            source_type=source_type,
            relation_type=_DEFAULT_BOOTSTRAP_RELATION_TYPE,
            target_type=target_type,
            is_allowed=True,
            requires_evidence=True,
            created_by=self._agent_created_by,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )

    def _ensure_relation_constraint_for_type(
        self: _EntityRecognitionBootstrapContext,
        *,
        relation_triplet: tuple[str, str, str],
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
        requires_evidence: bool = True,
    ) -> None:
        source_type, relation_type, target_type = relation_triplet
        self._dictionary.create_relation_constraint(
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            is_allowed=True,
            requires_evidence=requires_evidence,
            created_by=self._agent_created_by,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )

    def _ensure_pubmed_publication_baseline(
        self: _EntityRecognitionBootstrapContext,
        *,
        domain_context: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> tuple[int, int]:
        created_entity_types = 0
        created_variables = 0

        for entity_type_id in _PUBMED_PUBLICATION_BASELINE_ENTITY_TYPES:
            if self._dictionary.get_entity_type(entity_type_id) is not None:
                continue
            self._dictionary.create_entity_type(
                entity_type=entity_type_id,
                display_name=self._to_display_name(entity_type_id),
                description=(
                    "PubMed publication-graph bootstrap entity type used for "
                    "relation validation."
                ),
                domain_context=domain_context,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            created_entity_types += 1

        for (
            relation_type_id,
            display_name,
            description,
            is_directional,
            inverse_label,
        ) in _PUBMED_PUBLICATION_BASELINE_RELATION_TYPES:
            if self._dictionary.get_relation_type(relation_type_id) is not None:
                continue
            self._dictionary.create_relation_type(
                relation_type=relation_type_id,
                display_name=display_name,
                description=description,
                domain_context=domain_context,
                is_directional=is_directional,
                inverse_label=inverse_label,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

        for (
            source_type,
            relation_type,
            target_type,
            requires_evidence,
        ) in _PUBMED_PUBLICATION_BASELINE_CONSTRAINTS:
            self._ensure_relation_constraint_for_type(
                relation_triplet=(source_type, relation_type, target_type),
                requires_evidence=requires_evidence,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

        for (
            variable_id,
            canonical_name,
            display_name,
            data_type,
            description,
            constraints,
            synonyms,
        ) in _PUBMED_METADATA_VARIABLE_SPECS:
            created_variables += self._ensure_pubmed_metadata_variable(
                variable_id=variable_id,
                canonical_name=canonical_name,
                display_name=display_name,
                data_type=data_type,
                description=description,
                constraints=constraints,
                synonyms=synonyms,
                domain_context=domain_context,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

        return created_entity_types, created_variables

    def _ensure_pubmed_metadata_variable(  # noqa: PLR0913
        self: _EntityRecognitionBootstrapContext,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        description: str,
        constraints: dict[str, JSONValue] | None,
        synonyms: tuple[str, ...],
        domain_context: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> int:
        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            for synonym in synonyms:
                resolved = self._dictionary.resolve_synonym(synonym)
                if resolved is not None:
                    variable = resolved
                    break

        created_variables = 0
        if variable is None:
            variable = self._dictionary.create_variable(
                variable_id=variable_id,
                canonical_name=canonical_name,
                display_name=display_name,
                data_type=data_type,
                domain_context=domain_context,
                sensitivity="PUBLIC",
                constraints=constraints,
                description=description,
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            created_variables = 1

        self._ensure_variable_synonyms(
            variable_id=variable.id,
            synonyms=synonyms,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )
        return created_variables

    def _ensure_variable_synonyms(
        self: _EntityRecognitionBootstrapContext,
        *,
        variable_id: str,
        synonyms: tuple[str, ...],
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> None:
        for synonym in synonyms:
            resolved = self._dictionary.resolve_synonym(synonym)
            if resolved is not None:
                continue
            self._dictionary.create_synonym(
                variable_id=variable_id,
                synonym=synonym,
                source="pubmed",
                created_by=self._agent_created_by,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )

    @staticmethod
    def _bootstrap_entity_types_for_domain(domain_context: str) -> tuple[str, ...]:
        normalized = domain_context.strip().lower()
        if normalized == "genomics":
            return ("GENE", "PROTEIN", "VARIANT", "PHENOTYPE")
        if normalized == "clinical":
            return ("PATIENT", "PHENOTYPE", "PUBLICATION")
        return ("SUBJECT", "PHENOTYPE")

    def _bootstrap_variable_id(
        self: _EntityRecognitionBootstrapContext,
        domain_context: str,
    ) -> str:
        normalized = self._normalize_identifier(
            domain_context,
            prefix="GENERAL",
            max_length=48,
        )
        return f"VAR_{normalized}_EVIDENCE_SIGNAL"[:64]

    @staticmethod
    def _bootstrap_review_settings(  # noqa: C901, PLR0912
        settings: ResearchSpaceSettings,
    ) -> ResearchSpaceSettings:
        normalized: ResearchSpaceSettings = {}
        if "auto_approve" in settings:
            normalized["auto_approve"] = settings["auto_approve"]
        if "require_review" in settings:
            normalized["require_review"] = settings["require_review"]
        if "review_threshold" in settings:
            normalized["review_threshold"] = settings["review_threshold"]
        if "relation_default_review_threshold" in settings:
            normalized["relation_default_review_threshold"] = settings[
                "relation_default_review_threshold"
            ]
        relation_governance_mode = settings.get("relation_governance_mode")
        if relation_governance_mode in {"HUMAN_IN_LOOP", "FULL_AUTO"}:
            normalized["relation_governance_mode"] = relation_governance_mode
        relation_review_thresholds = settings.get("relation_review_thresholds")
        if isinstance(relation_review_thresholds, dict):
            normalized["relation_review_thresholds"] = dict(relation_review_thresholds)
        if "max_data_sources" in settings:
            normalized["max_data_sources"] = settings["max_data_sources"]
        if "allowed_source_types" in settings:
            normalized["allowed_source_types"] = settings["allowed_source_types"]
        if "public_read" in settings:
            normalized["public_read"] = settings["public_read"]
        if "allow_invites" in settings:
            normalized["allow_invites"] = settings["allow_invites"]
        if "email_notifications" in settings:
            normalized["email_notifications"] = settings["email_notifications"]
        if "notification_frequency" in settings:
            normalized["notification_frequency"] = settings["notification_frequency"]
        if "custom" in settings and isinstance(settings["custom"], dict):
            normalized["custom"] = dict(settings["custom"])
        # Bootstrap entries are required for immediate kernel writes in the same run.
        # Keep them ACTIVE regardless of space-level agent-creation policy so
        # dictionary hard guarantees and runtime ingestion remain compatible.
        normalized["dictionary_agent_creation_policy"] = "ACTIVE"
        return normalized

    @staticmethod
    def _is_domain_bootstrap_enabled(settings: ResearchSpaceSettings) -> bool:
        custom = settings.get("custom")
        if isinstance(custom, dict):
            explicit = custom.get("dictionary_cold_start_bootstrap")
            if isinstance(explicit, bool):
                return explicit
        return True


__all__ = ["_EntityRecognitionBootstrapHelpers"]
