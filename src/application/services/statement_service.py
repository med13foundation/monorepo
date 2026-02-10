"""Application-level orchestration for Statement of Understanding workflows."""

from collections.abc import Mapping
from uuid import UUID

from src.domain.entities.mechanism import Mechanism
from src.domain.entities.statement import StatementOfUnderstanding
from src.domain.repositories.mechanism_repository import MechanismRepository
from src.domain.repositories.statement_repository import StatementRepository
from src.domain.value_objects.confidence import EvidenceLevel
from src.domain.value_objects.mechanism_lifecycle import MechanismLifecycleState
from src.domain.value_objects.protein_structure import ProteinDomain
from src.domain.value_objects.statement_status import StatementStatus
from src.type_definitions.common import FilterValue, QueryFilters, StatementUpdate

PROMOTION_EVIDENCE_LEVELS: set[EvidenceLevel] = {
    EvidenceLevel.MODERATE,
    EvidenceLevel.STRONG,
    EvidenceLevel.DEFINITIVE,
}


class StatementApplicationService:
    """
    Application service for statement management use cases.
    """

    def __init__(
        self,
        statement_repository: StatementRepository,
        mechanism_repository: MechanismRepository,
    ):
        self._statement_repository = statement_repository
        self._mechanism_repository = mechanism_repository

    def create_statement(  # noqa: PLR0913 - explicit statement fields for clarity
        self,
        title: str,
        *,
        research_space_id: UUID,
        summary: str,
        evidence_tier: EvidenceLevel = EvidenceLevel.SUPPORTING,
        confidence_score: float = 0.5,
        status: StatementStatus = StatementStatus.DRAFT,
        source: str = "manual_curation",
        protein_domains: list[ProteinDomain] | None = None,
        phenotype_ids: list[int] | None = None,
    ) -> StatementOfUnderstanding:
        """
        Create a new statement of understanding.
        """
        if not title.strip():
            msg = "Statement title is required"
            raise ValueError(msg)
        if summary is None or not summary.strip():
            msg = "Statement summary is required"
            raise ValueError(msg)

        statement = StatementOfUnderstanding(
            research_space_id=research_space_id,
            title=title,
            summary=summary,
            evidence_tier=evidence_tier,
            confidence_score=confidence_score,
            status=status,
            source=source,
            protein_domains=protein_domains or [],
            phenotype_ids=phenotype_ids or [],
        )
        return self._statement_repository.create(statement)

    def get_statement_by_id(self, statement_id: int) -> StatementOfUnderstanding | None:
        """Retrieve a statement by its database ID."""
        return self._statement_repository.get_by_id(statement_id)

    def search_statements(
        self,
        query: str,
        limit: int = 10,
        filters: Mapping[str, FilterValue] | QueryFilters | None = None,
    ) -> list[StatementOfUnderstanding]:
        """Search statements with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._statement_repository.search_statements(
            query,
            limit,
            normalized_filters,
        )

    def list_statements(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        sort_order: str,
        filters: Mapping[str, FilterValue] | QueryFilters | None = None,
    ) -> tuple[list[StatementOfUnderstanding], int]:
        """Retrieve paginated statements with optional filters."""
        normalized_filters = self._normalize_filters(filters)
        return self._statement_repository.paginate_statements(
            page,
            per_page,
            sort_by,
            sort_order,
            normalized_filters,
        )

    def update_statement(
        self,
        statement_id: int,
        updates: StatementUpdate,
    ) -> StatementOfUnderstanding:
        """Update statement fields."""
        if not updates:
            msg = "No statement updates provided"
            raise ValueError(msg)
        if "title" in updates and not str(updates["title"]).strip():
            msg = "Statement title cannot be empty"
            raise ValueError(msg)
        if "summary" in updates:
            summary = updates["summary"]
            if summary is None or not str(summary).strip():
                msg = "Statement summary is required"
                raise ValueError(msg)
        return self._statement_repository.update_statement(statement_id, updates)

    def delete_statement(self, statement_id: int) -> bool:
        """Delete a statement by ID."""
        return self._statement_repository.delete(statement_id)

    def promote_to_mechanism(
        self,
        statement_id: int,
        *,
        research_space_id: UUID,
    ) -> Mechanism:
        """
        Promote a well-supported statement to a canonical mechanism.
        """
        statement = self._statement_repository.get_by_id(statement_id)
        if statement is None or statement.research_space_id != research_space_id:
            msg = "Statement not found"
            raise ValueError(msg)
        if statement.promoted_mechanism_id is not None:
            msg = "Statement has already been promoted"
            raise ValueError(msg)
        if statement.status != StatementStatus.WELL_SUPPORTED:
            msg = "Statement must be well supported before promotion"
            raise ValueError(msg)
        if statement.evidence_tier not in PROMOTION_EVIDENCE_LEVELS:
            msg = "Evidence tier must be moderate or higher to promote"
            raise ValueError(msg)
        if not statement.phenotype_ids:
            msg = "At least one phenotype is required for promotion"
            raise ValueError(msg)

        mechanism = Mechanism(
            research_space_id=statement.research_space_id,
            name=statement.title,
            description=statement.summary,
            evidence_tier=statement.evidence_tier,
            confidence_score=statement.confidence_score,
            source=statement.source,
            lifecycle_state=MechanismLifecycleState.DRAFT,
            protein_domains=statement.protein_domains,
            phenotype_ids=statement.phenotype_ids,
        )
        created = self._mechanism_repository.create(mechanism)
        self._statement_repository.update_statement(
            statement_id,
            {"promoted_mechanism_id": created.id},
        )
        return created

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


__all__ = ["StatementApplicationService"]
