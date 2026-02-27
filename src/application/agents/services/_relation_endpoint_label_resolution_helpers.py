"""Shared label-resolution helpers for extraction relation endpoint matching."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.entities import KernelEntity

_CONCEPTUAL_ENTITY_TYPES = frozenset(
    {
        "GENE",
        "PROTEIN",
        "VARIANT",
        "PHENOTYPE",
        "DISEASE",
        "PATHWAY",
        "DRUG",
        "MECHANISM",
        "COMPLEX",
    },
)
_TOKEN_BASE_CONCEPT_KEY_TYPES = frozenset({"GENE", "PROTEIN", "COMPLEX"})
_TOKEN_BASE_FAMILY_TYPES = frozenset({"GENE", "PROTEIN", "COMPLEX", "VARIANT"})


def build_label_variants(label: str) -> tuple[str, ...]:
    """Build normalized query variants for endpoint lookup."""
    variants: list[str] = []
    seen: set[str] = set()

    def _append(raw_value: str) -> None:
        normalized = raw_value.strip()
        if not normalized:
            return
        dedupe_key = normalized.casefold()
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        variants.append(normalized)

    _append(label)
    without_parenthetical = re.sub(r"\([^)]*\)", " ", label)
    without_parenthetical = " ".join(without_parenthetical.split())
    _append(without_parenthetical)

    normalized_for_matching = normalize_label_for_matching(label)
    if normalized_for_matching:
        _append(normalized_for_matching)
        primary_token = extract_primary_token(normalized_for_matching)
        if primary_token is not None:
            _append(primary_token)
    return tuple(variants)


def select_best_candidate(
    *,
    query_label: str,
    candidates: tuple[KernelEntity, ...],
) -> KernelEntity | None:
    """Pick the best entity candidate for a query label."""
    if not candidates:
        return None
    query_normalized = normalize_label_for_matching(query_label)
    if not query_normalized:
        return None

    for candidate in candidates:
        candidate_label = (
            candidate.display_label if isinstance(candidate.display_label, str) else ""
        )
        if normalize_label_for_matching(candidate_label) == query_normalized:
            return candidate

    query_primary = extract_primary_token(query_normalized)
    if query_primary is None:
        return None
    query_species = extract_species_hints(query_normalized)

    token_matches: list[KernelEntity] = []
    for candidate in candidates:
        candidate_label = (
            candidate.display_label if isinstance(candidate.display_label, str) else ""
        )
        candidate_normalized = normalize_label_for_matching(candidate_label)
        candidate_primary = extract_primary_token(candidate_normalized)
        if candidate_primary != query_primary:
            continue
        candidate_species = extract_species_hints(candidate_normalized)
        if query_species and candidate_species and query_species != candidate_species:
            continue
        token_matches.append(candidate)

    if not token_matches:
        return None
    return min(
        token_matches,
        key=lambda candidate: len(
            normalize_label_for_matching(
                candidate.display_label if candidate.display_label is not None else "",
            ),
        ),
    )


def normalize_label_for_matching(label: str) -> str:
    """Normalize labels to a lower-cased alphanumeric token form."""
    without_parenthetical = re.sub(r"\([^)]*\)", " ", label)
    flattened = re.sub(r"[^A-Za-z0-9]+", " ", without_parenthetical)
    return " ".join(flattened.lower().split())


def extract_primary_token(normalized_label: str) -> str | None:
    """Extract the strongest token for coarse concept matching."""
    tokens = normalized_label.split()
    if not tokens:
        return None
    for token in tokens:
        if any(char.isdigit() for char in token) and any(
            char.isalpha() for char in token
        ):
            return token
    for token in tokens:
        if any(char.isalpha() for char in token):
            return token
    return tokens[0]


def extract_species_hints(normalized_label: str) -> set[str]:
    """Extract coarse species hints used to avoid bad cross-species merges."""
    species_tokens = {
        "human",
        "mouse",
        "rat",
        "zebrafish",
        "drosophila",
        "plant",
        "arabidopsis",
    }
    tokens = set(normalized_label.split())
    return {token for token in tokens if token in species_tokens}


def normalize_entity_type(entity_type: str) -> str:
    """Normalize entity-type text for identity functions."""
    return entity_type.strip().upper()


def is_conceptual_entity_type(entity_type: str) -> bool:
    """Return whether an entity type should participate in concept identity."""
    return normalize_entity_type(entity_type) in _CONCEPTUAL_ENTITY_TYPES


def _normalized_label_component(label: str) -> str | None:
    normalized_label = normalize_label_for_matching(label)
    if not normalized_label:
        return None
    return normalized_label.replace(" ", "_").upper()


def build_entity_concept_key(entity_type: str, label: str) -> str | None:
    """Build a deterministic concept key for one entity node."""
    normalized_type = normalize_entity_type(entity_type)
    if normalized_type not in _CONCEPTUAL_ENTITY_TYPES:
        return None
    normalized_label = normalize_label_for_matching(label)
    if not normalized_label:
        return None
    species = extract_species_hints(normalized_label)
    species_key = "+".join(sorted(species)) if species else "unspecified"
    if normalized_type in _TOKEN_BASE_CONCEPT_KEY_TYPES:
        primary = extract_primary_token(normalized_label)
        if primary is None:
            return None
        identity_component = primary.upper()
    else:
        normalized_component = _normalized_label_component(label)
        if normalized_component is None:
            return None
        identity_component = normalized_component
    return f"{normalized_type}::{identity_component}::{species_key}"


def build_concept_family_key(entity_type: str, label: str) -> str | None:
    """Build a family key used to group related conceptual entities."""
    normalized_type = normalize_entity_type(entity_type)
    if normalized_type not in _CONCEPTUAL_ENTITY_TYPES:
        return None
    normalized_label = normalize_label_for_matching(label)
    if not normalized_label:
        return None
    if normalized_type in _TOKEN_BASE_FAMILY_TYPES:
        primary = extract_primary_token(normalized_label)
        if primary is None:
            return None
        family_component = primary.upper()
    else:
        normalized_component = _normalized_label_component(label)
        if normalized_component is None:
            return None
        family_component = normalized_component
    species = extract_species_hints(normalized_label)
    if species:
        return f"{family_component}::{'+'.join(sorted(species))}"
    return family_component


def build_concept_family_key_from_label(label: str) -> str | None:
    """Build a family key directly from a label."""
    normalized_label = normalize_label_for_matching(label)
    primary = extract_primary_token(normalized_label)
    if primary is None:
        return None
    species = extract_species_hints(normalized_label)
    if species:
        return f"{primary.upper()}::{'+'.join(sorted(species))}"
    return primary.upper()


__all__ = [
    "build_label_variants",
    "build_concept_family_key",
    "build_concept_family_key_from_label",
    "build_entity_concept_key",
    "extract_primary_token",
    "extract_species_hints",
    "is_conceptual_entity_type",
    "normalize_entity_type",
    "normalize_label_for_matching",
    "select_best_candidate",
]
