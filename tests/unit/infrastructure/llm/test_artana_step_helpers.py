"""Tests for shared Artana step helper behavior."""

from __future__ import annotations

import pytest

from src.infrastructure.llm.adapters._artana_step_helpers import (
    run_single_step_with_policy,
)


class _StubResult:
    def __init__(self, output: object) -> None:
        self.output = output


class _StubClient:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, object] | None = None

    async def step(self, **kwargs: object) -> _StubResult:
        self.last_kwargs = kwargs
        return _StubResult(output={"ok": True})


@pytest.mark.asyncio
async def test_run_single_step_with_policy_passes_context_version() -> None:
    client = _StubClient()
    context_version = {"system_prompt_hash": "abc123"}

    await run_single_step_with_policy(
        client,
        run_id="run-1",
        tenant={"tenant_id": "space-1"},
        model="gpt-5",
        prompt="prompt",
        output_schema=dict,
        step_key="test.step",
        replay_policy="strict",
        context_version=context_version,
    )

    assert client.last_kwargs is not None
    assert client.last_kwargs["replay_policy"] == "strict"
    assert client.last_kwargs["context_version"] == context_version


@pytest.mark.asyncio
async def test_run_single_step_with_policy_omits_context_version_when_none() -> None:
    client = _StubClient()

    await run_single_step_with_policy(
        client,
        run_id="run-2",
        tenant={"tenant_id": "space-2"},
        model="gpt-5",
        prompt="prompt",
        output_schema=dict,
        step_key="test.step",
        replay_policy="allow_prompt_drift",
        context_version=None,
    )

    assert client.last_kwargs is not None
    assert client.last_kwargs["replay_policy"] == "allow_prompt_drift"
    assert "context_version" not in client.last_kwargs
