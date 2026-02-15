"""Cold-start dictionary bootstrap helpers for entity-recognition orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domain.ports.dictionary_port import DictionaryPort
    from src.type_definitions.common import ResearchSpaceSettings

_DEFAULT_BOOTSTRAP_RELATION_TYPE = "ASSOCIATED_WITH"
_MIN_BOOTSTRAP_ENTITY_TYPES_FOR_RELATION = 2


class _EntityRecognitionBootstrapHelpers:
    """Mixin with domain cold-start bootstrap support."""

    def _ensure_domain_bootstrap(  # noqa: PLR0913
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
        existing = self._dictionary.dictionary_search_by_domain(
            domain_context=domain_context,
            limit=1,
            include_inactive=False,
        )
        if existing:
            return 0, 0

        created_entity_types = 0
        for entity_type_id in self._bootstrap_entity_types_for_domain(domain_context):
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
        if self._dictionary.get_variable(bootstrap_variable_id) is None:
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

        if self._dictionary.get_relation_type(_DEFAULT_BOOTSTRAP_RELATION_TYPE) is None:
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

        entity_types = self._bootstrap_entity_types_for_domain(domain_context)
        if len(entity_types) >= _MIN_BOOTSTRAP_ENTITY_TYPES_FOR_RELATION:
            self._ensure_relation_constraint(
                source_type=entity_types[0],
                target_type=entity_types[1],
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
        constraints = self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=_DEFAULT_BOOTSTRAP_RELATION_TYPE,
            include_inactive=False,
        )
        if any(constraint.target_type == target_type for constraint in constraints):
            return
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

    @staticmethod
    def _bootstrap_entity_types_for_domain(domain_context: str) -> tuple[str, ...]:
        normalized = domain_context.strip().lower()
        if normalized == "genomics":
            return ("GENE", "VARIANT", "PHENOTYPE")
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
    def _bootstrap_review_settings(  # noqa: C901
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
