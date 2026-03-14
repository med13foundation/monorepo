#!/usr/bin/env python3
"""Validate phase-2 graph-core versus domain-pack import boundaries."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPH_ROOT = REPO_ROOT / "src" / "graph"
CORE_ROOT = GRAPH_ROOT / "core"
BIOMEDICAL_ROOT = GRAPH_ROOT / "domain_biomedical"

CORE_FORBIDDEN_IMPORT_PREFIXES = (
    "src.graph.domain_biomedical",
    "services.graph_api",
)


@dataclass(frozen=True)
class BoundaryViolation:
    file_path: str
    line_number: int
    imported_module: str
    rule_name: str


def _is_type_checking_guard(test_node: ast.expr) -> bool:
    return (isinstance(test_node, ast.Name) and test_node.id == "TYPE_CHECKING") or (
        isinstance(test_node, ast.Attribute)
        and isinstance(test_node.value, ast.Name)
        and test_node.value.id == "typing"
        and test_node.attr == "TYPE_CHECKING"
    )


def _build_parent_lookup(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parent_by_child: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_by_child[child] = parent
    return parent_by_child


def _is_type_checking_import(
    *,
    node: ast.AST,
    parent_by_child: dict[ast.AST, ast.AST],
) -> bool:
    current = parent_by_child.get(node)
    while current is not None:
        if isinstance(current, ast.If) and _is_type_checking_guard(current.test):
            return True
        current = parent_by_child.get(current)
    return False


def _extract_import_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.ImportFrom):
        if node.module is None:
            return []
        return [node.module]
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return []


def _find_core_boundary_violations() -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    if not CORE_ROOT.exists():
        return violations

    for file_path in CORE_ROOT.rglob("*.py"):
        relative_path = str(file_path.relative_to(REPO_ROOT))
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        parent_by_child = _build_parent_lookup(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            if _is_type_checking_import(node=node, parent_by_child=parent_by_child):
                continue
            imported_modules = _extract_import_modules(node)
            violations.extend(
                BoundaryViolation(
                    file_path=relative_path,
                    line_number=getattr(node, "lineno", 0),
                    imported_module=module_name,
                    rule_name="core_must_not_depend_on_domain_pack_or_service",
                )
                for module_name in imported_modules
                if module_name.startswith(CORE_FORBIDDEN_IMPORT_PREFIXES)
            )

    return sorted(
        violations,
        key=lambda violation: (
            violation.file_path,
            violation.line_number,
            violation.imported_module,
        ),
    )


def main() -> int:
    if not GRAPH_ROOT.exists():
        print("graph_phase2_boundary: ok (src/graph not present)")
        return 0

    violations = _find_core_boundary_violations()
    if not violations:
        print("graph_phase2_boundary: ok")
        print(f"graph_phase2_boundary: core_root={CORE_ROOT.relative_to(REPO_ROOT)}")
        print(
            "graph_phase2_boundary: allowed direction is "
            "src.graph.domain_biomedical -> src.graph.core",
        )
        if BIOMEDICAL_ROOT.exists():
            print(
                "graph_phase2_boundary: biomedical_root="
                f"{BIOMEDICAL_ROOT.relative_to(REPO_ROOT)}",
            )
        return 0

    print("graph_phase2_boundary: error")
    print("Graph core must remain independent of domain packs and service runtime.")
    for violation in violations:
        print(
            f"{violation.file_path}:{violation.line_number}: error: "
            f"{violation.rule_name}: imports {violation.imported_module}",
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
