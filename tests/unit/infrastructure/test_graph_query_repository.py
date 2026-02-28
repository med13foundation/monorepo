"""Unit tests for the SQLAlchemy graph-query repository adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.entities.user import UserRole, UserStatus
from src.infrastructure.repositories.kernel.graph_query_repository import (
    SqlAlchemyGraphQueryRepository,
)
from src.infrastructure.repositories.kernel.kernel_relation_repository import (
    SqlAlchemyKernelRelationRepository,
)
from src.models.database.kernel.dictionary import (
    DictionaryDataTypeModel,
    DictionaryDomainContextModel,
    DictionarySensitivityLevelModel,
    VariableDefinitionModel,
)
from src.models.database.kernel.entities import EntityModel
from src.models.database.kernel.observations import ObservationModel
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _seed_dictionary_primitives(db_session: Session) -> None:
    if db_session.get(DictionaryDataTypeModel, "STRING") is None:
        db_session.add(
            DictionaryDataTypeModel(
                id="STRING",
                display_name="String",
                python_type_hint="str",
                description="Text",
                constraint_schema={},
            ),
        )
    if db_session.get(DictionaryDomainContextModel, "general") is None:
        db_session.add(
            DictionaryDomainContextModel(
                id="general",
                display_name="General",
                description="General domain",
            ),
        )
    if db_session.get(DictionarySensitivityLevelModel, "INTERNAL") is None:
        db_session.add(
            DictionarySensitivityLevelModel(
                id="INTERNAL",
                display_name="Internal",
                description="Internal sensitivity",
            ),
        )
    if db_session.get(VariableDefinitionModel, "VAR_A") is None:
        db_session.add(
            VariableDefinitionModel(
                id="VAR_A",
                canonical_name="var_a",
                display_name="Variable A",
                data_type="STRING",
                preferred_unit=None,
                constraints={},
                domain_context="general",
                sensitivity="INTERNAL",
                description="Test variable A",
                created_by="seed",
            ),
        )
    if db_session.get(VariableDefinitionModel, "VAR_B") is None:
        db_session.add(
            VariableDefinitionModel(
                id="VAR_B",
                canonical_name="var_b",
                display_name="Variable B",
                data_type="STRING",
                preferred_unit=None,
                constraints={},
                domain_context="general",
                sensitivity="INTERNAL",
                description="Test variable B",
                created_by="seed",
            ),
        )
    db_session.flush()


def _seed_space(db_session: Session) -> UUID:
    owner_id = uuid4()
    db_session.add(
        UserModel(
            id=owner_id,
            email=f"{owner_id}@example.org",
            username=f"user_{str(owner_id).replace('-', '')[:8]}",
            full_name="Test User",
            hashed_password="hashed",
            role=UserRole.RESEARCHER,
            status=UserStatus.ACTIVE,
            email_verified=True,
        ),
    )

    research_space_id = uuid4()
    db_session.add(
        ResearchSpaceModel(
            id=research_space_id,
            slug=f"space-{str(research_space_id).replace('-', '')[:8]}",
            name="Test Space",
            description="Test research space",
            owner_id=owner_id,
            status=SpaceStatusEnum.ACTIVE,
            settings={},
            tags=[],
        ),
    )
    db_session.flush()
    return research_space_id


def _seed_graph(
    db_session: Session,
    *,
    research_space_id: UUID,
) -> tuple[UUID, UUID, UUID, UUID]:
    entity_a = uuid4()
    entity_b = uuid4()
    shared_entity = uuid4()
    db_session.add_all(
        [
            EntityModel(
                id=entity_a,
                research_space_id=research_space_id,
                entity_type="GENE",
                display_label="MED13",
                metadata_payload={},
            ),
            EntityModel(
                id=entity_b,
                research_space_id=research_space_id,
                entity_type="PHENOTYPE",
                display_label="Cardiomyopathy",
                metadata_payload={},
            ),
            EntityModel(
                id=shared_entity,
                research_space_id=research_space_id,
                entity_type="PATIENT",
                display_label="Patient 1",
                metadata_payload={},
            ),
        ],
    )
    db_session.flush()

    now = datetime.now(UTC)
    db_session.add_all(
        [
            ObservationModel(
                id=uuid4(),
                research_space_id=research_space_id,
                subject_id=entity_a,
                variable_id="VAR_A",
                value_text="yes",
                created_at=now,
            ),
            ObservationModel(
                id=uuid4(),
                research_space_id=research_space_id,
                subject_id=entity_b,
                variable_id="VAR_B",
                value_text="yes",
                created_at=now,
            ),
            ObservationModel(
                id=uuid4(),
                research_space_id=research_space_id,
                subject_id=shared_entity,
                variable_id="VAR_A",
                value_text="yes",
                created_at=now,
            ),
            ObservationModel(
                id=uuid4(),
                research_space_id=research_space_id,
                subject_id=shared_entity,
                variable_id="VAR_B",
                value_text="yes",
                created_at=now,
            ),
        ],
    )
    db_session.flush()

    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    relation = relation_repo.create(
        research_space_id=str(research_space_id),
        source_id=str(entity_a),
        relation_type="ASSOCIATED_WITH",
        target_id=str(entity_b),
        confidence=0.8,
        evidence_tier="LITERATURE",
    )
    relation_repo.create(
        research_space_id=str(research_space_id),
        source_id=str(entity_a),
        relation_type="ASSOCIATED_WITH",
        target_id=str(entity_b),
        confidence=0.9,
        evidence_tier="EXPERIMENTAL",
    )

    return entity_a, entity_b, shared_entity, relation.id


def test_graph_query_neighbourhood_scopes_to_research_space(
    db_session: Session,
) -> None:
    _seed_dictionary_primitives(db_session)
    primary_space = _seed_space(db_session)
    other_space = _seed_space(db_session)
    entity_a, entity_b, _shared_entity, _relation_id = _seed_graph(
        db_session,
        research_space_id=primary_space,
    )

    # Add an inconsistent edge in another space to ensure repository scoping works.
    relation_repo = SqlAlchemyKernelRelationRepository(db_session)
    relation_repo.create(
        research_space_id=str(other_space),
        source_id=str(entity_a),
        relation_type="ASSOCIATED_WITH",
        target_id=str(entity_b),
        confidence=0.5,
        evidence_tier="COMPUTATIONAL",
    )

    repository = SqlAlchemyGraphQueryRepository(db_session)
    relations = repository.graph_query_neighbourhood(
        research_space_id=str(primary_space),
        entity_id=str(entity_a),
        depth=1,
    )

    assert relations
    assert all(
        str(relation.research_space_id) == str(primary_space) for relation in relations
    )


def test_graph_query_shared_subjects_returns_overlap_entity(
    db_session: Session,
) -> None:
    _seed_dictionary_primitives(db_session)
    research_space = _seed_space(db_session)
    entity_a, entity_b, shared_entity, _relation_id = _seed_graph(
        db_session,
        research_space_id=research_space,
    )

    repository = SqlAlchemyGraphQueryRepository(db_session)
    shared_subjects = repository.graph_query_shared_subjects(
        research_space_id=str(research_space),
        entity_id_a=str(entity_a),
        entity_id_b=str(entity_b),
    )

    shared_ids = {str(entity.id) for entity in shared_subjects}
    assert str(shared_entity) in shared_ids
    assert str(entity_a) not in shared_ids
    assert str(entity_b) not in shared_ids


def test_graph_query_observations_filters_by_variable(db_session: Session) -> None:
    _seed_dictionary_primitives(db_session)
    research_space = _seed_space(db_session)
    _entity_a, _entity_b, shared_entity, _relation_id = _seed_graph(
        db_session,
        research_space_id=research_space,
    )

    repository = SqlAlchemyGraphQueryRepository(db_session)
    observations = repository.graph_query_observations(
        research_space_id=str(research_space),
        entity_id=str(shared_entity),
        variable_ids=["VAR_A"],
    )

    assert observations
    assert all(observation.variable_id == "VAR_A" for observation in observations)


def test_graph_query_relation_evidence_returns_rows(db_session: Session) -> None:
    _seed_dictionary_primitives(db_session)
    research_space = _seed_space(db_session)
    _entity_a, _entity_b, _shared_entity, relation_id = _seed_graph(
        db_session,
        research_space_id=research_space,
    )

    repository = SqlAlchemyGraphQueryRepository(db_session)
    evidences = repository.graph_query_relation_evidence(
        research_space_id=str(research_space),
        relation_id=str(relation_id),
    )

    assert len(evidences) == 2
    assert all(str(evidence.relation_id) == str(relation_id) for evidence in evidences)


def test_graph_query_entities_filters_by_type_and_query(db_session: Session) -> None:
    _seed_dictionary_primitives(db_session)
    research_space = _seed_space(db_session)
    entity_a, _entity_b, _shared_entity, _relation_id = _seed_graph(
        db_session,
        research_space_id=research_space,
    )

    repository = SqlAlchemyGraphQueryRepository(db_session)
    entities = repository.graph_query_entities(
        research_space_id=str(research_space),
        entity_type="GENE",
        query_text="MED13",
    )

    assert len(entities) == 1
    assert str(entities[0].id) == str(entity_a)


def test_graph_query_relations_applies_direction_filter(db_session: Session) -> None:
    _seed_dictionary_primitives(db_session)
    research_space = _seed_space(db_session)
    entity_a, entity_b, _shared_entity, _relation_id = _seed_graph(
        db_session,
        research_space_id=research_space,
    )

    repository = SqlAlchemyGraphQueryRepository(db_session)
    outgoing = repository.graph_query_relations(
        research_space_id=str(research_space),
        entity_id=str(entity_a),
        direction="outgoing",
    )
    incoming = repository.graph_query_relations(
        research_space_id=str(research_space),
        entity_id=str(entity_b),
        direction="incoming",
    )

    assert outgoing
    assert incoming
    assert all(str(relation.source_id) == str(entity_a) for relation in outgoing)
    assert all(str(relation.target_id) == str(entity_b) for relation in incoming)


def test_graph_query_by_observation_and_aggregate(db_session: Session) -> None:
    _seed_dictionary_primitives(db_session)
    research_space = _seed_space(db_session)
    entity_a, _entity_b, shared_entity, _relation_id = _seed_graph(
        db_session,
        research_space_id=research_space,
    )

    repository = SqlAlchemyGraphQueryRepository(db_session)
    entities = repository.graph_query_by_observation(
        research_space_id=str(research_space),
        variable_id="VAR_A",
        operator="eq",
        value="yes",
    )
    aggregate = repository.graph_aggregate(
        research_space_id=str(research_space),
        variable_id="VAR_A",
        aggregation="count",
    )

    entity_ids = {str(entity.id) for entity in entities}
    assert str(entity_a) in entity_ids
    assert str(shared_entity) in entity_ids
    assert aggregate["aggregation"] == "count"
    assert aggregate["value"] == 2
