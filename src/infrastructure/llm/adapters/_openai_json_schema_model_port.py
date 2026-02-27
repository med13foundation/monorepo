"""Shared OpenAI JSON-schema model port for Artana adapters."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, TypeVar

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from artana.ports.model import ModelRequest, ModelResult

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OutputT = TypeVar("OutputT", bound=BaseModel)


def resolve_configured_openai_api_key() -> str | None:
    raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.lower() in _INVALID_OPENAI_KEYS:
        return None
    return normalized


def has_configured_openai_api_key() -> bool:
    return resolve_configured_openai_api_key() is not None


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


def ensure_openai_strict_json_schema(schema: object) -> dict[str, object]:
    """Normalize JSON Schema for OpenAI strict structured-output requirements."""
    if not isinstance(schema, dict):
        msg = "Expected JSON schema dictionary."
        raise TypeError(msg)
    normalized = _normalize_openai_json_schema_node(schema)
    if not isinstance(normalized, dict):
        msg = "Normalized JSON schema must remain a dictionary."
        raise TypeError(msg)
    return {str(key): value for key, value in normalized.items()}


class OpenAIJSONSchemaModelPort:
    """Minimal Artana model port backed by OpenAI Chat Completions."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        default_model: str = "openai:gpt-5-mini",
        schema_name_fallback: str = "model_contract",
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._default_model = default_model
        self._schema_name_fallback = schema_name_fallback
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _resolve_openai_api_key() -> str | None:
        return resolve_configured_openai_api_key()

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

    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        api_key = self._resolve_openai_api_key()
        if api_key is None:
            msg = "OPENAI_API_KEY (or ARTANA_OPENAI_API_KEY) is not configured."
            raise RuntimeError(msg)

        output_schema = request.output_schema
        prompt = _extract_prompt(request)
        if not prompt:
            msg = "Artana model request is missing prompt/messages content."
            raise ValueError(msg)

        requested_model = str(request.model or self._default_model)
        openai_model = _normalize_openai_model_id(requested_model)
        schema_name = output_schema.__name__.lower() or self._schema_name_fallback
        payload = {
            "model": openai_model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": ensure_openai_strict_json_schema(
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
        parsed_payload = json.loads(content)
        output = output_schema.model_validate(parsed_payload)

        usage_raw = body.get("usage", {})
        if not isinstance(usage_raw, dict):
            usage_raw = {}

        from artana.ports.model import ModelResult, ModelUsage

        usage = ModelUsage(
            prompt_tokens=_to_int(usage_raw.get("prompt_tokens")),
            completion_tokens=_to_int(usage_raw.get("completion_tokens")),
            cost_usd=0.0,
        )
        return ModelResult(output=output, usage=usage)


__all__ = [
    "OpenAIJSONSchemaModelPort",
    "ensure_openai_strict_json_schema",
    "has_configured_openai_api_key",
    "resolve_configured_openai_api_key",
]
