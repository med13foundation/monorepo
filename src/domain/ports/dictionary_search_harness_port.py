"""Port interface for dictionary search harness orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.kernel.dictionary import DictionarySearchResult


class DictionarySearchHarnessPort(ABC):
    """Port for staged dictionary search orchestration."""

    @abstractmethod
    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        """Run staged dictionary search and return ranked matches."""


__all__ = ["DictionarySearchHarnessPort"]
