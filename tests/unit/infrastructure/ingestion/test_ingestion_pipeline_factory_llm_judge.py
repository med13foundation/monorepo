"""Tests for LLM judge mapper feature-flag wiring in ingestion pipeline factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.ingestion.mapping import HybridMapper, LLMJudgeMapper

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext


class StubMappingJudgeAgent(MappingJudgePort):
    """No-op mapping judge used for factory wiring tests."""

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        _ = context
        _ = model_id
        return MappingJudgeContract(
            decision="no_match",
            selected_variable_id=None,
            candidate_count=0,
            selection_rationale="stub",
            selected_candidate=None,
            confidence_score=0.1,
            rationale="stub",
            evidence=[],
        )

    def close(self) -> None:
        return None


def _create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return cast("Session", session_factory())


def test_factory_skips_llm_judge_mapper_when_feature_flag_off(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_LLM_JUDGE_MAPPER", "0")
    session = _create_session()
    try:
        pipeline = create_ingestion_pipeline(session)
    finally:
        session.close()

    mapper = pipeline.mapper
    assert isinstance(mapper, HybridMapper)
    assert not any(isinstance(item, LLMJudgeMapper) for item in mapper.mappers)


def test_factory_enables_llm_judge_mapper_when_feature_flag_on(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MED13_ENABLE_LLM_JUDGE_MAPPER", "1")
    session = _create_session()
    try:
        pipeline = create_ingestion_pipeline(
            session,
            mapping_judge_agent=StubMappingJudgeAgent(),
        )
    finally:
        session.close()

    mapper = pipeline.mapper
    assert isinstance(mapper, HybridMapper)
    assert any(isinstance(item, LLMJudgeMapper) for item in mapper.mappers)
