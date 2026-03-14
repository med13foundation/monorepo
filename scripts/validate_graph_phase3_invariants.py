"""Validate that domain packs cannot override graph-core invariants."""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from src.graph.core.domain_pack import GraphDomainPack

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_INVARIANT_OWNER_FILES = (
    PROJECT_ROOT
    / "src/application/services/kernel/kernel_relation_projection_materialization_service.py",
    PROJECT_ROOT
    / "src/application/services/kernel/kernel_relation_projection_invariant_service.py",
    PROJECT_ROOT
    / "src/application/services/kernel/kernel_claim_projection_readiness_service.py",
    PROJECT_ROOT / "src/application/services/kernel/kernel_reasoning_path_service.py",
)

_FORBIDDEN_IMPORT_PREFIXES = (
    "src.graph.runtime",
    "src.graph.pack_registry",
    "src.graph.domain_",
)

_FORBIDDEN_PACK_FIELD_FRAGMENTS = (
    "projection",
    "materialization",
    "invariant",
)


def _import_targets(module: ast.AST) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            targets.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            targets.append((node.lineno, node.module))
    return targets


def _validate_invariant_owner_imports() -> list[str]:
    errors: list[str] = []
    for path in _INVARIANT_OWNER_FILES:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, target in _import_targets(module):
            if target.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                errors.append(f"{path}:{lineno}: forbidden invariant import '{target}'")
    return errors


def _validate_graph_domain_pack_contract() -> list[str]:
    errors: list[str] = []
    for field in fields(GraphDomainPack):
        normalized_name = field.name.lower()
        if any(
            fragment in normalized_name for fragment in _FORBIDDEN_PACK_FIELD_FRAGMENTS
        ):
            errors.append(
                "GraphDomainPack field "
                f"'{field.name}' suggests pack-level override of core invariant/projection logic",
            )
    return errors


def main() -> int:
    errors = [
        *_validate_invariant_owner_imports(),
        *_validate_graph_domain_pack_contract(),
    ]
    if errors:
        print("graph_phase3_invariants: error")
        for error in errors:
            print(f" - {error}")
        return 1

    print("graph_phase3_invariants: ok")
    for path in _INVARIANT_OWNER_FILES:
        print(f"graph_phase3_invariants: checked {path.relative_to(PROJECT_ROOT)}")
    print("graph_phase3_invariants: GraphDomainPack override surface is clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
