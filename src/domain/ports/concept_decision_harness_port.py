"""Port interface for Concept Manager AI decision harness."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.kernel.concepts import (
    ConceptDecisionProposal,  # noqa: TC001
    ConceptHarnessVerdict,  # noqa: TC001
)


class ConceptDecisionHarnessPort(ABC):
    """Evaluate concept decisions before application."""

    @abstractmethod
    def evaluate(
        self,
        proposal: ConceptDecisionProposal,
    ) -> ConceptHarnessVerdict:
        """Run harness checks and return normalized verdict."""
