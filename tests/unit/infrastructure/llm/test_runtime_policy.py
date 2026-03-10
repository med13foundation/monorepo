"""Tests for runtime replay/context policy loading."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.llm.config.runtime_policy import load_runtime_policy

if TYPE_CHECKING:
    from pathlib import Path


def test_load_runtime_policy_defaults_to_fork_on_drift_when_missing(
    tmp_path: Path,
) -> None:
    missing_config_path = tmp_path / "missing-artana.toml"
    load_runtime_policy.cache_clear()
    policy = load_runtime_policy(str(missing_config_path))
    load_runtime_policy.cache_clear()

    assert policy.replay_policy == "fork_on_drift"
    assert policy.extraction_config_version == "v1"


def test_load_runtime_policy_reads_context_version_fields(tmp_path) -> None:
    config_path = tmp_path / "artana.toml"
    config_path.write_text(
        """
[runtime]
replay_policy = "fork_on_drift"
extraction_config_version = "v9"
context_system_prompt_hash = "hash-123"
context_builder_version = "builder-v2"
context_compaction_version = "compact-v1"
""".strip(),
        encoding="utf-8",
    )

    load_runtime_policy.cache_clear()
    policy = load_runtime_policy(str(config_path))
    load_runtime_policy.cache_clear()

    assert policy.replay_policy == "fork_on_drift"
    assert policy.extraction_config_version == "v9"
    assert policy.context_system_prompt_hash == "hash-123"
    assert policy.context_builder_version == "builder-v2"
    assert policy.context_compaction_version == "compact-v1"
