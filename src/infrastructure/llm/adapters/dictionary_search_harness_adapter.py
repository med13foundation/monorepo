"""Artana workflow harness for staged dictionary search orchestration."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine  # noqa: TC003
from dataclasses import dataclass
from threading import Thread
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
from src.domain.agents.contracts.mapping_judge import MappingJudgeCandidate
from src.domain.agents.models import ModelCapability
from src.domain.entities.kernel.dictionary import DictionarySearchResult
from src.domain.ports.dictionary_search_harness_port import DictionarySearchHarnessPort
from src.infrastructure.llm.adapters._artana_step_helpers import (
    run_single_step_with_policy,
    stable_sha256_digest,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    OpenAIJSONSchemaModelPort,
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
    resolve_artana_state_uri,
)

if TYPE_CHECKING:
    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.ports.text_embedding_port import TextEmbeddingPort
    from src.domain.repositories.kernel.dictionary_repository import (
        DictionaryRepository,
    )

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel, WorkflowContext
    from artana.models import TenantContext
    from artana.store import PostgresStore
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_DETERMINISTIC_MATCH_METHODS: frozenset[str] = frozenset({"exact", "synonym"})
_JUDGE_MATCH_METHODS: frozenset[str] = frozenset({"fuzzy", "vector"})
_JUDGE_CANDIDATE_FLOOR = 0.4
_JUDGE_AMBIGUITY_DELTA = 0.08
_JUDGE_MAX_CANDIDATES = 5
_JUDGE_MIN_CANDIDATES = 2
_PROMPT_RESULT_PREVIEW_LIMIT = 8


class _PlannerContract(BaseModel):
    action: Literal["stop", "vector_original", "vector_custom"]
    custom_terms: list[str] = Field(default_factory=list, max_length=8)
    rationale: str = Field(..., min_length=1, max_length=4000)


class _DirectSearchArgs(BaseModel):
    terms: list[str]
    dimensions: list[str] | None = None
    domain_context: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    include_inactive: bool = False


class _VectorSearchArgs(BaseModel):
    terms: list[str]
    dimensions: list[str] | None = None
    domain_context: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    include_inactive: bool = False


@dataclass(frozen=True)
class _PlannerInput:
    terms: list[str]
    dimensions: list[str] | None
    domain_context: str | None
    direct_hits: list[DictionarySearchResult]


@dataclass(frozen=True)
class _HarnessResult:
    results: list[dict[str, object]]


class ArtanaDictionarySearchHarnessAdapter(DictionarySearchHarnessPort):
    """Artana workflow that selects direct/vector/custom-query search strategy."""

    def __init__(
        self,
        *,
        dictionary_repo: DictionaryRepository,
        embedding_provider: TextEmbeddingPort | None,
        mapping_judge_agent: MappingJudgePort | None = None,
        model: str | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for dictionary harness execution. Install "
                "'artana @ git+https://github.com/aandresalvarez/artana-kernel.git@main'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._dictionary = dictionary_repo
        self._embedding_provider = embedding_provider
        self._mapping_judge_agent = mapping_judge_agent
        self._default_model = model
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._model_port: OpenAIJSONSchemaModelPort | None = None
        self._kernel: ArtanaKernel | None = None
        self._client: SingleStepModelClient | None = None

    def search(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        normalized_terms = self._normalize_terms(terms)
        if not normalized_terms:
            return []
        normalized_dimensions = self._normalize_dimensions(dimensions)
        direct_hits = self._dictionary.search_dictionary(
            terms=normalized_terms,
            dimensions=normalized_dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=None,
            include_inactive=include_inactive,
        )
        if self._has_deterministic_hits(direct_hits):
            return direct_hits
        if not self._has_openai_key():
            return direct_hits

        run_id = self._create_run_id(
            terms=normalized_terms,
            dimensions=normalized_dimensions,
            domain_context=domain_context,
            limit=limit,
            include_inactive=include_inactive,
        )
        kernel, client = self._ensure_runtime()

        async def workflow(ctx: WorkflowContext) -> _HarnessResult:
            plan = await self._plan_strategy(
                client=client,
                run_id=ctx.run_id,
                tenant=ctx.tenant,
                planner_input=_PlannerInput(
                    terms=normalized_terms,
                    dimensions=normalized_dimensions,
                    domain_context=domain_context,
                    direct_hits=direct_hits,
                ),
            )
            if plan.action == "stop":
                return _HarnessResult(
                    results=self._apply_mapping_judge(
                        terms=normalized_terms,
                        dimensions=normalized_dimensions,
                        domain_context=domain_context,
                        results=direct_hits,
                    ),
                )

            tool_name = "dictionary_vector_search"
            step_key = "dictionary.search.vector.original.v1"
            vector_terms = normalized_terms
            if plan.action == "vector_custom":
                normalized_custom_terms = self._normalize_terms(plan.custom_terms)
                if not normalized_custom_terms:
                    msg = "Planner selected vector_custom without valid custom_terms."
                    raise ValueError(msg)
                vector_terms = normalized_custom_terms
                tool_name = "dictionary_vector_custom_search"
                step_key = "dictionary.search.vector.custom.v1"

            vector_result = await kernel.step_tool(
                run_id=ctx.run_id,
                tenant=ctx.tenant,
                tool_name=tool_name,
                arguments=_VectorSearchArgs(
                    terms=vector_terms,
                    dimensions=normalized_dimensions,
                    domain_context=domain_context,
                    limit=limit,
                    include_inactive=include_inactive,
                ),
                step_key=step_key,
            )
            vector_hits = self._decode_results(vector_result.result_json)
            return _HarnessResult(
                results=self._apply_mapping_judge(
                    terms=normalized_terms,
                    dimensions=normalized_dimensions,
                    domain_context=domain_context,
                    results=vector_hits,
                ),
            )

        outcome = self._run_coroutine(
            kernel.run_workflow(
                run_id=run_id,
                tenant=self._create_tenant(),
                workflow=workflow,
            ),
        )
        status = getattr(outcome, "status", None)
        output = getattr(outcome, "output", None)
        if status != "complete" or not isinstance(output, _HarnessResult):
            msg = f"Dictionary search harness did not complete for run_id={run_id}."
            raise RuntimeError(msg)
        return [DictionarySearchResult.model_validate(item) for item in output.results]

    def close(self) -> None:
        if self._kernel is None or self._model_port is None:
            return
        self._run_void_coroutine(self._close_async())

    async def _close_async(self) -> None:
        model_port = self._model_port
        kernel = self._kernel
        self._model_port = None
        self._kernel = None
        self._client = None
        if model_port is not None:
            await model_port.aclose()
        if kernel is not None:
            await kernel.close()

    def _ensure_runtime(self) -> tuple[ArtanaKernel, SingleStepModelClient]:
        kernel = self._kernel
        client = self._client
        if kernel is not None and client is not None:
            return kernel, client

        model_port = OpenAIJSONSchemaModelPort(
            timeout_seconds=self._resolve_timeout_seconds(self._default_model),
            schema_name_fallback="dictionary_search_plan",
        )
        kernel = ArtanaKernel(
            store=self._create_store(),
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        self._model_port = model_port
        self._kernel = kernel
        self._client = client
        self._register_tools(kernel)
        return kernel, client

    def _register_tools(self, kernel: ArtanaKernel) -> None:
        @kernel.tool()
        async def dictionary_direct_search(  # noqa: ANN202
            terms: list[str],
            dimensions: list[str] | None = None,
            domain_context: str | None = None,
            limit: int = 50,
            *,
            include_inactive: bool = False,
        ) -> str:
            results = self._dictionary.search_dictionary(
                terms=terms,
                dimensions=dimensions,
                domain_context=domain_context,
                limit=limit,
                query_embeddings=None,
                include_inactive=include_inactive,
            )
            return json.dumps(self._dump_results(results))

        @kernel.tool()
        async def dictionary_vector_search(  # noqa: ANN202
            terms: list[str],
            dimensions: list[str] | None = None,
            domain_context: str | None = None,
            limit: int = 50,
            *,
            include_inactive: bool = False,
        ) -> str:
            return self._vector_search_payload(
                terms=terms,
                dimensions=dimensions,
                domain_context=domain_context,
                limit=limit,
                include_inactive=include_inactive,
            )

        @kernel.tool()
        async def dictionary_vector_custom_search(  # noqa: ANN202
            terms: list[str],
            dimensions: list[str] | None = None,
            domain_context: str | None = None,
            limit: int = 50,
            *,
            include_inactive: bool = False,
        ) -> str:
            return self._vector_search_payload(
                terms=terms,
                dimensions=dimensions,
                domain_context=domain_context,
                limit=limit,
                include_inactive=include_inactive,
            )

    def _vector_search_payload(  # noqa: PLR0913
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None,
        domain_context: str | None,
        limit: int,
        include_inactive: bool,
    ) -> str:
        if self._embedding_provider is None:
            msg = "Vector search requires an embedding provider."
            raise RuntimeError(msg)
        query_embeddings = self._build_query_embeddings(terms)
        if query_embeddings is None:
            return json.dumps([])
        results = self._dictionary.search_dictionary(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=query_embeddings,
            include_inactive=include_inactive,
        )
        return json.dumps(self._dump_results(results))

    async def _plan_strategy(
        self,
        *,
        client: SingleStepModelClient,
        run_id: str,
        tenant: TenantContext,
        planner_input: _PlannerInput,
    ) -> _PlannerContract:
        prompt = self._build_planner_prompt(
            terms=planner_input.terms,
            dimensions=planner_input.dimensions,
            domain_context=planner_input.domain_context,
            direct_hits=planner_input.direct_hits,
        )
        model_id = self._resolve_model_id()
        step_result = await run_single_step_with_policy(
            client,
            run_id=run_id,
            tenant=tenant,
            model=model_id,
            prompt=prompt,
            output_schema=_PlannerContract,
            step_key="dictionary.search.plan.v1",
            replay_policy=self._runtime_policy.replay_policy,
            context_version=self._runtime_policy.to_context_version(),
        )
        output = step_result.output
        if isinstance(output, _PlannerContract):
            return output
        return _PlannerContract.model_validate(output)

    @staticmethod
    def _normalize_terms(terms: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for term in terms:
            value = term.strip()
            if not value:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(value)
        return normalized

    @staticmethod
    def _normalize_dimensions(dimensions: list[str] | None) -> list[str] | None:
        if dimensions is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for dimension in dimensions:
            value = dimension.strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized if normalized else None

    def _build_query_embeddings(
        self,
        terms: list[str],
    ) -> dict[str, list[float]] | None:
        if self._embedding_provider is None:
            return None
        normalized_terms = [term.casefold() for term in terms]
        embedded_terms = self._embedding_provider.embed_texts(
            normalized_terms,
            model_name=self._resolve_embedding_model(),
        )
        embeddings: dict[str, list[float]] = {}
        for index, term in enumerate(normalized_terms):
            embedding = embedded_terms[index]
            if embedding is None:
                continue
            embeddings[term] = embedding
        return embeddings or None

    @staticmethod
    def _decode_results(payload: str) -> list[DictionarySearchResult]:
        parsed = json.loads(payload)
        if not isinstance(parsed, list):
            msg = "Dictionary search tool returned invalid payload."
            raise TypeError(msg)
        return [DictionarySearchResult.model_validate(item) for item in parsed]

    @staticmethod
    def _dump_results(results: list[DictionarySearchResult]) -> list[dict[str, object]]:
        return [result.model_dump(mode="json") for result in results]

    @staticmethod
    def _has_deterministic_hits(results: list[DictionarySearchResult]) -> bool:
        return any(
            result.match_method in _DETERMINISTIC_MATCH_METHODS for result in results
        )

    def _apply_mapping_judge(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None,
        domain_context: str | None,
        results: list[DictionarySearchResult],
    ) -> list[dict[str, object]]:
        if not self._has_openai_key():
            return self._dump_results(results)
        if dimensions is not None and "variables" not in dimensions:
            return self._dump_results(results)
        if self._has_deterministic_hits(results):
            return self._dump_results(results)
        candidates = self._build_judge_candidates(results)
        if not self._should_invoke_judge(candidates):
            return self._dump_results(results)
        context = MappingJudgeContext(
            field_key=terms[0][:512],
            field_value_preview=" | ".join(terms)[:2000],
            source_id="dictionary_search",
            source_type="dictionary",
            domain_context=domain_context,
            record_metadata={
                "terms": terms,
                "dimensions": (
                    dimensions
                    if dimensions is not None
                    else ["variables", "entity_types", "relation_types", "constraints"]
                ),
            },
            candidates=candidates,
            request_source="dictionary_search_harness",
        )
        decision = self._resolve_mapping_judge_agent().judge(context)
        if decision.decision != "matched" or decision.selected_variable_id is None:
            return self._dump_results(results)
        selected_id = decision.selected_variable_id
        reordered: list[DictionarySearchResult] = []
        selected: DictionarySearchResult | None = None
        for result in results:
            if result.dimension == "variables" and result.entry_id == selected_id:
                selected = result
                continue
            reordered.append(result)
        if selected is not None:
            reordered.insert(0, selected)
        return self._dump_results(reordered)

    @staticmethod
    def _build_judge_candidates(
        results: list[DictionarySearchResult],
    ) -> list[MappingJudgeCandidate]:
        ranked = sorted(
            (
                result
                for result in results
                if result.dimension == "variables"
                and result.match_method in _JUDGE_MATCH_METHODS
                and result.similarity_score >= _JUDGE_CANDIDATE_FLOOR
            ),
            key=lambda item: item.similarity_score,
            reverse=True,
        )
        return [
            MappingJudgeCandidate(
                variable_id=result.entry_id,
                display_name=result.display_name,
                match_method=result.match_method,
                similarity_score=result.similarity_score,
                description=result.description,
                metadata=result.metadata,
            )
            for result in ranked[:_JUDGE_MAX_CANDIDATES]
        ]

    @staticmethod
    def _should_invoke_judge(candidates: list[MappingJudgeCandidate]) -> bool:
        if len(candidates) < _JUDGE_MIN_CANDIDATES:
            return False
        return (
            abs(candidates[0].similarity_score - candidates[1].similarity_score)
            <= _JUDGE_AMBIGUITY_DELTA
        )

    def _resolve_model_id(self) -> str:
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.QUERY_GENERATION,
        ).model_id

    @staticmethod
    def _resolve_embedding_model() -> str:
        return _DEFAULT_EMBEDDING_MODEL

    def _resolve_timeout_seconds(self, model: str | None) -> float:
        if model:
            try:
                model_spec = self._registry.get_model(model)
                return float(model_spec.timeout_seconds)
            except (KeyError, ValueError):
                pass
        try:
            default_spec = self._registry.get_default_model(
                ModelCapability.QUERY_GENERATION,
            )
        except (KeyError, ValueError):
            return 60.0
        return float(default_spec.timeout_seconds)

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    def _resolve_mapping_judge_agent(self) -> MappingJudgePort:
        agent = self._mapping_judge_agent
        if agent is not None:
            return agent
        from src.infrastructure.llm.adapters.mapping_judge_agent_adapter import (
            ArtanaMappingJudgeAdapter,
        )

        agent = ArtanaMappingJudgeAdapter()
        self._mapping_judge_agent = agent
        return agent

    @staticmethod
    def _create_store() -> PostgresStore:
        state_uri = resolve_artana_state_uri()
        if state_uri.startswith("postgresql://"):
            return PostgresStore(state_uri)
        msg = f"Unsupported ARTANA_STATE_URI scheme: {state_uri}"
        raise ValueError(msg)

    def _create_tenant(self) -> TenantContext:
        budget = self._governance.usage_limits.total_cost_usd or 1.0
        return TenantContext(
            tenant_id="dictionary_search_harness",
            capabilities=frozenset(),
            budget_usd_limit=max(float(budget), 0.01),
        )

    def _create_run_id(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None,
        domain_context: str | None,
        limit: int,
        include_inactive: bool,
    ) -> str:
        payload = json.dumps(
            {
                "terms": terms,
                "dimensions": dimensions,
                "domain_context": domain_context,
                "limit": limit,
                "include_inactive": include_inactive,
            },
            sort_keys=True,
        )
        digest = stable_sha256_digest(payload)
        return f"dictionary_search:{digest}"

    def _build_planner_prompt(
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None,
        domain_context: str | None,
        direct_hits: list[DictionarySearchResult],
    ) -> str:
        top_hits = direct_hits[:_PROMPT_RESULT_PREVIEW_LIMIT]
        lines = [
            (
                f"- id={hit.entry_id}; dim={hit.dimension}; method={hit.match_method}; "
                f"score={hit.similarity_score:.3f}; name={hit.display_name}"
            )
            for hit in top_hits
        ]
        rendered_hits = "\n".join(lines) if lines else "- none"
        return (
            "You are the Dictionary Search Strategy Planner.\n"
            "Select the cheapest valid next action.\n\n"
            "Allowed actions:\n"
            "- stop: keep direct search results.\n"
            "- vector_original: run vector search using original terms.\n"
            "- vector_custom: run vector search with rewritten terms.\n\n"
            "Rules:\n"
            "- Prefer stop when direct hits are likely sufficient.\n"
            "- Use vector_original when terms are semantically clear but lexical misses.\n"
            "- Use vector_custom only when query rewrite is likely needed.\n"
            "- For vector_custom, return 1-5 concise custom_terms.\n\n"
            f"Terms: {terms}\n"
            f"Dimensions: {dimensions}\n"
            f"Domain: {domain_context}\n"
            f"Direct hits:\n{rendered_hits}\n"
        )

    @staticmethod
    def _run_coroutine(coroutine: Coroutine[object, object, object]) -> object:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result_holder: list[object] = []
        error_holder: dict[str, BaseException | None] = {"error": None}

        def _target() -> None:
            try:
                result_holder.append(asyncio.run(coroutine))
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        thread = Thread(target=_target, daemon=True)
        thread.start()
        thread.join()

        if error_holder["error"] is not None:
            raise error_holder["error"]
        if not result_holder:
            msg = "Coroutine returned no result."
            raise RuntimeError(msg)
        return result_holder[0]

    @staticmethod
    def _run_void_coroutine(coroutine: Coroutine[object, object, object]) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coroutine)
            return

        error_holder: dict[str, BaseException | None] = {"error": None}

        def _target() -> None:
            try:
                asyncio.run(coroutine)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        thread = Thread(target=_target, daemon=True)
        thread.start()
        thread.join()
        if error_holder["error"] is not None:
            raise error_holder["error"]


__all__ = ["ArtanaDictionarySearchHarnessAdapter"]
