"""Tests for OpenAI JSON-schema model port usage accounting."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    OpenAIJSONSchemaModelPort,
)


class _TestContract(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_complete_computes_usage_cost_from_token_counts() -> None:
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.headers = {}
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"answer":"ok"}',
                },
            },
        ],
        "usage": {
            "prompt_tokens": 2000,
            "completion_tokens": 500,
        },
    }

    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    port = OpenAIJSONSchemaModelPort(timeout_seconds=1.0)
    request = SimpleNamespace(
        model="openai:gpt-5-mini",
        prompt="hello",
        output_schema=_TestContract,
        metadata={},
    )

    with (
        patch.object(
            port,
            "_resolve_openai_api_key",
            return_value="sk-test-value",
        ),
        patch.object(
            port,
            "_http_client",
            AsyncMock(return_value=client),
        ),
        patch(
            "src.infrastructure.llm.costs.get_model_registry",
            return_value=MagicMock(
                get_cost_config=MagicMock(
                    return_value={
                        "prompt_tokens_per_1k": 0.00025,
                        "completion_tokens_per_1k": 0.002,
                    },
                ),
            ),
        ),
    ):
        result = await port.complete(request)

    assert result.output.answer == "ok"
    assert result.usage.prompt_tokens == 2000
    assert result.usage.completion_tokens == 500
    assert result.usage.cost_usd == 0.0015
