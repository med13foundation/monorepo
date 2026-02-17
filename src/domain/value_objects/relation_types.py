"""Canonical relation-type normalization helpers."""

from __future__ import annotations

_RELATION_TYPE_ALIASES: dict[str, str] = {
    "MENTIONS_GENE": "MENTIONS",
    "MENTIONS_PROTEIN": "MENTIONS",
    "MENTIONS_VARIANT": "MENTIONS",
    "MENTIONS_PHENOTYPE": "MENTIONS",
    "MENTIONS_DISEASE": "MENTIONS",
    "MENTIONS_DRUG": "MENTIONS",
    "AUTHORED_BY": "HAS_AUTHOR",
    "WRITTEN_BY": "HAS_AUTHOR",
    "HAS_MESH_TERM": "HAS_KEYWORD",
    "TAGGED_WITH": "HAS_KEYWORD",
}


def normalize_relation_type(relation_type: str) -> str:
    """Normalize relation labels to canonical dictionary relation types."""
    normalized = relation_type.strip().upper()
    if not normalized:
        return ""
    return _RELATION_TYPE_ALIASES.get(normalized, normalized)


__all__ = ["normalize_relation_type"]
