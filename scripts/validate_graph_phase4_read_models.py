"""Validate graph-core read-model ownership and truth-source rules."""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from src.graph.core.domain_pack import GraphDomainPack
from src.graph.core.read_model import (
    CORE_GRAPH_READ_MODELS,
    GraphReadModelOwner,
    GraphReadModelTrigger,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
READ_MODEL_MODULE = PROJECT_ROOT / "src/graph/core/read_model.py"

_FORBIDDEN_IMPORT_PREFIXES = (
    "src.graph.runtime",
    "src.graph.pack_registry",
    "src.graph.domain_",
)

_CORE_READ_MODEL_NAMES = frozenset(
    definition.name for definition in CORE_GRAPH_READ_MODELS
)


def _import_targets(module: ast.AST) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            targets.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            targets.append((node.lineno, node.module))
    return targets


def _validate_read_model_module_imports() -> list[str]:
    errors: list[str] = []
    module = ast.parse(READ_MODEL_MODULE.read_text(encoding="utf-8"))
    for lineno, target in _import_targets(module):
        if target.startswith(_FORBIDDEN_IMPORT_PREFIXES):
            errors.append(
                f"{READ_MODEL_MODULE}:{lineno}: forbidden read-model import '{target}'",
            )
    return errors


def _validate_core_read_model_catalog() -> list[str]:
    errors: list[str] = []
    expected_names = {
        "entity_neighbors",
        "entity_relation_summary",
        "entity_claim_summary",
        "entity_mechanism_paths",
    }
    if expected_names != _CORE_READ_MODEL_NAMES:
        errors.append(
            "Core read-model catalog mismatch: "
            f"expected {sorted(expected_names)}, got {sorted(_CORE_READ_MODEL_NAMES)}",
        )

    for definition in CORE_GRAPH_READ_MODELS:
        if definition.owner != GraphReadModelOwner.GRAPH_CORE:
            errors.append(
                f"Core read model '{definition.name}' is not owned by graph-core",
            )
        if definition.is_truth_source:
            errors.append(
                f"Core read model '{definition.name}' must not be a truth source",
            )
        if GraphReadModelTrigger.FULL_REBUILD not in definition.triggers:
            errors.append(
                f"Core read model '{definition.name}' must support full rebuild",
            )
    return errors


def _validate_graph_domain_pack_contract() -> list[str]:
    errors: list[str] = []
    normalized_fields = {field.name.lower() for field in fields(GraphDomainPack)}
    overlap = _CORE_READ_MODEL_NAMES.intersection(normalized_fields)
    if overlap:
        errors.append(
            "GraphDomainPack exposes graph-core read-model names directly: "
            f"{sorted(overlap)}",
        )
    return errors


def main() -> int:
    errors = [
        *_validate_read_model_module_imports(),
        *_validate_core_read_model_catalog(),
        *_validate_graph_domain_pack_contract(),
    ]
    if errors:
        print("graph_phase4_read_models: error")
        for error in errors:
            print(f" - {error}")
        return 1

    print("graph_phase4_read_models: ok")
    print("graph_phase4_read_models: graph-core catalog owns generic read models")
    print(
        "graph_phase4_read_models: read models remain derived, rebuildable, non-truth surfaces",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
