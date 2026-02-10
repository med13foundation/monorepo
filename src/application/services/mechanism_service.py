"""Application-level orchestration for mechanism workflows."""

from collections.abc import Mapping
from uuid import UUID

from src.domain.entities.mechanism import Mechanism
from src.domain.repositories.mechanism_repository import MechanismRepository
from src.domain.value_objects.confidence import EvidenceLevel
from src.domain.value_objects.mechanism_lifecycle import MechanismLifecycleState
from src.domain.value_objects.protein_structure import ProteinDomain
from src.type_definitions.common import FilterValue, MechanismUpdate, QueryFilters


class MechanismApplicationService:
    """
    Application service for mechanism management use cases.
    """

    def __init__(self, mechanism_repository: MechanismRepository):
        self._mechanism_repository = mechanism_repository

    def create_mechanism(  # noqa: PLR0913 - explicit mechanism fields for clarity
        self,
        name: str,
        *,
        research_space_id: UUID,
        description: str | None = None,
        evidence_tier: EvidenceLevel = EvidenceLevel.SUPPORTING,
        confidence_score: float = 0.5,
        source: str = "manual_curation",
        lifecycle_state: MechanismLifecycleState = MechanismLifecycleState.DRAFT,
        protein_domains: list[ProteinDomain] | None = None,
        phenotype_ids: list[int] | None = None,
    ) -> Mechanism:
        """
        Create a new mechanism.
        """
        if description is None or not description.strip():
            msg = "Mechanism description is required"
            raise ValueError(msg)
        if not phenotype_ids:
            msg = "At least one phenotype is required"
            raise ValueError(msg)
        mechanism = Mechanism(
            research_space_id=research_space_id,
            name=name,
            description=description,
            evidence_tier=evidence_tier,
            confidence_score=confidence_score,
            source=source,
            lifecycle_state=lifecycle_state,
            protein_domains=protein_domains or [],
            phenotype_ids=phenotype_ids,
        )
        return self._mechanism_repository.create(mechanism)

    def get_mechanism_by_id(self, mechanism_id: int) -> Mechanism | None:
        """Retrieve a mechanism by its database ID."""
        return self._mechanism_repository.get_by_id(mechanism_id)

    def get_mechanism_by_name(
        self,
        name: str,
        *,
        research_space_id: UUID,
    ) -> Mechanism | None:
        """Find a mechanism by name within a research space."""
        return self._mechanism_repository.find_by_name(
            name,
            research_space_id=research_space_id,
        )

    def search_mechanisms(
        self,
        query: str,
        limit: int = 10,
        filters: Mapping[str, FilterValue] | QueryFilters | None = None,
    ) -> list[Mechanism]:
        """Search mechanisms with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._mechanism_repository.search_mechanisms(
            query,
            limit,
            normalized_filters,
        )

    def list_mechanisms(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: Mapping[str, FilterValue] | QueryFilters | None = None,
    ) -> tuple[list[Mechanism], int]:
        """Retrieve paginated mechanisms with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._mechanism_repository.paginate_mechanisms(
            page,
            per_page,
            sort_by,
            sort_order,
            normalized_filters,
        )

    def update_mechanism(
        self,
        mechanism_id: int,
        updates: MechanismUpdate,
    ) -> Mechanism:
        """Update mechanism fields."""
        if not updates:
            msg = "No mechanism updates provided"
            raise ValueError(msg)
        if "description" in updates:
            description = updates["description"]
            if description is None or not str(description).strip():
                msg = "Mechanism description is required"
                raise ValueError(msg)
        if "phenotype_ids" in updates and not updates["phenotype_ids"]:
            msg = "At least one phenotype is required"
            raise ValueError(msg)
        return self._mechanism_repository.update_mechanism(
            mechanism_id,
            updates,
        )

    def delete_mechanism(self, mechanism_id: int) -> bool:
        """Delete a mechanism by ID."""
        return self._mechanism_repository.delete(mechanism_id)

    @staticmethod
    def _normalize_filters(
        filters: Mapping[str, FilterValue] | QueryFilters | None,
    ) -> QueryFilters | None:
        if filters is None:
            return None
        normalized: QueryFilters = {}
        for key, value in filters.items():
            if value is not None:
                normalized[key] = value
        return normalized or None


__all__ = ["MechanismApplicationService"]
