"""Persistent SQLite cache for embedding vectors."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from ._provider_config import env_bool

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_CACHE_PATH = Path.home() / ".cache" / "med13" / "embeddings.sqlite3"


class SqliteEmbeddingCache:
    """Simple persistent cache for embeddings keyed by deterministic hashes."""

    def __init__(self, cache_path: Path, *, dimensions: int) -> None:
        self._dimensions = dimensions
        self._lock = threading.Lock()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(cache_path),
            timeout=30.0,
            check_same_thread=False,
        )
        self._initialize_schema()

    @classmethod
    def from_environment(cls, *, dimensions: int) -> SqliteEmbeddingCache | None:
        cache_enabled = env_bool("MED13_EMBEDDING_CACHE_ENABLED", default=True)
        if not cache_enabled:
            return None

        configured_path = os.getenv("MED13_EMBEDDING_CACHE_PATH")
        cache_path = (
            Path(configured_path).expanduser()
            if configured_path and configured_path.strip()
            else _DEFAULT_EMBEDDING_CACHE_PATH
        )

        try:
            return cls(cache_path, dimensions=dimensions)
        except (OSError, sqlite3.Error):
            logger.exception(
                "Embedding cache initialization failed; continuing without cache",
            )
            return None

    def _initialize_schema(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    cache_key TEXT PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    text_sha256 TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )
            self._connection.commit()

    def get(self, cache_key: str) -> list[float] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT embedding_json FROM embedding_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

        if row is None:
            return None
        payload = row[0]
        if not isinstance(payload, str):
            return None
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, list):
            return None

        normalized = [
            float(value) for value in parsed if isinstance(value, int | float)
        ]
        if len(normalized) != self._dimensions:
            return None
        return normalized

    def set(
        self,
        *,
        cache_key: str,
        model_name: str,
        text_sha256: str,
        embedding: list[float],
    ) -> None:
        if len(embedding) != self._dimensions:
            return
        serialized_embedding = json.dumps(embedding, separators=(",", ":"))
        created_at = datetime.now(UTC).isoformat()

        with self._lock:
            self._connection.execute(
                """
                INSERT INTO embedding_cache (
                    cache_key,
                    model_name,
                    text_sha256,
                    dimensions,
                    embedding_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    embedding_json = excluded.embedding_json,
                    created_at = excluded.created_at
                """,
                (
                    cache_key,
                    model_name,
                    text_sha256,
                    self._dimensions,
                    serialized_embedding,
                    created_at,
                ),
            )
            self._connection.commit()


__all__ = ["SqliteEmbeddingCache"]
