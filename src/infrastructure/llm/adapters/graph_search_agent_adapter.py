"""Artana-based adapter for graph-search agent operations."""

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_search_port import GraphSearchPort
from src.infrastructure.llm.adapters._artana_step_helpers import (
    run_single_step_with_policy,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
    resolve_artana_state_uri,
)
from src.infrastructure.llm.prompts.graph_search import GRAPH_SEARCH_SYSTEM_PROMPT

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_search_context import GraphSearchContext

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import ModelResult, ModelUsage
    from artana.store import PostgresStore, SQLiteStore
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc


def _normalize_openai_model_id(model_id: str) -> str:
    if model_id.startswith("openai:"):
        return model_id.split(":", 1)[1]
    return model_id


def _to_int(raw_value: object, *, default: int = 0) -> int:
    if isinstance(raw_value, bool):
        return default
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError:
            return default
    return default


def _join_message_text(messages: object) -> str:
    if not isinstance(messages, list):
        return ""
    lines: list[str] = []
    for message in messages:
        role = getattr(message, "role", "user")
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def _extract_prompt(request: object) -> str:
    prompt = getattr(request, "prompt", None)
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()

    input_payload = getattr(request, "input", None)
    input_prompt = getattr(input_payload, "prompt", None)
    if isinstance(input_prompt, str) and input_prompt.strip():
        return input_prompt.strip()

    messages = getattr(request, "messages", None)
    joined_messages = _join_message_text(messages)
    if joined_messages:
        return joined_messages

    return ""


class _OpenAIChatModelPort:
    """Minimal Artana model port backed by OpenAI Chat Completions."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _resolve_openai_api_key() -> str | None:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
        if raw_value is None:
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        if normalized.lower() in _INVALID_OPENAI_KEYS:
            return None
        return normalized

    async def _http_client(self) -> httpx.AsyncClient:
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_seconds)
            self._client = client
        return client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def complete(self, request: object) -> object:
        api_key = self._resolve_openai_api_key()
        if api_key is None:
            msg = "OPENAI_API_KEY (or ARTANA_OPENAI_API_KEY) is not configured."
            raise RuntimeError(msg)

        output_schema = getattr(request, "output_schema", None)
        if not isinstance(output_schema, type) or not issubclass(
            output_schema,
            BaseModel,
        ):
            msg = "Artana model request output_schema must be a Pydantic BaseModel."
            raise TypeError(msg)

        prompt = _extract_prompt(request)
        if not prompt:
            msg = "Artana model request is missing prompt/messages content."
            raise ValueError(msg)

        requested_model = str(getattr(request, "model", "openai:gpt-5-mini"))
        openai_model = _normalize_openai_model_id(requested_model)
        schema_name = output_schema.__name__.lower() or "graph_search_contract"
        payload = {
            "model": openai_model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": _ensure_openai_strict_json_schema(
                        output_schema.model_json_schema(),
                    ),
                    "strict": True,
                },
            },
        }

        client = await self._http_client()
        response = await client.post(
            _OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        body = response.json()

        choices = body.get("choices", [])
        if not isinstance(choices, list) or not choices:
            msg = "OpenAI response did not include choices."
            raise ValueError(msg)
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            msg = "OpenAI response choice payload is invalid."
            raise TypeError(msg)
        message = first_choice.get("message", {})
        if not isinstance(message, dict):
            msg = "OpenAI response message payload is invalid."
            raise TypeError(msg)
        content = message.get("content", "")
        if not isinstance(content, str):
            msg = "OpenAI response message content is not text."
            raise TypeError(msg)
        parsed_payload = __import__("json").loads(content)
        output = output_schema.model_validate(parsed_payload)

        usage_raw = body.get("usage", {})
        if not isinstance(usage_raw, dict):
            usage_raw = {}
        usage = ModelUsage(
            prompt_tokens=_to_int(usage_raw.get("prompt_tokens")),
            completion_tokens=_to_int(usage_raw.get("completion_tokens")),
            cost_usd=0.0,
        )
        return ModelResult(output=output, usage=usage)


def _normalize_openai_json_schema_node(node: object) -> object:
    if isinstance(node, dict):
        normalized = {
            str(key): _normalize_openai_json_schema_node(value)
            for key, value in node.items()
        }
        properties_payload = normalized.get("properties")
        raw_type = normalized.get("type")
        is_object_type = raw_type == "object" or (
            isinstance(raw_type, list) and "object" in raw_type
        )
        has_properties = isinstance(properties_payload, dict)
        additional_properties_payload = normalized.get("additionalProperties")
        is_map_object = (
            is_object_type
            and not has_properties
            and isinstance(additional_properties_payload, dict)
        )
        if is_map_object:
            normalized["properties"] = {}
            normalized["required"] = []
            normalized["additionalProperties"] = False
            return normalized
        if (
            has_properties
            or is_object_type
            and "additionalProperties" not in normalized
        ):
            normalized["additionalProperties"] = False
        if isinstance(properties_payload, dict):
            normalized["required"] = [str(key) for key in properties_payload]
        elif "required" in normalized:
            normalized.pop("required", None)
        return normalized
    if isinstance(node, list):
        return [_normalize_openai_json_schema_node(item) for item in node]
    return node


def _ensure_openai_strict_json_schema(schema: object) -> dict[str, object]:
    if not isinstance(schema, dict):
        msg = "Expected JSON schema dictionary."
        raise TypeError(msg)
    normalized = _normalize_openai_json_schema_node(schema)
    if not isinstance(normalized, dict):
        msg = "Normalized JSON schema must remain a dictionary."
        raise TypeError(msg)
    return {str(key): value for key, value in normalized.items()}


class ArtanaGraphSearchAdapter(GraphSearchPort):
    """Adapter that executes graph-search workflows through Artana."""

    def __init__(
        self,
        model: str | None = None,
        *,
        graph_query_service: object | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for graph search execution. Install dependency "
                "'artana @ git+https://github.com/aandresalvarez/artana-kernel.git@main'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._graph_query_service = graph_query_service
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        timeout_seconds = self._resolve_timeout_seconds(model)
        self._model_port = _OpenAIChatModelPort(timeout_seconds=timeout_seconds)
        self._kernel = ArtanaKernel(
            store=self._create_store(),
            model_port=self._model_port,
        )
        self._client = SingleStepModelClient(kernel=self._kernel)

    async def search(
        self,
        context: GraphSearchContext,
        *,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        self._last_run_id = None

        if not self._has_openai_key():
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search agent API key is not configured.",
            )

        if self._graph_query_service is None:
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search tools are unavailable.",
            )

        effective_model = self._resolve_model_id(model_id)
        run_id = self._create_run_id(
            model_id=effective_model,
            research_space_id=context.research_space_id,
            question=context.question,
        )
        self._last_run_id = run_id

        try:
            usage_limits = self._governance.usage_limits
            budget_limit = (
                usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
            )
            tenant = self._create_tenant(
                tenant_id=context.research_space_id,
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            result = await run_single_step_with_policy(
                self._client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(context),
                output_schema=GraphSearchContract,
                step_key="graph.search.v1",
                replay_policy=self._runtime_policy.replay_policy,
            )
            output = result.output
            contract = (
                output
                if isinstance(output, GraphSearchContract)
                else GraphSearchContract.model_validate(output)
            )
            return contract.model_copy(
                update={
                    "research_space_id": context.research_space_id,
                    "original_query": context.question,
                    "total_results": len(contract.results),
                    "executed_path": "agent",
                    "agent_run_id": contract.agent_run_id or run_id,
                },
            )
        except Exception:  # noqa: BLE001
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search agent execution failed.",
            )

    async def close(self) -> None:
        await self._model_port.aclose()
        await self._kernel.close()

    @staticmethod
    def _has_openai_key() -> bool:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
        if raw_value is None:
            return False
        normalized = raw_value.strip()
        if not normalized:
            return False
        return normalized.lower() not in _INVALID_OPENAI_KEYS

    def _resolve_model_id(self, model_id: str | None) -> str:
        if (
            self._registry.allow_runtime_model_overrides()
            and model_id is not None
            and self._registry.validate_model_for_capability(
                model_id,
                ModelCapability.QUERY_GENERATION,
            )
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.QUERY_GENERATION,
        ).model_id

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
            return float(default_spec.timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    @staticmethod
    def _create_store() -> object:
        state_uri = resolve_artana_state_uri()
        if state_uri.startswith("sqlite:///"):
            sqlite_path = state_uri.removeprefix("sqlite:///")
            if not sqlite_path:
                sqlite_path = "artana_state.db"
            return SQLiteStore(sqlite_path)
        if state_uri.startswith("postgresql://"):
            return PostgresStore(state_uri)
        msg = f"Unsupported ARTANA_STATE_URI scheme: {state_uri}"
        raise ValueError(msg)

    @staticmethod
    def _create_run_id(*, model_id: str, research_space_id: str, question: str) -> str:
        payload = f"{model_id}|{research_space_id}|{question.strip()}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"graph_search:{digest}"

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _build_input_text(context: GraphSearchContext) -> str:
        return (
            f"QUESTION: {context.question}\n"
            f"RESEARCH SPACE ID: {context.research_space_id}\n"
            f"MAX DEPTH: {context.max_depth}\n"
            f"TOP K: {context.top_k}\n"
            f"INCLUDE EVIDENCE CHAINS: {context.include_evidence_chains}\n"
            f"FORCE AGENT: {context.force_agent}\n"
        )

    def _build_prompt(self, context: GraphSearchContext) -> str:
        return (
            f"{GRAPH_SEARCH_SYSTEM_PROMPT}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"{self._build_input_text(context)}"
        )

    def _fallback_contract(
        self,
        context: GraphSearchContext,
        *,
        decision: Literal["fallback", "escalate"],
        reason: str,
    ) -> GraphSearchContract:
        return GraphSearchContract(
            decision=decision,
            confidence_score=0.35 if decision == "fallback" else 0.05,
            rationale=reason,
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-search:{context.research_space_id}",
                    excerpt=reason,
                    relevance=0.4 if decision == "fallback" else 0.1,
                ),
            ],
            research_space_id=context.research_space_id,
            original_query=context.question,
            interpreted_intent=context.question,
            query_plan_summary="Graph-search adapter fallback.",
            total_results=0,
            results=[],
            executed_path="agent_fallback",
            warnings=[reason],
            agent_run_id=self._last_run_id,
        )


__all__ = ["ArtanaGraphSearchAdapter"]
