"""Cold-start dictionary bootstrap helpers for entity-recognition orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import ResearchSpaceSettings

_DEFAULT_BOOTSTRAP_RELATION_TYPE = "ASSOCIATED_WITH"
_DEFAULT_INTERACTION_RELATION_TYPE = "PHYSICALLY_INTERACTS_WITH"
_MIN_BOOTSTRAP_ENTITY_TYPES_FOR_RELATION = 2
_PUBMED_PUBLICATION_BASELINE_ENTITY_TYPES: tuple[str, ...] = (
    "PUBLICATION",
    "AUTHOR",
    "KEYWORD",
    "GENE",
    "PROTEIN",
    "VARIANT",
    "PHENOTYPE",
    "DRUG",
    "MECHANISM",
)
_PUBMED_PUBLICATION_BASELINE_RELATION_TYPES: tuple[
    tuple[str, str, str, bool, str | None],
    ...,
] = (
    (
        "MENTIONS",
        "Mentions",
        "Publication reference relationship for documented entities.",
        True,
        "MENTIONED_BY",
    ),
    (
        "SUPPORTS",
        "Supports",
        "Publication evidence support relationship.",
        True,
        "SUPPORTED_BY",
    ),
    (
        "CITES",
        "Cites",
        "Citation relationship between publications.",
        True,
        "CITED_BY",
    ),
    (
        "HAS_AUTHOR",
        "Has Author",
        "Authorship relationship from publication to author entity.",
        True,
        "AUTHOR_OF",
    ),
    (
        "HAS_KEYWORD",
        "Has Keyword",
        "Keyword tagging relationship from publication to keyword entity.",
        True,
        "KEYWORD_OF",
    ),
)
_PUBMED_PUBLICATION_BASELINE_CONSTRAINTS: tuple[tuple[str, str, str, bool], ...] = (
    ("PUBLICATION", "MENTIONS", "GENE", False),
    ("PUBLICATION", "MENTIONS", "PROTEIN", False),
    ("PUBLICATION", "MENTIONS", "VARIANT", False),
    ("PUBLICATION", "MENTIONS", "PHENOTYPE", False),
    ("PUBLICATION", "MENTIONS", "DRUG", False),
    ("PUBLICATION", "SUPPORTS", "GENE", False),
    ("PUBLICATION", "SUPPORTS", "PROTEIN", False),
    ("PUBLICATION", "SUPPORTS", "VARIANT", False),
    ("PUBLICATION", "SUPPORTS", "MECHANISM", False),
    ("PUBLICATION", "HAS_AUTHOR", "AUTHOR", False),
    ("PUBLICATION", "HAS_KEYWORD", "KEYWORD", False),
    ("PUBLICATION", "CITES", "PUBLICATION", False),
)


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

        if source_type.strip().lower() == "pubmed":
            created_entity_types += self._ensure_pubmed_publication_baseline(
                domain_context=domain_context,
                source_ref=source_ref,
                research_space_settings=bootstrap_review_settings,
            )

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
    ) -> int:
        created_entity_types = 0

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

        return created_entity_types

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
        creation_policy = settings.get("dictionary_agent_creation_policy")
        if isinstance(creation_policy, str):
            normalized_policy = creation_policy.strip().upper()
            if normalized_policy == "ACTIVE":
                normalized["dictionary_agent_creation_policy"] = "ACTIVE"
            elif normalized_policy == "PENDING_REVIEW":
                normalized["dictionary_agent_creation_policy"] = "PENDING_REVIEW"
            else:
                normalized["dictionary_agent_creation_policy"] = "PENDING_REVIEW"
        else:
            normalized["dictionary_agent_creation_policy"] = "PENDING_REVIEW"
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


class _EntityRecognitionBootstrapContext(Protocol):
    """Structural typing contract consumed by bootstrap helper methods."""

    _dictionary: DictionaryPort
    _agent_created_by: str

    @staticmethod
    def _infer_domain_context(source_type: str) -> str: ...

    @staticmethod
    def _to_display_name(field_name: str) -> str: ...

    @staticmethod
    def _normalize_identifier(
        value: str,
        *,
        prefix: str,
        max_length: int,
    ) -> str: ...

    @staticmethod
    def _is_domain_bootstrap_enabled(settings: ResearchSpaceSettings) -> bool: ...

    @staticmethod
    def _bootstrap_entity_types_for_domain(domain_context: str) -> tuple[str, ...]: ...

    @staticmethod
    def _bootstrap_review_settings(
        settings: ResearchSpaceSettings,
    ) -> ResearchSpaceSettings: ...

    def _bootstrap_variable_id(self, domain_context: str) -> str: ...

    def _ensure_relation_constraint(
        self,
        *,
        source_type: str,
        target_type: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> None: ...

    def _ensure_relation_constraint_for_type(
        self,
        *,
        relation_triplet: tuple[str, str, str],
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
        requires_evidence: bool = True,
    ) -> None: ...

    def _ensure_pubmed_publication_baseline(
        self,
        *,
        domain_context: str,
        source_ref: str,
        research_space_settings: ResearchSpaceSettings,
    ) -> int: ...
