"""Semantic long-term memory: the local embedder over the existing SQLite.

The product already keeps structured memory (core/people/soul/profile/recall)
and indexes the wiki. What it could not do is answer "what did we say about X"
by MEANING. This adds exactly that, without a new service:

* the embedding model is already on the machine (``nomic-embed-text`` via
  Ollama) - free, offline, no quota, no vendor;
* the storage is the SQLite the product already ships;
* retrieval is cosine similarity computed in Python.

A small adapter, not a new platform: no Docker, no vector server, no LLM judge.
``remember`` and ``recall`` never raise and never invent: when the embedder is
unreachable they say so (``False`` / ``[]``) instead of storing a half-made
memory. Vectors live as JSON text, which keeps the file portable and readable;
the linear scan is honest for a personal memory (thousands of rows) and the
scale limit is written down rather than discovered later.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

EMBED_MODEL = "nomic-embed-text"
DB_FILE_NAME = "semantic_memory.db"
#: Same connect/read shape the local brain adapter uses: a cold model load can
#: take seconds while the server itself answers instantly.
_TIMEOUT = (10.0, 120.0)
#: After this many rows a linear scan stops being honest and the store should
#: move to an index. Recorded here so the limit is documented, not guessed.
LINEAR_SCAN_LIMIT = 20_000


def store_path() -> Path:
    """``DATA_DIR/state/semantic_memory.db`` - resolved at call time."""
    from jarvis.core import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / "state" / DB_FILE_NAME


def embed_root() -> str:
    """Where the local embedder lives: the configured Ollama endpoint."""
    try:
        from jarvis.core import config as cfg_mod

        endpoint = cfg_mod.resolve_provider_endpoint(
            "ollama", vendor_default_base_url="http://localhost:11434"
        )
        return str(endpoint.base_url or "http://localhost:11434").rstrip("/")
    except Exception:  # noqa: BLE001 - an unreadable config means the default
        log.debug("semantic: endpoint lookup failed; using the default root", exc_info=True)
        return "http://localhost:11434"


async def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """One POST -> parsed JSON, or ``None``. The single place that touches HTTP,
    so the offline tests can replace it without a network."""
    import httpx

    try:
        timeout = httpx.Timeout(10.0, read=_TIMEOUT[1])
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception:  # noqa: BLE001 - a missing embedder is a state, not an error
        log.warning("semantic: embedder call failed (%s)", url, exc_info=True)
        return None
    return data if isinstance(data, dict) else None


def _vector_of(payload: dict[str, Any] | None) -> list[float] | None:
    """The embedding out of one Ollama response, or ``None`` when it is not one."""
    if not isinstance(payload, dict):
        return None
    raw = payload.get("embedding")
    if not isinstance(raw, list) or not raw:
        return None
    try:
        vector = [float(value) for value in raw]
    except (TypeError, ValueError):
        # Reject malformed vector as unavailable.
        return None
    return vector if all(math.isfinite(value) for value in vector) else None


async def embed(text: str, *, model: str = EMBED_MODEL) -> list[float] | None:
    """The local embedding of ``text``, or ``None`` when it cannot be made."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    payload = await _post_json(
        f"{embed_root()}/api/embeddings", {"model": model, "prompt": cleaned}
    )
    return _vector_of(payload)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, ``0.0`` for anything unusable (never raises)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = norm_a = norm_b = 0.0
    for left, right in zip(a, b, strict=True):
        dot += left * right
        norm_a += left * left
        norm_b += right * right
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class SemanticIndex:
    """Rows of ``(kind, ref, text, vector)`` searched by meaning."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._path = Path(db_path) if db_path is not None else store_path()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._path))
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        ref TEXT NOT NULL DEFAULT '',
                        text TEXT NOT NULL,
                        vector TEXT NOT NULL,
                        dim INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS semantic_memory_kind ON semantic_memory(kind)"
                )
        except (OSError, sqlite3.Error):
            log.warning("semantic: schema creation failed at %s", self._path, exc_info=True)

    def add(
        self,
        text: str,
        vector: list[float],
        *,
        kind: str = "note",
        ref: str = "",
    ) -> int | None:
        """Store one memory. Returns its row id, or ``None`` when refused."""
        cleaned = str(text or "").strip()
        if not cleaned or not vector:
            return None
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO semantic_memory (kind, ref, text, vector, dim, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(kind or "note"),
                        str(ref or ""),
                        cleaned,
                        json.dumps(vector),
                        len(vector),
                        datetime.now(UTC).isoformat(timespec="seconds"),
                    ),
                )
                return int(cursor.lastrowid) if cursor.lastrowid is not None else None
        except (OSError, sqlite3.Error):
            log.warning("semantic: could not store a memory", exc_info=True)
            return None

    def count(self, *, kind: str | None = None) -> int:
        try:
            with self._connect() as connection:
                if kind is None:
                    row = connection.execute("SELECT COUNT(*) AS n FROM semantic_memory").fetchone()
                else:
                    row = connection.execute(
                        "SELECT COUNT(*) AS n FROM semantic_memory WHERE kind = ?", (kind,)
                    ).fetchone()
        except (OSError, sqlite3.Error):
            log.debug("semantic: count failed", exc_info=True)
            return 0
        return int(row["n"]) if row is not None else 0

    def search(
        self, query_vector: list[float], *, limit: int = 5, kind: str | None = None
    ) -> list[dict[str, Any]]:
        """The ``limit`` closest memories, best first. ``[]`` for a bad query."""
        if not query_vector or limit <= 0:
            return []
        try:
            with self._connect() as connection:
                if kind is None:
                    rows = connection.execute(
                        "SELECT id, kind, ref, text, vector, created_at FROM semantic_memory"
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT id, kind, ref, text, vector, created_at FROM semantic_memory"
                        " WHERE kind = ?",
                        (kind,),
                    ).fetchall()
        except (OSError, sqlite3.Error):
            log.warning("semantic: search read failed", exc_info=True)
            return []
        if len(rows) > LINEAR_SCAN_LIMIT:
            log.info(
                "semantic: %d rows exceed the honest linear-scan limit (%d); "
                "an index is due.",
                len(rows),
                LINEAR_SCAN_LIMIT,
            )
        scored: list[dict[str, Any]] = []
        for row in rows:
            try:
                vector = [float(value) for value in json.loads(row["vector"])]
            except (TypeError, ValueError, json.JSONDecodeError):
                log.debug("semantic: skipping a row with an unreadable vector", exc_info=True)
                continue
            scored.append(
                {
                    "id": int(row["id"]),
                    "kind": str(row["kind"]),
                    "ref": str(row["ref"]),
                    "text": str(row["text"]),
                    "created_at": str(row["created_at"]),
                    "score": cosine(query_vector, vector),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]


async def remember(
    text: str, *, kind: str = "note", ref: str = "", index: SemanticIndex | None = None
) -> bool:
    """Embed and store one memory. ``False`` when the embedder cannot answer."""
    vector = await embed(text)
    if vector is None:
        return False
    stored = (index or SemanticIndex()).add(text, vector, kind=kind, ref=ref)
    return stored is not None


async def recall(
    query: str, *, limit: int = 5, kind: str | None = None, index: SemanticIndex | None = None
) -> list[dict[str, Any]]:
    """The closest stored memories to ``query``. ``[]`` when nothing can answer."""
    vector = await embed(query)
    if vector is None:
        return []
    return (index or SemanticIndex()).search(vector, limit=limit, kind=kind)


__all__ = [
    "DB_FILE_NAME",
    "EMBED_MODEL",
    "LINEAR_SCAN_LIMIT",
    "SemanticIndex",
    "cosine",
    "embed",
    "embed_root",
    "recall",
    "remember",
    "store_path",
]
