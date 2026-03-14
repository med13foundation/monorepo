"""Dictionary domain-context contracts owned by graph-core."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DictionaryDomainContextDefinition:
    """One approved builtin dictionary domain context."""

    id: str
    display_name: str
    description: str
