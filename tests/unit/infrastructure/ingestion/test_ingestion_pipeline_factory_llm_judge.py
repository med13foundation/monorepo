"""Tests for Artana-first LLM judge wiring in ingestion pipeline factory."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.infrastructure.factories.ingestion_pipeline_factory import (
    create_ingestion_pipeline,
)
from src.infrastructure.ingestion.mapping import HybridMapper, LLMJudgeMapper

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
    from src.domain.entities.kernel.dictionary import DictionarySearchResult


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


class StubDictionarySearchHarness(DictionarySearchHarnessPort):
    """No-op dictionary harness stub for factory wiring tests."""

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        _ = terms
        _ = dimensions
        _ = domain_context
        _ = limit
        _ = include_inactive
        return []


def _create_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return cast("Session", session_factory())


def test_factory_requires_artana_judge_when_not_injected() -> None:
    session = _create_session()
    try:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "sqlite+pysqlite:///:memory:",
                "ASYNC_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            },
            clear=False,
        ):
            os.environ.pop("ARTANA_STATE_URI", None)
            with pytest.raises(
                RuntimeError,
                match="Artana state backend requires a PostgreSQL",
            ):
                create_ingestion_pipeline(session)
    finally:
        session.close()


def test_factory_always_enables_llm_judge_mapper_when_injected() -> None:
    session = _create_session()
    try:
        pipeline = create_ingestion_pipeline(
            session,
            mapping_judge_agent=StubMappingJudgeAgent(),
            dictionary_search_harness=StubDictionarySearchHarness(),
        )
    finally:
        session.close()

    mapper = pipeline.mapper
    assert isinstance(mapper, HybridMapper)
    assert any(isinstance(item, LLMJudgeMapper) for item in mapper.mappers)
