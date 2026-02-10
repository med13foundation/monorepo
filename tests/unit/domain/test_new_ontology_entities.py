"""
Unit tests for new ontology entities (Drug, Pathway) and enhanced Variant/Phenotype.
"""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.entities.drug import Drug, DrugApprovalStatus, TherapeuticModality
from src.domain.entities.mechanism import Mechanism
from src.domain.entities.pathway import Pathway
from src.domain.entities.phenotype import LongitudinalObservation, Phenotype
from src.domain.entities.statement import StatementOfUnderstanding
from src.domain.entities.variant import (
    InSilicoScores,
    ProteinStructuralAnnotation,
    Variant,
)
from src.domain.value_objects.confidence import EvidenceLevel
from src.domain.value_objects.identifiers import PhenotypeIdentifier, VariantIdentifier
from src.domain.value_objects.mechanism_lifecycle import MechanismLifecycleState
from src.domain.value_objects.protein_structure import Coordinates3D, ProteinDomain
from src.domain.value_objects.statement_status import StatementStatus


class TestDrugEntity:
    def test_create_valid_drug(self) -> None:
        drug = Drug(
            id="DB00001",
            name="TestDrug",
            modality=TherapeuticModality.SMALL_MOLECULE,
            approval_status=DrugApprovalStatus.APPROVED,
            brain_penetrant=True,
        )
        assert drug.name == "TestDrug"
        assert drug.brain_penetrant is True
        assert drug.modality == TherapeuticModality.SMALL_MOLECULE

    def test_default_values(self) -> None:
        drug = Drug(id="DB00002", name="NewDrug")
        assert drug.approval_status == DrugApprovalStatus.EXPERIMENTAL
        assert drug.targets == []


class TestPathwayEntity:
    def test_create_valid_pathway(self) -> None:
        pathway = Pathway(
            id="R-HSA-123",
            name="Wnt Signaling",
            source="Reactome",
            genes=["MED13", "CTNNB1"],
            category="signaling",
        )
        assert pathway.name == "Wnt Signaling"
        assert "MED13" in pathway.genes

    def test_invalid_category(self) -> None:
        # Pydantic validation should catch invalid literals if strict,
        # but here we check if it accepts valid ones.
        # Note: Pydantic V2 enforces literals by default.
        with pytest.raises(ValidationError):
            Pathway(
                id="P1",
                name="Test",
                source="Local",
                category="invalid_category",  # type: ignore[arg-type]
            )


class TestProteinDomain:
    def test_create_domain(self) -> None:
        coords = Coordinates3D(x=1.0, y=2.0, z=3.0, confidence=90.0)
        domain = ProteinDomain(
            name="TestDomain",
            start_residue=10,
            end_residue=50,
            coordinates=[coords],
        )
        assert domain.contains_residue(30) is True
        assert domain.contains_residue(5) is False


class TestEnhancedVariant:
    def test_variant_with_annotations(self) -> None:
        domain = ProteinDomain(name="IDR", start_residue=1, end_residue=100)
        structural = ProteinStructuralAnnotation(
            affected_domains=[domain],
            distance_to_interface=5.5,
        )
        scores = InSilicoScores(cadd_phred=25.0)

        variant = Variant(
            identifier=VariantIdentifier(variant_id="chr1:100:A>G"),
            chromosome="chr1",
            position=100,
            reference_allele="A",
            alternate_allele="G",
            structural_annotation=structural,
            in_silico_scores=scores,
            predicted_mechanism="LoF",
        )

        assert variant.structural_annotation is not None
        assert variant.structural_annotation.distance_to_interface == 5.5
        assert variant.in_silico_scores.cadd_phred == 25.0
        assert variant.predicted_mechanism == "LoF"


class TestEnhancedPhenotype:
    def test_phenotype_with_observations(self) -> None:
        phenotype = Phenotype(
            identifier=PhenotypeIdentifier(hpo_id="HP:0001250", hpo_term="Seizures"),
            name="Seizures",
        )

        obs = LongitudinalObservation(
            date_observed=date(2023, 1, 1),
            age_at_onset_months=12,
            severity_score=3,
            source="Clinician",
        )

        phenotype.add_observation(obs)
        assert len(phenotype.observations) == 1
        assert phenotype.observations[0].severity_score == 3


class TestMechanismEntity:
    def test_create_valid_mechanism(self) -> None:
        domain = ProteinDomain(
            name="Mediator binding",
            start_residue=10,
            end_residue=50,
        )
        mechanism = Mechanism(
            research_space_id=uuid4(),
            name="Mediator complex disruption",
            description="Disrupts mediator complex stability leading to phenotype.",
            evidence_tier=EvidenceLevel.STRONG,
            confidence_score=0.8,
            lifecycle_state=MechanismLifecycleState.REVIEWED,
            protein_domains=[domain],
            phenotype_ids=[1, 2],
        )
        assert mechanism.name == "Mediator complex disruption"
        assert mechanism.evidence_tier == EvidenceLevel.STRONG
        assert mechanism.confidence_score == 0.8
        assert mechanism.lifecycle_state == MechanismLifecycleState.REVIEWED
        assert mechanism.protein_domains[0].name == "Mediator binding"
        assert mechanism.phenotype_ids == [1, 2]

    def test_invalid_confidence_score(self) -> None:
        with pytest.raises(ValidationError):
            Mechanism(
                research_space_id=uuid4(),
                name="Invalid confidence",
                confidence_score=1.5,
                description="Placeholder description.",
                phenotype_ids=[1],
            )

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Mechanism(
                research_space_id=uuid4(),
                name="  ",
                description="Placeholder description.",
                phenotype_ids=[1],
            )


class TestStatementEntity:
    def test_create_valid_statement(self) -> None:
        statement = StatementOfUnderstanding(
            research_space_id=uuid4(),
            title="Mediator complex destabilization",
            summary="Evidence indicates mediator complex instability drives phenotype.",
            evidence_tier=EvidenceLevel.MODERATE,
            confidence_score=0.7,
            status=StatementStatus.WELL_SUPPORTED,
            phenotype_ids=[1],
        )
        assert statement.title == "Mediator complex destabilization"
        assert statement.status == StatementStatus.WELL_SUPPORTED
        assert statement.evidence_tier == EvidenceLevel.MODERATE

    def test_invalid_statement_title(self) -> None:
        with pytest.raises(ValidationError):
            StatementOfUnderstanding(
                research_space_id=uuid4(),
                title=" ",
                summary="Valid summary",
            )

    def test_invalid_statement_summary(self) -> None:
        with pytest.raises(ValidationError):
            StatementOfUnderstanding(
                research_space_id=uuid4(),
                title="Valid title",
                summary=" ",
            )
