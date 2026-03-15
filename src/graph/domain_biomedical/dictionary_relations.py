"""Biomedical built-in relation catalog for graph dictionary startup."""

from __future__ import annotations

from src.graph.core.dictionary_loading_extension import (
    BuiltinRelationSynonymDefinition,
    BuiltinRelationTypeDefinition,
)

BIOMEDICAL_CORE_CAUSAL_RELATION_TYPES = (
    BuiltinRelationTypeDefinition(
        relation_type="ASSOCIATED_WITH",
        display_name="Associated With",
        description="Generic biomedical association between two entities.",
        domain_context="general",
        category="core_causal",
        is_directional=True,
        inverse_label="ASSOCIATED_WITH",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="CAUSES",
        display_name="Causes",
        description="Directional causal relationship between biomedical entities.",
        domain_context="clinical",
        category="core_causal",
        is_directional=True,
        inverse_label="CAUSED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="TREATS",
        display_name="Treats",
        description="Therapeutic relationship from an intervention to a condition.",
        domain_context="clinical",
        category="core_causal",
        is_directional=True,
        inverse_label="TREATED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="TARGETS",
        display_name="Targets",
        description="Directed targeting relationship between an intervention and a molecular entity.",
        domain_context="genomics",
        category="core_causal",
        is_directional=True,
        inverse_label="TARGETED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="BIOMARKER_FOR",
        display_name="Biomarker For",
        description="Biomarker relationship linking a measurable signal to a condition or mechanism.",
        domain_context="clinical",
        category="core_causal",
        is_directional=True,
        inverse_label="HAS_BIOMARKER",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="PHYSICALLY_INTERACTS_WITH",
        display_name="Physically Interacts With",
        description="Physical interaction relationship between molecular entities.",
        domain_context="genomics",
        category="core_causal",
        is_directional=False,
        inverse_label="PHYSICALLY_INTERACTS_WITH",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="ACTIVATES",
        display_name="Activates",
        description="Positive regulatory relationship between biomedical entities.",
        domain_context="genomics",
        category="core_causal",
        is_directional=True,
        inverse_label="ACTIVATED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="INHIBITS",
        display_name="Inhibits",
        description="Negative regulatory relationship between biomedical entities.",
        domain_context="genomics",
        category="core_causal",
        is_directional=True,
        inverse_label="INHIBITED_BY",
    ),
)

BIOMEDICAL_EXTENDED_SCIENTIFIC_RELATION_TYPES = (
    BuiltinRelationTypeDefinition(
        relation_type="UPSTREAM_OF",
        display_name="Upstream Of",
        description="Mechanistic ordering relationship for pathway and causal chains.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="DOWNSTREAM_OF",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="DOWNSTREAM_OF",
        display_name="Downstream Of",
        description="Mechanistic ordering relationship inverse to UPSTREAM_OF.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="UPSTREAM_OF",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="PART_OF",
        display_name="Part Of",
        description="Compositional relationship between biomedical structures or mechanisms.",
        domain_context="general",
        category="extended_scientific",
        is_directional=True,
        inverse_label="HAS_PART",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="EXPRESSED_IN",
        display_name="Expressed In",
        description="Expression relationship from a molecular entity to a tissue or cell context.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="EXPRESSES",
    ),
)

BIOMEDICAL_DOCUMENT_GOVERNANCE_RELATION_TYPES = (
    BuiltinRelationTypeDefinition(
        relation_type="SUPPORTS",
        display_name="Supports",
        description="Evidence-bearing support relationship used in claims and publication views.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="SUPPORTED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="REFINES",
        display_name="Refines",
        description="Relationship indicating a more specific statement or mechanism.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="REFINED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="GENERALIZES",
        display_name="Generalizes",
        description="Relationship indicating a more general statement or abstraction.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="SPECIALIZED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="INSTANCE_OF",
        display_name="Instance Of",
        description="Relationship linking a specific instance to a more general class.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="HAS_INSTANCE",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="MENTIONS",
        display_name="Mentions",
        description="Publication mention relationship for documented entities.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="MENTIONED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="CITES",
        display_name="Cites",
        description="Citation relationship between publications.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="CITED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="HAS_AUTHOR",
        display_name="Has Author",
        description="Authorship relationship from a publication to an author entity.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="AUTHOR_OF",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="HAS_KEYWORD",
        display_name="Has Keyword",
        description="Keyword tagging relationship from a publication to a keyword entity.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="KEYWORD_OF",
    ),
)

BIOMEDICAL_BUILTIN_RELATION_TYPES = (
    *BIOMEDICAL_CORE_CAUSAL_RELATION_TYPES,
    *BIOMEDICAL_EXTENDED_SCIENTIFIC_RELATION_TYPES,
    *BIOMEDICAL_DOCUMENT_GOVERNANCE_RELATION_TYPES,
)

BIOMEDICAL_BUILTIN_RELATION_SYNONYMS = (
    BuiltinRelationSynonymDefinition(
        relation_type="ASSOCIATED_WITH",
        synonym="ASSOCIATES_WITH",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="ASSOCIATED_WITH",
        synonym="LINKED_TO",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="ASSOCIATED_WITH",
        synonym="CORRELATED_WITH",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="CAUSES",
        synonym="LEADS_TO",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="CAUSES",
        synonym="RESULTS_IN",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="TREATS",
        synonym="THERAPEUTIC_FOR",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="TARGETS",
        synonym="ACTS_ON",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="PHYSICALLY_INTERACTS_WITH",
        synonym="INTERACTS_WITH",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="ACTIVATES",
        synonym="STIMULATES",
        source="biomedical_pack",
    ),
    BuiltinRelationSynonymDefinition(
        relation_type="INHIBITS",
        synonym="SUPPRESSES",
        source="biomedical_pack",
    ),
)
