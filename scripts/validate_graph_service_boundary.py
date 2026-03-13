#!/usr/bin/env python3
"""Validate that graph internals stay behind the standalone service boundary."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_IMPORT_PREFIXES = (
    "src.application.services.kernel",
    "src.infrastructure.repositories.kernel",
    "src.models.database.kernel",
)
FORBIDDEN_SERVICE_IMPORT_PREFIX = "services.graph_api"

ALLOWED_PREFIXES = (
    "services/graph_api/",
    "src/application/services/kernel/",
    "src/database/graph_schema.py",
    "src/infrastructure/dependency_injection/graph_runtime_factories.py",
    "src/infrastructure/graph_governance/",
    "src/infrastructure/queries/graph_security_queries.py",
    "src/infrastructure/repositories/graph_observability_repository.py",
    "src/infrastructure/repositories/kernel/",
    "src/models/database/kernel/",
)

LEGACY_ALLOWLIST = frozenset()


@dataclass(frozen=True)
class BoundaryViolation:
    file_path: str
    line_number: int
    imported_module: str


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


def _is_allowed_file(relative_path: str) -> bool:
    return relative_path in LEGACY_ALLOWLIST or relative_path.startswith(
        ALLOWED_PREFIXES,
    )


def _find_violations() -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    for file_path in SRC_ROOT.rglob("*.py"):
        relative_path = str(file_path.relative_to(REPO_ROOT))
        if _is_allowed_file(relative_path):
            continue

        try:
            tree = ast.parse(
                file_path.read_text(encoding="utf-8"),
                filename=str(file_path),
            )
        except SyntaxError:
            continue

        parent_by_child = _build_parent_lookup(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            if _is_type_checking_import(node=node, parent_by_child=parent_by_child):
                continue
            violations.extend(
                BoundaryViolation(
                    file_path=relative_path,
                    line_number=getattr(node, "lineno", 0),
                    imported_module=module_name,
                )
                for module_name in _extract_import_modules(node)
                if module_name.startswith(FORBIDDEN_IMPORT_PREFIXES)
            )
            violations.extend(
                BoundaryViolation(
                    file_path=relative_path,
                    line_number=getattr(node, "lineno", 0),
                    imported_module=module_name,
                )
                for module_name in _extract_import_modules(node)
                if module_name.startswith(FORBIDDEN_SERVICE_IMPORT_PREFIX)
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
    violations = _find_violations()
    if not violations:
        print("graph_boundary: ok")
        return 0

    print("graph_boundary: error")
    print("Direct graph-internal imports are only allowed in the standalone service")
    print("and the explicit legacy allowlist while extraction is still in progress.")
    for violation in violations:
        print(
            f"{violation.file_path}:{violation.line_number}: error: "
            f"graph_boundary: imports {violation.imported_module}",
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
