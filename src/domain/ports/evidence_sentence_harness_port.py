"""Port interface for optional evidence-sentence generation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.relations import (
    EvidenceSentenceGenerationRequest,  # noqa: TC001
    EvidenceSentenceGenerationResult,  # noqa: TC001
)


class EvidenceSentenceHarnessPort(ABC):
    """Generate contextual, non-verbatim evidence sentences for optional relations."""

    @abstractmethod
    def generate(
        self,
        request: EvidenceSentenceGenerationRequest,
        *,
        model_id: str | None = None,
    ) -> EvidenceSentenceGenerationResult:
        """Generate or fail with a structured reason without raising."""
