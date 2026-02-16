"""
State backend management for Flujo.

Provides thread-safe singleton management of the Flujo state backend
to ensure consistent state handling across the application.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard

from flujo.application.core.runtime.factories import BackendFactory
from flujo.domain.agent_result import FlujoAgentResult
from flujo.utils.serialization import register_custom_serializer

from src.infrastructure.llm.config.flujo_config import resolve_flujo_state_uri
from src.type_definitions.common import JSONValue  # noqa: TC001
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from flujo.state.backends.base import StateBackend

logger = logging.getLogger(__name__)


@dataclass
class _StateBackendHolder:
    """Thread-safe holder for the state backend singleton."""

    value: StateBackend | None = None


_STATE_BACKEND_LOCK = threading.Lock()
_STATE_BACKEND_HOLDER = _StateBackendHolder()
_STATE_BACKEND_FACTORY = BackendFactory()
_SERIALIZER_REGISTRATION_LOCK = threading.Lock()
_SERIALIZER_REGISTRATION_STATE = {"registered": False}
_MAX_WORKFLOW_STATE_DECODE_DEPTH = 3


class _StateBackendWithNormalization:
    """Proxy that normalizes legacy string-encoded workflow state fields."""

    def __init__(self, backend: StateBackend) -> None:
        self._backend = backend

    async def load_state(self, run_id: str) -> object:
        loaded_state = await self._backend.load_state(run_id)
        return _normalize_loaded_workflow_state(loaded_state)

    def __getattr__(self, name: str) -> object:
        return getattr(self._backend, name)


def _decode_nested_json_string(value: object) -> object:
    decoded: object = value
    for _ in range(_MAX_WORKFLOW_STATE_DECODE_DEPTH):
        if not isinstance(decoded, str):
            break
        candidate = decoded.strip()
        if not candidate:
            return decoded
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            break
    return decoded


def _coerce_json_object(value: object) -> dict[str, JSONValue]:
    decoded = _decode_nested_json_string(value)
    if not isinstance(decoded, dict):
        return {}
    return {str(key): to_json_value(item) for key, item in decoded.items()}


def _coerce_json_list(value: object) -> list[JSONValue]:
    decoded = _decode_nested_json_string(value)
    if not isinstance(decoded, list):
        return []
    return [to_json_value(item) for item in decoded]


def _normalize_loaded_workflow_state(state: object) -> object:
    if not isinstance(state, dict):
        return state

    normalized_state: dict[str, object] = dict(state)
    normalized_state["pipeline_context"] = _coerce_json_object(
        state.get("pipeline_context"),
    )
    normalized_state["step_history"] = _coerce_json_list(state.get("step_history"))
    normalized_state["metadata"] = _coerce_json_object(state.get("metadata"))
    return normalized_state


def _serialize_flujo_agent_result(result: FlujoAgentResult) -> dict[str, JSONValue]:
    usage_payload: dict[str, JSONValue] | None = None
    usage = result.usage()
    if usage is not None:
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        usage_cost = getattr(usage, "cost_usd", None)
        usage_payload = {
            "input_tokens": (
                int(input_tokens) if isinstance(input_tokens, int | float) else 0
            ),
            "output_tokens": (
                int(output_tokens) if isinstance(output_tokens, int | float) else 0
            ),
            "cost_usd": (
                float(usage_cost) if isinstance(usage_cost, int | float) else None
            ),
        }

    serialized: dict[str, JSONValue] = {
        "output": to_json_value(result.output),
        "usage": to_json_value(usage_payload),
        "cost_usd": (
            float(result.cost_usd) if isinstance(result.cost_usd, int | float) else None
        ),
        "token_counts": (
            int(result.token_counts)
            if isinstance(result.token_counts, int | float)
            else None
        ),
    }
    return serialized


def _register_custom_serializers() -> None:
    with _SERIALIZER_REGISTRATION_LOCK:
        if _SERIALIZER_REGISTRATION_STATE["registered"]:
            return
        register_custom_serializer(
            FlujoAgentResult,
            _serialize_flujo_agent_result,
        )
        _SERIALIZER_REGISTRATION_STATE["registered"] = True


def _build_state_backend() -> StateBackend:
    """Build a new state backend instance."""
    state_uri = resolve_flujo_state_uri()
    _register_custom_serializers()
    os.environ["FLUJO_STATE_URI"] = state_uri
    logger.info("Initializing Flujo state backend with URI: %s", _mask_uri(state_uri))
    raw_backend = _STATE_BACKEND_FACTORY.create_state_backend()
    normalized_backend = _StateBackendWithNormalization(raw_backend)
    if _is_state_backend(normalized_backend):
        return normalized_backend
    msg = "State backend does not satisfy StateBackend protocol after normalization"
    raise TypeError(msg)


def _mask_uri(uri: str) -> str:
    """Mask sensitive parts of the URI for logging."""
    if "://" not in uri or "@" not in uri:
        return uri

    # Mask password in postgresql://user:pass@host/db
    scheme, _, rest = uri.partition("://")
    if not rest or "@" not in rest:
        return uri

    auth_part, _, host_part = rest.rpartition("@")
    if ":" in auth_part:
        user = auth_part.split(":")[0]
        return f"{scheme}://{user}:***@{host_part}"

    return uri


def _is_state_backend(value: object) -> TypeGuard[StateBackend]:
    required_methods = (
        "save_state",
        "load_state",
        "delete_state",
        "get_trace",
        "save_trace",
        "persist_evaluation",
        "list_evaluations",
        "save_run_start",
        "save_step_result",
        "save_run_end",
        "get_run_details",
        "list_runs",
        "list_run_steps",
        "set_system_state",
        "get_system_state",
    )
    return all(
        callable(getattr(value, method_name, None)) for method_name in required_methods
    )


def get_state_backend() -> StateBackend:
    """
    Get the singleton state backend instance.

    Thread-safe lazy initialization ensures only one backend
    is created regardless of concurrent access.

    Returns:
        The shared StateBackend instance
    """
    existing = _STATE_BACKEND_HOLDER.value
    if existing is not None:
        return existing

    with _STATE_BACKEND_LOCK:
        existing = _STATE_BACKEND_HOLDER.value
        if existing is None:
            existing = _build_state_backend()
            _STATE_BACKEND_HOLDER.value = existing
        return existing


def reset_state_backend() -> None:
    """
    Reset the state backend singleton.

    Use for testing or when reconfiguring the backend.
    Should not be called during normal operation.
    """
    with _STATE_BACKEND_LOCK:
        _STATE_BACKEND_HOLDER.value = None


class StateBackendManager:
    """
    Manager for Flujo state backend with lifecycle support.

    Provides explicit lifecycle management for the state backend
    to ensure proper cleanup during application shutdown.
    """

    def __init__(self) -> None:
        """Initialize the manager."""
        self._backend: StateBackend | None = None

    @property
    def backend(self) -> StateBackend:
        """
        Get the managed state backend.

        Lazily initializes the backend on first access.
        """
        if self._backend is None:
            self._backend = get_state_backend()
        return self._backend

    async def close(self) -> None:
        """
        Close the state backend and release resources.

        Should be called during application shutdown.
        """
        if self._backend is not None:
            try:
                # Attempt to close if the backend supports it
                if hasattr(self._backend, "close"):
                    await self._backend.close()
                elif hasattr(self._backend, "aclose"):
                    await self._backend.aclose()
            except (RuntimeError, OSError, ConnectionError) as exc:
                logger.warning("Error closing state backend: %s", exc)
            finally:
                self._backend = None
