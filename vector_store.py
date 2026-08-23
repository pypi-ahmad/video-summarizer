"""Persistent Qdrant storage for searchable video-note chunks."""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import streamlit as st
from qdrant_client import QdrantClient, models

import llm
import observability

if TYPE_CHECKING:
    from collections.abc import Sequence

COLLECTION_NAME = "video_chunks_text_embedding_3_small_v1"
DEFAULT_STORAGE_PATH = Path("runs") / "qdrant"
_STORE_LOCK = threading.RLock()

logger = observability.get_logger("qdrant")


@dataclass(frozen=True)
class SearchHit:
    heading: str
    text: str
    timestamp: str | None
    score: float


class ChunkLike(Protocol):
    heading: str
    text: str
    timestamp: str | None


@st.cache_resource
def get_client(storage_path: str = str(DEFAULT_STORAGE_PATH)) -> QdrantClient:
    """Return the single process-wide client required by persistent local mode."""
    if storage_path == ":memory:":
        return QdrantClient(location=storage_path)
    return QdrantClient(path=storage_path, force_disable_check_same_thread=True)


def _job_filter(request_id: str, notes_hash: str | None = None) -> models.Filter:
    conditions = [
        models.FieldCondition(key="request_id", match=models.MatchValue(value=request_id)),
    ]
    if notes_hash is not None:
        conditions.extend(
            [
                models.FieldCondition(
                    key="notes_hash", match=models.MatchValue(value=notes_hash)
                ),
                models.FieldCondition(
                    key="embedding_model", match=models.MatchValue(value=llm.EMBED_MODEL)
                ),
            ]
        )
    return models.Filter(must=conditions)


def _notes_hash(notes: str) -> str:
    return hashlib.sha256(notes.encode()).hexdigest()


def _point_id(request_id: str, notes_hash: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{request_id}:{notes_hash}:{index}"))


def _ensure_collection(client: QdrantClient, vector_size: int) -> None:
    if client.collection_exists(COLLECTION_NAME):
        return
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def _index_video(
    *,
    request_id: str,
    source_name: str,
    notes: str,
    chunks: Sequence[ChunkLike],
    client: QdrantClient | None = None,
) -> None:
    """Idempotently index one video's chunks, replacing stale points for that video."""
    if not chunks:
        msg = "cannot index video notes without chunks"
        raise ValueError(msg)

    active_client = client or get_client()
    content_hash = _notes_hash(notes)
    with _STORE_LOCK:
        if active_client.collection_exists(COLLECTION_NAME):
            indexed = active_client.count(
                collection_name=COLLECTION_NAME,
                count_filter=_job_filter(request_id, content_hash),
                exact=True,
            ).count
            if indexed == len(chunks):
                logger.info(
                    "index.reused request_id=%s chunks=%s", request_id, len(chunks)
                )
                return

        texts = [chunk.text for chunk in chunks]
        embeddings = llm.embed(texts)
        if not embeddings or not embeddings[0]:
            msg = "embedding provider returned no vectors"
            raise RuntimeError(msg)
        _ensure_collection(active_client, len(embeddings[0]))
        active_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(filter=_job_filter(request_id)),
            wait=True,
        )
        points = []
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            points.append(
                models.PointStruct(
                    id=_point_id(request_id, content_hash, index),
                    vector=embedding,
                    payload={
                        "request_id": request_id,
                        "source_name": source_name,
                        "heading": chunk.heading,
                        "timestamp": chunk.timestamp,
                        "text": chunk.text,
                        "chunk_index": index,
                        "notes_hash": content_hash,
                        "embedding_model": llm.EMBED_MODEL,
                    },
                )
            )
        active_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )


def index_video(
    *,
    request_id: str,
    source_name: str,
    notes: str,
    chunks: Sequence[ChunkLike],
    client: QdrantClient | None = None,
) -> None:
    """Log and idempotently index one video's chunks."""
    started = time.perf_counter()
    logger.info("index.started request_id=%s chunks=%s", request_id, len(chunks))
    try:
        _index_video(
            request_id=request_id,
            source_name=source_name,
            notes=notes,
            chunks=chunks,
            client=client,
        )
    except Exception as exc:
        observability.log_failure(
            logger,
            "index",
            exc,
            request_id=request_id,
            chunks=len(chunks),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    logger.info(
        "index.completed request_id=%s chunks=%s duration_ms=%s",
        request_id,
        len(chunks),
        round((time.perf_counter() - started) * 1000),
    )


def _search_video(
    request_id: str,
    query: str,
    *,
    top_k: int = 5,
    client: QdrantClient | None = None,
) -> list[SearchHit]:
    """Return semantic matches from only the active video."""
    active_client = client or get_client()
    query_vector = llm.embed([query])[0]
    with _STORE_LOCK:
        points = active_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=_job_filter(request_id),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        ).points

    hits = []
    for point in points:
        payload = point.payload or {}
        text = payload.get("text")
        heading = payload.get("heading")
        timestamp = payload.get("timestamp")
        if not isinstance(text, str) or not isinstance(heading, str):
            continue
        hits.append(
            SearchHit(
                heading=heading,
                text=text,
                timestamp=timestamp if isinstance(timestamp, str) else None,
                score=float(point.score),
            )
        )
    return hits


def search_video(
    request_id: str,
    query: str,
    *,
    top_k: int = 5,
    client: QdrantClient | None = None,
) -> list[SearchHit]:
    """Log and return semantic matches from only the active video."""
    started = time.perf_counter()
    logger.info("search.started request_id=%s top_k=%s", request_id, top_k)
    try:
        hits = _search_video(request_id, query, top_k=top_k, client=client)
    except Exception as exc:
        observability.log_failure(
            logger,
            "search",
            exc,
            request_id=request_id,
            top_k=top_k,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    logger.info(
        "search.completed request_id=%s hits=%s duration_ms=%s",
        request_id,
        len(hits),
        round((time.perf_counter() - started) * 1000),
    )
    return hits


def close_local_store() -> None:
    """Release Qdrant's Windows file lock before deleting local run data."""
    logger.info("store.close_started")
    with _STORE_LOCK:
        client = get_client()
        client.close()
        get_client.clear()
    logger.info("store.close_completed")
