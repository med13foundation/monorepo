"""Integration test for kernel ingestion pipeline (PubMed -> kernel tables)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.database.seeds.seeder import seed_all
from src.database.session import SessionLocal
from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.ingestion.sources.pubmed import PubMedAdapter
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.observations import ObservationModel
from src.models.database.research_space import ResearchSpaceModel
from src.models.database.user import UserModel


@pytest.mark.integration
@pytest.mark.database
def test_pubmed_pipeline_writes_publication_entity_and_observations(
    postgres_required,
) -> None:
    """
    Ensure the deterministic ingestion pipeline can write kernel facts for PubMed.

    This verifies:
    - dictionary seeding + synonym mapping works
    - a PUBLICATION entity is created/resolved from PMID/DOI/title anchors
    - observations are written with correct typed value slots
    """
    assert postgres_required is None

    session = SessionLocal()
    try:
        # Seed dictionary tables (idempotent)
        seed_all(session)

        # Create a space to scope kernel entities/observations
        suffix = uuid4().hex
        slug_suffix = suffix[:16]
        user = UserModel(
            email=f"kernel-pubmed-{suffix}@example.com",
            username=f"kernel-pubmed-{suffix}",
            full_name="Kernel PubMed Test",
            hashed_password="hashed_password",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        )
        session.add(user)
        session.flush()

        space = ResearchSpaceModel(
            # Slugs are limited to 50 chars in both domain + DB schema.
            slug=f"kpubmed-{slug_suffix}",
            name="Kernel PubMed Space",
            description="Space used for kernel PubMed ingestion test",
            owner_id=user.id,
            status="active",
        )
        session.add(space)
        session.flush()

        pipeline = create_ingestion_pipeline(session)

        records = [
            {
                "pmid": "123456",
                "title": "Test Study",
                "abstract": "This is a test abstract.",
                "doi": "10.1000/123456",
                "publication_date": "2023-01-01",
            },
        ]
        raw_records = PubMedAdapter().to_raw_records(records, source_id=str(uuid4()))

        result = pipeline.run(raw_records, research_space_id=str(space.id))

        assert result.success is True
        assert result.entities_created == 1
        assert result.observations_created == 5

        publication_entities = session.execute(
            select(EntityModel).where(
                EntityModel.research_space_id == space.id,
                EntityModel.entity_type == "PUBLICATION",
            ),
        ).scalars()
        publication_entity = publication_entities.one()
        assert publication_entity.display_label == "Test Study"

        title_obs = session.execute(
            select(ObservationModel).where(
                ObservationModel.subject_id == publication_entity.id,
                ObservationModel.variable_id == "VAR_PUBLICATION_TITLE",
            ),
        ).scalars()
        title_observation = title_obs.one()
        assert title_observation.value_text == "Test Study"

        abstract_obs = session.execute(
            select(ObservationModel).where(
                ObservationModel.subject_id == publication_entity.id,
                ObservationModel.variable_id == "VAR_ABSTRACT",
            ),
        ).scalars()
        abstract_observation = abstract_obs.one()
        assert abstract_observation.value_text == "This is a test abstract."

        pmid_obs = session.execute(
            select(ObservationModel).where(
                ObservationModel.subject_id == publication_entity.id,
                ObservationModel.variable_id == "VAR_PUBMED_ID",
            ),
        ).scalars()
        pmid_observation = pmid_obs.one()
        assert pmid_observation.value_text == "123456"

        doi_obs = session.execute(
            select(ObservationModel).where(
                ObservationModel.subject_id == publication_entity.id,
                ObservationModel.variable_id == "VAR_DOI",
            ),
        ).scalars()
        doi_observation = doi_obs.one()
        assert doi_observation.value_text == "10.1000/123456"

        publication_date_obs = session.execute(
            select(ObservationModel).where(
                ObservationModel.subject_id == publication_entity.id,
                ObservationModel.variable_id == "VAR_PUBLICATION_DATE",
            ),
        ).scalars()
        publication_date_observation = publication_date_obs.one()
        assert publication_date_observation.value_date is not None
    finally:
        session.close()
