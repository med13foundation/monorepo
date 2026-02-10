"""
Unit tests for StatementMapper.
"""

from datetime import UTC, datetime
from uuid import uuid4

from src.domain.entities.statement import StatementOfUnderstanding
from src.domain.value_objects.confidence import EvidenceLevel
from src.domain.value_objects.statement_status import StatementStatus
from src.infrastructure.mappers.statement_mapper import StatementMapper
from src.models.database.phenotype import PhenotypeModel
from src.models.database.statement import StatementModel


def test_statement_mapper_to_domain() -> None:
    now = datetime.now(UTC)
    space_id = uuid4()
    statement_model = StatementModel(
        research_space_id=str(space_id),
        title="Mediator complex destabilization",
        summary="Test statement",
        evidence_tier="moderate",
        confidence_score=0.7,
        status="well_supported",
        source="manual",
        protein_domains=[
            {
                "name": "Mediator binding",
                "start_residue": 10,
                "end_residue": 50,
                "domain_type": "structural",
            },
        ],
        created_at=now,
        updated_at=now,
        promoted_mechanism_id=12,
    )
    phenotype = PhenotypeModel(
        hpo_id="HP:0000001",
        hpo_term="All",
        name="All",
        category="other",
    )
    phenotype.id = 1
    statement_model.phenotypes = [phenotype]

    statement = StatementMapper.to_domain(statement_model)

    assert statement.research_space_id == space_id
    assert statement.title == "Mediator complex destabilization"
    assert statement.evidence_tier == EvidenceLevel.MODERATE
    assert statement.status == StatementStatus.WELL_SUPPORTED
    assert statement.phenotype_ids == [1]
    assert statement.promoted_mechanism_id == 12


def test_statement_mapper_to_model() -> None:
    space_id = uuid4()
    statement = StatementOfUnderstanding(
        research_space_id=space_id,
        title="Mediator complex destabilization",
        summary="Test statement",
        evidence_tier=EvidenceLevel.STRONG,
        confidence_score=0.9,
        status=StatementStatus.UNDER_REVIEW,
        source="manual",
        promoted_mechanism_id=3,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    model = StatementMapper.to_model(statement)

    assert model.research_space_id == str(space_id)
    assert model.title == "Mediator complex destabilization"
    assert model.evidence_tier == "strong"
    assert model.status == "under_review"
    assert model.promoted_mechanism_id == 3
