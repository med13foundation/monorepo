"""Text embedding provider with OpenAI-first and deterministic fallback."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re

import httpx

from src.domain.ports import TextEmbeddingPort

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


class HybridTextEmbeddingProvider(TextEmbeddingPort):
    """Compute embeddings via OpenAI when available, otherwise locally."""

    def __init__(
        self,
        *,
        dimensions: int = 1536,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds

    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        normalized_text = text.strip()
        if not normalized_text:
            return None

        api_key = self._resolve_openai_api_key()
        if api_key is not None:
            openai_embedding = self._embed_with_openai(
                text=normalized_text,
                model_name=model_name,
                api_key=api_key,
            )
            if openai_embedding is not None:
                return openai_embedding

        return self._embed_deterministic(normalized_text)

    def _resolve_openai_api_key(self) -> str | None:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("FLUJO_OPENAI_API_KEY")
        if raw_value is None:
            return None

        normalized = raw_value.strip()
        if not normalized:
            return None
        if normalized.lower() in _INVALID_OPENAI_KEYS:
            return None
        return normalized

    def _embed_with_openai(  # noqa: PLR0911
        self,
        *,
        text: str,
        model_name: str,
        api_key: str,
    ) -> list[float] | None:
        request_payload: dict[str, object] = {
            "model": model_name,
            "input": text,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers=headers,
                    json=request_payload,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError:
            logger.exception(
                "OpenAI embedding request failed; falling back to deterministic vector",
            )
            return None

        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            return None

        first_item = data[0]
        if not isinstance(first_item, dict):
            return None
        embedding = first_item.get("embedding")
        if not isinstance(embedding, list):
            return None

        normalized = [
            float(value) for value in embedding if isinstance(value, int | float)
        ]

        if len(normalized) != self._dimensions:
            logger.warning(
                "Embedding size mismatch for model %s: expected %s, got %s",
                model_name,
                self._dimensions,
                len(normalized),
            )
            return None

        return normalized

    def _embed_deterministic(self, text: str) -> list[float]:
        """Generate a deterministic local embedding for offline/test environments."""
        vector = [0.0] * self._dimensions
        tokens = [token for token in _TOKEN_PATTERN.findall(text.lower()) if token]
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if (digest[4] % 2 == 0) else -1.0
            weight = 1.0 + ((digest[5] / 255.0) * 0.5)
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0.0:
            return vector

        return [value / norm for value in vector]


__all__ = ["HybridTextEmbeddingProvider"]
