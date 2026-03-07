"""Unit tests for Artana dictionary search harness adapter."""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agents.contracts.mapping_judge import MappingJudgeContract
from src.domain.agents.models import ModelCapability, ModelSpec
from src.domain.entities.kernel.dictionary import DictionarySearchResult
from src.domain.ports.text_embedding_port import TextEmbeddingPort
from src.infrastructure.llm.adapters.dictionary_search_harness_adapter import (
    ArtanaDictionarySearchHarnessAdapter,
)

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext

_ADAPTER_MODULE = "src.infrastructure.llm.adapters.dictionary_search_harness_adapter"


def _build_result(
    *,
    entry_id: str,
    display_name: str,
    match_method: str,
    score: float,
) -> DictionarySearchResult:
    return DictionarySearchResult(
        dimension="variables",
        entry_id=entry_id,
        display_name=display_name,
        description="test",
        domain_context="cardiology",
        match_method=match_method,
        similarity_score=score,
        metadata={"canonical_name": display_name.casefold().replace(" ", "_")},
    )


class _StubEmbeddingProvider(TextEmbeddingPort):
    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        del model_name
        normalized = text.strip()
        if not normalized:
            return None
        return [float(len(normalized))]


class _StubMappingJudge:
    def __init__(self, *, selected_variable_id: str | None) -> None:
        self.selected_variable_id = selected_variable_id
        self.calls = 0
        self.last_context: MappingJudgeContext | None = None

    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        del model_id
        self.calls += 1
        self.last_context = context
        if self.selected_variable_id is None:
            return MappingJudgeContract(
                decision="no_match",
                selected_variable_id=None,
                candidate_count=len(context.candidates),
                selection_rationale="No match.",
                selected_candidate=None,
                confidence_score=0.0,
                rationale="No match.",
                evidence=[],
            )
        return MappingJudgeContract(
            decision="matched",
            selected_variable_id=self.selected_variable_id,
            candidate_count=len(context.candidates),
            selection_rationale="Selected by test stub.",
            selected_candidate=None,
            confidence_score=0.82,
            rationale="Selected by test stub.",
            evidence=[],
        )

    def close(self) -> None:
        return None


@dataclass
class _FakeToolResult:
    result_json: str


class _FakeKernel:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.step_tool_calls: list[str] = []
        self.close = AsyncMock()

    def tool(self) -> object:
        def _decorator(function: object) -> object:
            name = getattr(function, "__name__", None)
            if not isinstance(name, str):
                msg = "Tool function must define __name__."
                raise TypeError(msg)
            self.tools[name] = function
            return function

        return _decorator

    async def step_tool(
        self,
        *,
        run_id: str,
        tenant: object,
        tool_name: str,
        arguments: object,
        step_key: str,
    ) -> _FakeToolResult:
        del run_id, tenant, step_key
        self.step_tool_calls.append(tool_name)
        tool = self.tools[tool_name]
        if not callable(tool):
            msg = f"Tool '{tool_name}' is not callable."
            raise TypeError(msg)
        payload = (
            arguments.model_dump() if hasattr(arguments, "model_dump") else arguments
        )
        if not isinstance(payload, dict):
            msg = "Tool arguments must serialize to a dict."
            raise TypeError(msg)
        result_json = await tool(**payload)
        if not isinstance(result_json, str):
            msg = "Tool must return JSON string payload."
            raise TypeError(msg)
        return _FakeToolResult(result_json=result_json)

    async def run_workflow(
        self,
        *,
        run_id: str,
        tenant: object,
        workflow: object,
    ) -> SimpleNamespace:
        if not callable(workflow):
            msg = "Workflow must be callable."
            raise TypeError(msg)
        output = await workflow(SimpleNamespace(run_id=run_id, tenant=tenant))
        return SimpleNamespace(status="complete", output=output)


class _FakeModelPort:
    def __init__(self) -> None:
        self.aclose = AsyncMock()


class _FakeClient:
    def __init__(self, *, outputs: list[object]) -> None:
        self._outputs = outputs
        self.calls: list[dict[str, object]] = []

    async def step(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant: object,
        model: str,
        prompt: str,
        output_schema: type[object],
        step_key: str,
        replay_policy: str,
        context_version: object | None = None,
    ) -> SimpleNamespace:
        del tenant, output_schema, context_version
        self.calls.append(
            {
                "run_id": run_id,
                "model": model,
                "prompt": prompt,
                "step_key": step_key,
                "replay_policy": replay_policy,
            },
        )
        if not self._outputs:
            msg = "No fake planner output available."
            raise RuntimeError(msg)
        return SimpleNamespace(output=self._outputs.pop(0))


def _build_registry() -> MagicMock:
    registry = MagicMock()
    query_spec = ModelSpec(
        model_id="openai:gpt-5-mini",
        display_name="GPT-5 Mini",
        provider="openai",
        capabilities=frozenset({ModelCapability.QUERY_GENERATION}),
        prompt_tokens_per_1k=0.00025,
        completion_tokens_per_1k=0.002,
        timeout_seconds=60.0,
        is_default=True,
    )
    registry.get_default_model.return_value = query_spec
    registry.get_model.return_value = query_spec
    return registry


@contextmanager
def _build_adapter(
    *,
    repo: MagicMock,
    mapping_judge: _StubMappingJudge,
    planner_outputs: list[object],
):
    fake_kernel = _FakeKernel()
    fake_model_port = _FakeModelPort()
    fake_client = _FakeClient(outputs=list(planner_outputs))
    governance = MagicMock()
    governance.usage_limits.total_cost_usd = 1.0
    runtime_policy = MagicMock()
    runtime_policy.replay_policy = "strict"
    runtime_policy.to_context_version.return_value = None

    with (
        patch(f"{_ADAPTER_MODULE}._ARTANA_IMPORT_ERROR", None),
        patch(f"{_ADAPTER_MODULE}.get_model_registry", return_value=_build_registry()),
        patch(
            f"{_ADAPTER_MODULE}.GovernanceConfig.from_environment",
            return_value=governance,
        ),
        patch(f"{_ADAPTER_MODULE}.load_runtime_policy", return_value=runtime_policy),
        patch(
            f"{_ADAPTER_MODULE}.OpenAIJSONSchemaModelPort",
            return_value=fake_model_port,
        ),
        patch(f"{_ADAPTER_MODULE}.ArtanaKernel", return_value=fake_kernel, create=True),
        patch(
            f"{_ADAPTER_MODULE}.SingleStepModelClient",
            return_value=fake_client,
            create=True,
        ),
        patch.object(
            ArtanaDictionarySearchHarnessAdapter,
            "_create_store",
            return_value=object(),
        ),
        patch.object(
            ArtanaDictionarySearchHarnessAdapter,
            "_create_tenant",
            return_value=object(),
        ),
    ):
        adapter = ArtanaDictionarySearchHarnessAdapter(
            dictionary_repo=repo,
            embedding_provider=_StubEmbeddingProvider(),
            mapping_judge_agent=mapping_judge,
        )
        yield adapter, fake_kernel, fake_client, fake_model_port


def test_search_stops_after_direct_exact_hit() -> None:
    repo = MagicMock()
    repo.search_dictionary.return_value = [
        _build_result(
            entry_id="VAR_HEART_RATE",
            display_name="Heart Rate",
            match_method="exact",
            score=1.0,
        ),
    ]
    mapping_judge = _StubMappingJudge(selected_variable_id=None)

    with _build_adapter(
        repo=repo,
        mapping_judge=mapping_judge,
        planner_outputs=[
            {"action": "vector_original", "custom_terms": [], "rationale": "unused"},
        ],
    ) as (adapter, fake_kernel, fake_client, _):
        results = adapter.search(terms=["Heart Rate"], dimensions=["variables"])

    assert len(results) == 1
    assert results[0].entry_id == "VAR_HEART_RATE"
    assert fake_kernel.step_tool_calls == []
    assert not fake_client.calls
    assert mapping_judge.calls == 0
    assert repo.search_dictionary.call_count == 1
    adapter.close()


def test_search_uses_custom_vector_tool_and_reorders_with_mapping_judge() -> None:
    repo = MagicMock()
    direct_hits = [
        _build_result(
            entry_id="VAR_ALPHA",
            display_name="Alpha Marker",
            match_method="fuzzy",
            score=0.66,
        ),
    ]
    vector_hits = [
        _build_result(
            entry_id="VAR_FIRST",
            display_name="First Candidate",
            match_method="vector",
            score=0.79,
        ),
        _build_result(
            entry_id="VAR_SECOND",
            display_name="Second Candidate",
            match_method="vector",
            score=0.75,
        ),
    ]
    repo.search_dictionary.side_effect = [direct_hits, vector_hits]
    mapping_judge = _StubMappingJudge(selected_variable_id="VAR_SECOND")

    with (
        patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "test-openai-key"},
            clear=False,
        ),
        _build_adapter(
            repo=repo,
            mapping_judge=mapping_judge,
            planner_outputs=[
                {
                    "action": "vector_custom",
                    "custom_terms": ["metabolic control axis"],
                    "rationale": "Rewrite for semantic retrieval.",
                },
            ],
        ) as (adapter, fake_kernel, fake_client, _),
    ):
        results = adapter.search(
            terms=["whole body metabolism cardiomyocyte"],
            dimensions=["variables"],
            domain_context="cardiology",
            limit=5,
        )

    assert len(results) == 2
    assert results[0].entry_id == "VAR_SECOND"
    assert results[1].entry_id == "VAR_FIRST"
    assert fake_kernel.step_tool_calls == ["dictionary_vector_custom_search"]
    assert len(fake_client.calls) == 1
    assert mapping_judge.calls == 1

    vector_call = repo.search_dictionary.call_args_list[1].kwargs
    assert vector_call["terms"] == ["metabolic control axis"]
    assert vector_call["query_embeddings"] is not None
    adapter.close()


def test_search_creates_runtime_per_call_to_avoid_loop_bound_reuse() -> None:
    repo = MagicMock()
    direct_hits = [
        _build_result(
            entry_id="VAR_ALPHA",
            display_name="Alpha Marker",
            match_method="fuzzy",
            score=0.61,
        ),
    ]
    vector_hits = [
        _build_result(
            entry_id="VAR_VECTOR",
            display_name="Vector Candidate",
            match_method="vector",
            score=0.82,
        ),
    ]
    # Each search performs direct + vector lookup.
    repo.search_dictionary.side_effect = [
        direct_hits,
        vector_hits,
        direct_hits,
        vector_hits,
    ]

    governance = MagicMock()
    governance.usage_limits.total_cost_usd = 1.0
    runtime_policy = MagicMock()
    runtime_policy.replay_policy = "strict"
    runtime_policy.to_context_version.return_value = None

    fake_kernel_first = _FakeKernel()
    fake_kernel_second = _FakeKernel()
    fake_model_port_first = _FakeModelPort()
    fake_model_port_second = _FakeModelPort()
    fake_client_first = _FakeClient(
        outputs=[
            {"action": "vector_original", "custom_terms": [], "rationale": "test"},
        ],
    )
    fake_client_second = _FakeClient(
        outputs=[
            {"action": "vector_original", "custom_terms": [], "rationale": "test"},
        ],
    )
    mapping_judge = _StubMappingJudge(selected_variable_id=None)

    with (
        patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "test-openai-key"},
            clear=False,
        ),
        patch(f"{_ADAPTER_MODULE}._ARTANA_IMPORT_ERROR", None),
        patch(f"{_ADAPTER_MODULE}.get_model_registry", return_value=_build_registry()),
        patch(
            f"{_ADAPTER_MODULE}.GovernanceConfig.from_environment",
            return_value=governance,
        ),
        patch(f"{_ADAPTER_MODULE}.load_runtime_policy", return_value=runtime_policy),
        patch(
            f"{_ADAPTER_MODULE}.OpenAIJSONSchemaModelPort",
            side_effect=[fake_model_port_first, fake_model_port_second],
        ),
        patch(
            f"{_ADAPTER_MODULE}.ArtanaKernel",
            side_effect=[fake_kernel_first, fake_kernel_second],
            create=True,
        ) as kernel_constructor,
        patch(
            f"{_ADAPTER_MODULE}.SingleStepModelClient",
            side_effect=[fake_client_first, fake_client_second],
            create=True,
        ),
        patch.object(
            ArtanaDictionarySearchHarnessAdapter,
            "_create_store",
            return_value=object(),
        ),
        patch.object(
            ArtanaDictionarySearchHarnessAdapter,
            "_create_tenant",
            return_value=object(),
        ),
    ):
        adapter = ArtanaDictionarySearchHarnessAdapter(
            dictionary_repo=repo,
            embedding_provider=_StubEmbeddingProvider(),
            mapping_judge_agent=mapping_judge,
        )
        first = adapter.search(terms=["term"], dimensions=["variables"], limit=5)
        second = adapter.search(terms=["term"], dimensions=["variables"], limit=5)

    assert first[0].entry_id == "VAR_VECTOR"
    assert second[0].entry_id == "VAR_VECTOR"
    # Runtime must be recreated per search to avoid reusing loop-bound async pools.
    assert kernel_constructor.call_count == 2
    fake_model_port_first.aclose.assert_awaited_once()
    fake_model_port_second.aclose.assert_awaited_once()
    fake_kernel_first.close.assert_awaited_once()
    fake_kernel_second.close.assert_awaited_once()


def test_search_creates_runtime_in_worker_thread_when_event_loop_is_active() -> None:
    repo = MagicMock()
    direct_hits = [
        _build_result(
            entry_id="VAR_ALPHA",
            display_name="Alpha Marker",
            match_method="fuzzy",
            score=0.61,
        ),
    ]
    vector_hits = [
        _build_result(
            entry_id="VAR_VECTOR",
            display_name="Vector Candidate",
            match_method="vector",
            score=0.82,
        ),
    ]
    repo.search_dictionary.side_effect = [direct_hits, vector_hits]
    mapping_judge = _StubMappingJudge(selected_variable_id=None)
    runtime_thread_ids: list[int] = []

    with (
        patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "test-openai-key"},
            clear=False,
        ),
        _build_adapter(
            repo=repo,
            mapping_judge=mapping_judge,
            planner_outputs=[
                {"action": "vector_original", "custom_terms": [], "rationale": "test"},
            ],
        ) as (adapter, _, _, _),
    ):
        original_create_runtime = adapter._create_runtime

        def _record_runtime_thread() -> tuple[_FakeKernel, _FakeClient, _FakeModelPort]:
            runtime_thread_ids.append(threading.get_ident())
            return original_create_runtime()

        async def _invoke_search() -> tuple[int, list[DictionarySearchResult]]:
            caller_thread_id = threading.get_ident()
            results = adapter.search(terms=["term"], dimensions=["variables"], limit=5)
            return caller_thread_id, results

        with patch.object(
            adapter,
            "_create_runtime",
            side_effect=_record_runtime_thread,
        ):
            caller_thread_id, results = asyncio.run(_invoke_search())

    assert results[0].entry_id == "VAR_VECTOR"
    assert runtime_thread_ids
    assert all(thread_id != caller_thread_id for thread_id in runtime_thread_ids)


def test_run_coroutine_times_out_when_bridge_thread_exceeds_deadline() -> None:
    async def _invoke_timeout() -> None:
        with (
            patch(
                f"{_ADAPTER_MODULE}._THREAD_BRIDGE_TIMEOUT_SECONDS",
                0.01,
            ),
            pytest.raises(TimeoutError, match="timed out"),
        ):
            ArtanaDictionarySearchHarnessAdapter._run_coroutine(asyncio.sleep(0.1))

    asyncio.run(_invoke_timeout())
