"""Unit tests for graph domain-pack registration and resolution."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.graph.core.pack_registration import InMemoryGraphDomainPackRegistry
from src.graph.domain_sports.pack import get_sports_graph_domain_pack
from src.graph.pack_registry import (
    bootstrap_default_graph_domain_packs,
    get_graph_domain_pack_registry,
    get_registered_graph_domain_packs,
    register_graph_domain_pack,
    resolve_graph_domain_pack,
)


def test_registered_graph_domain_packs_include_biomedical() -> None:
    packs = get_registered_graph_domain_packs()

    assert "biomedical" in packs
    assert packs["biomedical"].name == "biomedical"
    assert "sports" in packs
    assert packs["sports"].name == "sports"


def test_bootstrap_default_graph_domain_packs_registers_builtin_packs() -> None:
    registry = InMemoryGraphDomainPackRegistry()

    bootstrap_default_graph_domain_packs(registry=registry)

    assert registry.resolve("biomedical") is not None
    assert registry.resolve("sports") is not None


def test_register_graph_domain_pack_supports_explicit_registry() -> None:
    registry = InMemoryGraphDomainPackRegistry()
    sports_pack = replace(get_sports_graph_domain_pack(), name="sports-alt")

    register_graph_domain_pack(sports_pack, registry=registry)

    resolved = registry.resolve("sports-alt")
    assert resolved is not None
    assert resolved.name == "sports-alt"


def test_resolve_graph_domain_pack_defaults_to_biomedical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_DOMAIN_PACK", raising=False)

    pack = resolve_graph_domain_pack()

    assert pack.name == "biomedical"


def test_resolve_graph_domain_pack_supports_explicit_biomedical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")

    pack = resolve_graph_domain_pack()

    assert pack.name == "biomedical"


def test_resolve_graph_domain_pack_supports_explicit_sports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")

    pack = resolve_graph_domain_pack()

    assert pack.name == "sports"


def test_resolve_graph_domain_pack_rejects_unknown_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "unknown")

    with pytest.raises(RuntimeError, match="Unsupported GRAPH_DOMAIN_PACK"):
        resolve_graph_domain_pack()


def test_global_graph_domain_pack_registry_is_available() -> None:
    registry = get_graph_domain_pack_registry()

    assert registry is not None
