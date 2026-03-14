"""Validate explicit cross-domain proof for built-in graph domain packs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE_PATH = PROJECT_ROOT / "Makefile"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

os.environ.setdefault(
    "GRAPH_DATABASE_URL",
    "postgresql://graph-cross-domain:graph-cross-domain@localhost:5432/graph_cross_domain",
)

from src.graph.core.service_config import get_graph_service_settings
from src.graph.pack_registry import (
    get_registered_graph_domain_packs,
    resolve_graph_domain_pack,
)

_MATRIX_DOC = PROJECT_ROOT / "docs/graph/reference/cross-domain-validation-matrix.md"
_REQUIRED_PACKS = ("biomedical", "sports")


def _validate_registered_packs() -> list[str]:
    packs = get_registered_graph_domain_packs()
    return [
        f"Missing built-in graph domain pack: {pack_name}"
        for pack_name in _REQUIRED_PACKS
        if pack_name not in packs
    ]


def _validate_pack_runtime_identity() -> list[str]:
    errors: list[str] = []
    original_pack = os.environ.get("GRAPH_DOMAIN_PACK")
    expected_identity = {
        "biomedical": ("Biomedical Graph Service", "graph-biomedical"),
        "sports": ("Sports Graph Service", "graph-sports"),
    }
    try:
        for pack_name, (service_name, issuer) in expected_identity.items():
            os.environ["GRAPH_DOMAIN_PACK"] = pack_name
            resolved_pack = resolve_graph_domain_pack()
            settings = get_graph_service_settings()
            if resolved_pack.name != pack_name:
                errors.append(
                    f"Resolved graph domain pack mismatch for {pack_name!r}: {resolved_pack.name!r}",
                )
            if settings.app_name != service_name:
                errors.append(
                    f"Service name mismatch for {pack_name!r}: {settings.app_name!r} != {service_name!r}",
                )
            if settings.jwt_issuer != issuer:
                errors.append(
                    f"JWT issuer mismatch for {pack_name!r}: {settings.jwt_issuer!r} != {issuer!r}",
                )
    finally:
        if original_pack is None:
            os.environ.pop("GRAPH_DOMAIN_PACK", None)
        else:
            os.environ["GRAPH_DOMAIN_PACK"] = original_pack
    return errors


def _validate_matrix_doc() -> list[str]:
    if not _MATRIX_DOC.exists():
        return [f"Missing cross-domain validation matrix: {_MATRIX_DOC}"]
    contents = _MATRIX_DOC.read_text(encoding="utf-8")
    required_markers = (
        "# Graph Cross-Domain Validation Matrix",
        "biomedical",
        "sports",
        "graph-phase7-cross-domain-check",
        "match_report",
        "competition",
    )
    return [
        f"Cross-domain validation matrix is missing marker {marker!r}"
        for marker in required_markers
        if marker not in contents
    ]


def _validate_make_target() -> list[str]:
    contents = MAKEFILE_PATH.read_text(encoding="utf-8")
    if "graph-phase7-cross-domain-check:" in contents:
        return []
    return [
        "Missing Make target for cross-domain proof: graph-phase7-cross-domain-check",
    ]


def main() -> int:
    errors = [
        *_validate_registered_packs(),
        *_validate_pack_runtime_identity(),
        *_validate_matrix_doc(),
        *_validate_make_target(),
    ]
    if errors:
        print("graph_phase7_cross_domain: error")
        for error in errors:
            print(f" - {error}")
        return 1

    print("graph_phase7_cross_domain: ok")
    print(
        "graph_phase7_cross_domain: built-in biomedical and sports packs resolve through shared runtime boundaries",
    )
    print("graph_phase7_cross_domain: validation matrix and make target are present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
