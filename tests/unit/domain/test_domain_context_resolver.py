"""Unit tests for shared domain-context resolution rules."""

from src.domain.services.domain_context_resolver import DomainContextResolver


def test_resolve_prefers_explicit_domain_context() -> None:
    resolved = DomainContextResolver.resolve(
        explicit_domain_context="  Cardiology  ",
        metadata={"domain_context": "genomics"},
        source_type="pubmed",
        fallback="general",
    )

    assert resolved == "cardiology"


def test_resolve_uses_metadata_when_explicit_missing() -> None:
    resolved = DomainContextResolver.resolve(
        metadata={"domain": " Clinical "},
        source_type="clinvar",
        fallback="general",
    )

    assert resolved == "clinical"


def test_resolve_uses_source_type_default_when_metadata_missing() -> None:
    resolved = DomainContextResolver.resolve(
        source_type="pubmed",
        fallback=None,
    )

    assert resolved == "clinical"


def test_resolve_uses_fallback_for_unknown_source_type() -> None:
    resolved = DomainContextResolver.resolve(
        source_type="custom_source",
        fallback="general",
    )

    assert resolved == "general"


def test_resolve_uses_ai_inference_before_fallback() -> None:
    resolved = DomainContextResolver.resolve(
        source_type="custom_source",
        ai_inference=lambda: " Clinical ",
        fallback="general",
    )

    assert resolved == "clinical"
