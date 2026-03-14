"""Biomedical entity-recognition bootstrap content."""

from __future__ import annotations

from src.graph.core.entity_recognition_bootstrap import (
    BootstrapRelationConstraintDefinition,
    BootstrapRelationTypeDefinition,
    BootstrapVariableDefinition,
    DomainBootstrapEntityTypes,
    EntityRecognitionBootstrapConfig,
)

BIOMEDICAL_ENTITY_RECOGNITION_BOOTSTRAP = EntityRecognitionBootstrapConfig(
    default_relation_type="ASSOCIATED_WITH",
    default_relation_display_name="Associated With",
    default_relation_description=(
        "Generic bootstrap relation for domain initialization and cross-entity linkage."
    ),
    default_relation_inverse_label="ASSOCIATED_WITH",
    interaction_relation_type="PHYSICALLY_INTERACTS_WITH",
    interaction_relation_display_name="Physically Interacts With",
    interaction_relation_description=(
        "Physical interaction relation for molecular entities derived from curated evidence."
    ),
    interaction_relation_inverse_label="PHYSICALLY_INTERACTS_WITH",
    min_entity_types_for_default_relation=2,
    interaction_entity_types=("GENE", "PROTEIN"),
    domain_entity_types=(
        DomainBootstrapEntityTypes(
            domain_context="genomics",
            entity_types=("GENE", "PROTEIN", "VARIANT", "PHENOTYPE"),
        ),
        DomainBootstrapEntityTypes(
            domain_context="clinical",
            entity_types=("PATIENT", "PHENOTYPE", "PUBLICATION"),
        ),
        DomainBootstrapEntityTypes(
            domain_context="general",
            entity_types=("SUBJECT", "PHENOTYPE"),
        ),
    ),
    source_types_with_publication_baseline=("pubmed",),
    publication_baseline_source_label="pubmed",
    publication_baseline_entity_description=(
        "PubMed publication-graph bootstrap entity type used for relation validation."
    ),
    publication_baseline_entity_types=(
        "PUBLICATION",
        "AUTHOR",
        "KEYWORD",
        "GENE",
        "PROTEIN",
        "VARIANT",
        "PHENOTYPE",
        "DRUG",
        "MECHANISM",
    ),
    publication_baseline_relation_types=(
        BootstrapRelationTypeDefinition(
            relation_type="MENTIONS",
            display_name="Mentions",
            description="Publication reference relationship for documented entities.",
            is_directional=True,
            inverse_label="MENTIONED_BY",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="SUPPORTS",
            display_name="Supports",
            description="Publication evidence support relationship.",
            is_directional=True,
            inverse_label="SUPPORTED_BY",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="CITES",
            display_name="Cites",
            description="Citation relationship between publications.",
            is_directional=True,
            inverse_label="CITED_BY",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="HAS_AUTHOR",
            display_name="Has Author",
            description="Authorship relationship from publication to author entity.",
            is_directional=True,
            inverse_label="AUTHOR_OF",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="HAS_KEYWORD",
            display_name="Has Keyword",
            description="Keyword tagging relationship from publication to keyword entity.",
            is_directional=True,
            inverse_label="KEYWORD_OF",
        ),
    ),
    publication_baseline_constraints=(
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="GENE",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="PROTEIN",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="VARIANT",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="PHENOTYPE",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="DRUG",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="GENE",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="PROTEIN",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="VARIANT",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="MECHANISM",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="HAS_AUTHOR",
            target_type="AUTHOR",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="HAS_KEYWORD",
            target_type="KEYWORD",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="CITES",
            target_type="PUBLICATION",
            requires_evidence=False,
        ),
    ),
    publication_metadata_variables=(
        BootstrapVariableDefinition(
            variable_id="VAR_PUBLICATION_TITLE",
            canonical_name="publication_title",
            display_name="Publication Title",
            data_type="STRING",
            description="Title of the academic publication.",
            constraints=None,
            synonyms=("title", "paper_title", "publication_title"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_ABSTRACT",
            canonical_name="abstract",
            display_name="Abstract",
            data_type="STRING",
            description="Publication abstract text.",
            constraints=None,
            synonyms=("abstract", "abstract_text"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_PUBLICATION_YEAR",
            canonical_name="publication_year",
            display_name="Publication Year",
            data_type="INTEGER",
            description="Year of publication.",
            constraints={"min": 1900, "max": 2100},
            synonyms=("publication_year", "year", "pub_year"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_PUBLICATION_DATE",
            canonical_name="publication_date",
            display_name="Publication Date",
            data_type="DATE",
            description="Calendar publication date for the article.",
            constraints=None,
            synonyms=("publication_date", "pub_date", "date_published"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_JOURNAL_NAME",
            canonical_name="journal_name",
            display_name="Journal Name",
            data_type="STRING",
            description="Journal of publication.",
            constraints=None,
            synonyms=("journal", "journal_name"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_PUBMED_ID",
            canonical_name="pubmed_id",
            display_name="PubMed ID",
            data_type="STRING",
            description="PubMed stable identifier for a publication.",
            constraints=None,
            synonyms=("pmid", "pubmed_id"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_DOI",
            canonical_name="doi",
            display_name="DOI",
            data_type="STRING",
            description="Digital Object Identifier for a publication.",
            constraints=None,
            synonyms=("doi",),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_KEYWORDS",
            canonical_name="keywords",
            display_name="Keywords",
            data_type="JSON",
            description="Structured keyword list extracted from publication metadata.",
            constraints=None,
            synonyms=("keywords", "keyword_list"),
        ),
    ),
)
