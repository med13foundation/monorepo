"""Unit tests for graph domain-pack wiring."""

from __future__ import annotations

from src.graph.domain_biomedical.pack import get_biomedical_graph_domain_pack
from src.graph.domain_sports.pack import get_sports_graph_domain_pack


def test_biomedical_graph_domain_pack_exposes_view_extension() -> None:
    pack = get_biomedical_graph_domain_pack()

    assert pack.name == "biomedical"
    assert pack.runtime_identity.service_name == "Biomedical Graph Service"
    assert pack.runtime_identity.jwt_issuer == "graph-biomedical"
    assert pack.view_extension.normalize_view_type("gene") == "gene"
    assert pack.view_extension.entity_view_types["variant"] == "VARIANT"
    assert tuple(
        context.id
        for context in pack.dictionary_loading_extension.builtin_domain_contexts
    ) == (
        "general",
        "clinical",
        "genomics",
    )
    assert tuple(context.id for context in pack.dictionary_domain_contexts) == (
        "general",
        "clinical",
        "genomics",
    )
    assert {
        definition.source_type: definition.domain_context
        for definition in pack.domain_context_policy.source_type_defaults
    } == {
        "pubmed": "clinical",
        "clinvar": "genomics",
    }
    assert pack.entity_recognition_bootstrap.default_relation_type == "ASSOCIATED_WITH"
    assert pack.entity_recognition_bootstrap.interaction_relation_type == (
        "PHYSICALLY_INTERACTS_WITH"
    )
    assert (
        pack.entity_recognition_fallback.field_keys_for("clinvar", "variant")[0]
        == "clinvar_id"
    )
    assert (
        pack.entity_recognition_fallback.primary_entity_type_for("pubmed")
        == "PUBLICATION"
    )
    assert (
        pack.entity_recognition_payload.compact_record_rule_for("pubmed").fields[0]
        == "pubmed_id"
    )
    assert pack.entity_recognition_payload.compact_record_rule_for(
        "pubmed",
    ).preferred_text_fields == ("full_text", "abstract")
    assert pack.entity_recognition_prompt.supported_source_types() == frozenset(
        {"clinvar", "pubmed"},
    )
    assert "PubMed publications" in pack.entity_recognition_prompt.system_prompt_for(
        "pubmed",
    )
    assert pack.extraction_prompt.supported_source_types() == frozenset(
        {"clinvar", "pubmed"},
    )
    assert "ClinVar records" in pack.extraction_prompt.system_prompt_for("clinvar")
    assert pack.extraction_payload.compact_record_rule_for("pubmed") is not None
    assert (
        pack.extraction_payload.compact_record_rule_for("pubmed").chunk_indicator_field
        == "full_text_chunk_index"
    )
    assert (
        pack.extraction_payload.compact_record_rule_for("clinvar").fields[0]
        == "variation_id"
    )
    assert pack.graph_connection_prompt.supported_source_types() == frozenset(
        {"clinvar", "pubmed"},
    )
    assert pack.graph_connection_prompt.default_source_type == "clinvar"
    assert pack.graph_connection_prompt.step_key_for("pubmed") == (
        "graph.connection.pubmed.v1"
    )
    assert pack.search_extension.step_key == "graph.search.v1"
    assert "MED13 Graph Search Agent" in pack.search_extension.system_prompt
    assert pack.relation_suggestion_extension.vector_candidate_limit == 100
    assert pack.relation_suggestion_extension.min_vector_similarity == 0.0
    assert (
        "PubMed-backed research spaces"
        in pack.graph_connection_prompt.system_prompt_for("pubmed")
    )
    assert (
        pack.extraction_fallback.relation_when_variant_and_phenotype_present.source_type
        == "VARIANT"
    )
    assert pack.extraction_fallback.claim_text_fields[0] == "abstract"
    assert pack.entity_recognition_bootstrap.source_types_with_publication_baseline == (
        "pubmed",
    )
    assert pack.entity_recognition_bootstrap.publication_baseline_source_label == (
        "pubmed"
    )
    assert pack.entity_recognition_bootstrap.publication_baseline_entity_types[0] == (
        "PUBLICATION"
    )
    assert pack.relation_autopromotion_defaults.min_distinct_sources == 3
    assert pack.relation_autopromotion_defaults.min_aggregate_confidence == 0.95
    assert (
        pack.dictionary_domain_contexts[1].description
        == "Clinical and biomedical literature domain context."
    )


def test_sports_graph_domain_pack_exposes_view_extension() -> None:
    pack = get_sports_graph_domain_pack()

    assert pack.name == "sports"
    assert pack.runtime_identity.service_name == "Sports Graph Service"
    assert pack.runtime_identity.jwt_issuer == "graph-sports"
    assert pack.view_extension.normalize_view_type("team") == "team"
    assert pack.view_extension.entity_view_types["athlete"] == "ATHLETE"
    assert tuple(
        context.id
        for context in pack.dictionary_loading_extension.builtin_domain_contexts
    ) == ("general", "competition", "roster")
    assert {
        definition.source_type: definition.domain_context
        for definition in pack.domain_context_policy.source_type_defaults
    } == {
        "match_report": "competition",
        "player_profile": "roster",
        "box_score": "competition",
    }
    assert pack.entity_recognition_bootstrap.interaction_relation_type == (
        "COMPETES_AGAINST"
    )
    assert (
        pack.entity_recognition_fallback.field_keys_for("match_report", "team")[0]
        == "home_team"
    )
    assert (
        pack.entity_recognition_payload.compact_record_rule_for(
            "player_profile",
        ).fields[0]
        == "player_id"
    )
    assert pack.entity_recognition_prompt.supported_source_types() == frozenset(
        {"match_report", "player_profile"},
    )
    assert "sports claims" in pack.extraction_prompt.system_prompt_for("match_report")
    assert pack.graph_connection_prompt.default_source_type == "match_report"
    assert pack.graph_connection_prompt.step_key_for("match_report") == (
        "graph.connection.sports.match_report.v1"
    )
    assert pack.search_extension.step_key == "graph.search.sports.v1"
    assert pack.relation_suggestion_extension.vector_candidate_limit == 75
    assert pack.relation_autopromotion_defaults.min_distinct_sources == 2
