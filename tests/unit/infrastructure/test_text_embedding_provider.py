"""Tests for embedding provider environment mode resolution."""

from __future__ import annotations

from src.infrastructure.embeddings.text_embedding_provider import (
    HybridTextEmbeddingProvider,
)


def test_strict_mode_defaults_off_in_testing(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.delenv("MED13_AI_STRICT_MODE", raising=False)
    monkeypatch.delenv("MED13_EMBEDDING_STRICT_MODE", raising=False)

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is False


def test_strict_mode_defaults_on_outside_testing(monkeypatch) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("MED13_AI_STRICT_MODE", raising=False)
    monkeypatch.delenv("MED13_EMBEDDING_STRICT_MODE", raising=False)

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is True


def test_primary_strict_env_overrides_legacy_and_testing(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("MED13_AI_STRICT_MODE", "true")
    monkeypatch.setenv("MED13_EMBEDDING_STRICT_MODE", "false")

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is True


def test_legacy_strict_env_applies_when_primary_missing(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "false")
    monkeypatch.delenv("MED13_AI_STRICT_MODE", raising=False)
    monkeypatch.setenv("MED13_EMBEDDING_STRICT_MODE", "false")

    provider = HybridTextEmbeddingProvider()

    assert provider._strict_ai_mode is False
