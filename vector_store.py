"""Persistent Qdrant storage for text and described video-frame evidence."""

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
    kind: str = "text"
    image_path: str | None = None


class ChunkLike(Protocol):
    heading: str
    text: str
    timestamp: str | None


class FrameLike(Protocol):
    @property
    def relative_path(self) -> str: ...

    @property
    def alt(self) -> str: ...

    @property
    def heading(self) -> str: ...

    @property
    def timestamp(self) -> str | None: ...

    @property
    def caption(self) -> str: ...


@st.cache_resource
def get_client(storage_path: str = str(DEFAULT_STORAGE_PATH)) -> QdrantClient:
    """Return the single process-wide client required by persistent local mode."""
    if storage_path == ":memory:":
        return QdrantClient(location=storage_path)
    return QdrantClient(path=storage_path, force_disable_check_same_thread=True)


def _job_filter(
    request_id: str,
    evidence_hash: str | None = None,
    *,
    kind: str | None = None,
    notes_hash: str | None = None,
) -> models.Filter:
    conditions = [
        models.FieldCondition(key="request_id", match=models.MatchValue(value=request_id)),
    ]
    if evidence_hash is not None:
        conditions.extend(
            [
                models.FieldCondition(
                    key="evidence_hash", match=models.MatchValue(value=evidence_hash)
                ),
                models.FieldCondition(
                    key="embedding_model", match=models.MatchValue(value=llm.EMBED_MODEL)
                ),
            ]
        )
    if kind is not None:
        conditions.append(
            models.FieldCondition(key="kind", match=models.MatchValue(value=kind))
        )
    if notes_hash is not None:
        conditions.append(
            models.FieldCondition(
                key="notes_hash", match=models.MatchValue(value=notes_hash)
            )
        )
    return models.Filter(must=conditions)


def _notes_hash(notes: str) -> str:
    return hashlib.sha256(notes.encode()).hexdigest()


def _point_id(request_id: str, evidence_hash: str, kind: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{request_id}:{evidence_hash}:{kind}:{index}"))


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
    frames: Sequence[FrameLike] = (),
    evidence_hash: str = "text-only",
    client: QdrantClient | None = None,
) -> None:
    """Idempotently index one video's text and described frames."""
    if not chunks:
        msg = "cannot index video notes without chunks"
        raise ValueError(msg)

    active_client = client or get_client()
    notes_hash = _notes_hash(notes)
    expected_points = len(chunks) + len(frames)
    with _STORE_LOCK:
        if active_client.collection_exists(COLLECTION_NAME):
            indexed = active_client.count(
                collection_name=COLLECTION_NAME,
                count_filter=_job_filter(
                    request_id, evidence_hash, notes_hash=notes_hash
                ),
                exact=True,
            ).count
            if indexed == expected_points:
                logger.info(
                    "index.reused request_id=%s chunks=%s frames=%s",
                    request_id,
                    len(chunks),
                    len(frames),
                )
                return

        frame_texts = [
            "\n".join(part for part in (frame.heading, frame.alt, frame.caption) if part)
            for frame in frames
        ]
        texts = [chunk.text for chunk in chunks] + frame_texts
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
        for index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings[: len(chunks)], strict=True)
        ):
            points.append(
                models.PointStruct(
                    id=_point_id(request_id, evidence_hash, "text", index),
                    vector=embedding,
                    payload={
                        "request_id": request_id,
                        "source_name": source_name,
                        "heading": chunk.heading,
                        "timestamp": chunk.timestamp,
                        "text": chunk.text,
                        "kind": "text",
                        "chunk_index": index,
                        "notes_hash": notes_hash,
                        "evidence_hash": evidence_hash,
                        "embedding_model": llm.EMBED_MODEL,
                    },
                )
            )
        for index, (frame, embedding) in enumerate(
            zip(frames, embeddings[len(chunks) :], strict=True)
        ):
            points.append(
                models.PointStruct(
                    id=_point_id(request_id, evidence_hash, "frame", index),
                    vector=embedding,
                    payload={
                        "request_id": request_id,
                        "source_name": source_name,
                        "heading": frame.heading,
                        "timestamp": frame.timestamp,
                        "text": frame.caption,
                        "kind": "frame",
                        "image_path": frame.relative_path,
                        "frame_index": index,
                        "notes_hash": notes_hash,
                        "evidence_hash": evidence_hash,
                        "embedding_model": llm.EMBED_MODEL,
                    },
                )
            )
        active_client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)


def index_video(
    *,
    request_id: str,
    source_name: str,
    notes: str,
    chunks: Sequence[ChunkLike],
    frames: Sequence[FrameLike] = (),
    evidence_hash: str = "text-only",
    client: QdrantClient | None = None,
) -> None:
    """Log and idempotently index one video's text and visual evidence."""
    started = time.perf_counter()
    logger.info(
        "index.started request_id=%s chunks=%s frames=%s",
        request_id,
        len(chunks),
        len(frames),
    )
    try:
        _index_video(
            request_id=request_id,
            source_name=source_name,
            notes=notes,
            chunks=chunks,
            frames=frames,
            evidence_hash=evidence_hash,
            client=client,
        )
    except Exception as exc:
        observability.log_failure(
            logger,
            "index",
            exc,
            request_id=request_id,
            chunks=len(chunks),
            frames=len(frames),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    logger.info(
        "index.completed request_id=%s chunks=%s frames=%s duration_ms=%s",
        request_id,
        len(chunks),
        len(frames),
        round((time.perf_counter() - started) * 1000),
    )


def _query_points(
    client: QdrantClient,
    request_id: str,
    query_vector: list[float],
    *,
    top_k: int,
    kind: str | None,
) -> list[SearchHit]:
    points = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=_job_filter(request_id, kind=kind),
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
        point_kind = payload.get("kind")
        image_path = payload.get("image_path")
        if not isinstance(text, str) or not isinstance(heading, str):
            continue
        hits.append(
            SearchHit(
                heading=heading,
                text=text,
                timestamp=timestamp if isinstance(timestamp, str) else None,
                score=float(point.score),
                kind=point_kind if isinstance(point_kind, str) else "text",
                image_path=image_path if isinstance(image_path, str) else None,
            )
        )
    return hits


def _search_video(
    request_id: str,
    query: str,
    *,
    top_k: int = 5,
    kind: str | None = None,
    client: QdrantClient | None = None,
) -> list[SearchHit]:
    """Return semantic matches from only the active video."""
    active_client = client or get_client()
    query_vector = llm.embed([query])[0]
    with _STORE_LOCK:
        return _query_points(active_client, request_id, query_vector, top_k=top_k, kind=kind)


def search_video(
    request_id: str,
    query: str,
    *,
    top_k: int = 5,
    kind: str | None = None,
    client: QdrantClient | None = None,
) -> list[SearchHit]:
    """Log and return semantic matches from only the active video."""
    started = time.perf_counter()
    logger.info("search.started request_id=%s top_k=%s kind=%s", request_id, top_k, kind)
    try:
        hits = _search_video(request_id, query, top_k=top_k, kind=kind, client=client)
    except Exception as exc:
        observability.log_failure(
            logger,
            "search",
            exc,
            request_id=request_id,
            top_k=top_k,
            kind=kind,
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


def search_video_evidence(
    request_id: str,
    query: str,
    *,
    text_top_k: int = 5,
    frame_top_k: int = 3,
    client: QdrantClient | None = None,
) -> tuple[list[SearchHit], list[SearchHit]]:
    """Search text and frame descriptions with one query embedding."""
    active_client = client or get_client()
    query_vector = llm.embed([query])[0]
    with _STORE_LOCK:
        text_hits = _query_points(
            active_client, request_id, query_vector, top_k=text_top_k, kind="text"
        )
        frame_hits = _query_points(
            active_client, request_id, query_vector, top_k=frame_top_k, kind="frame"
        )
    return text_hits, frame_hits


def close_local_store() -> None:
    """Release Qdrant's Windows file lock before deleting local run data."""
    logger.info("store.close_started")
    with _STORE_LOCK:
        client = get_client()
        client.close()
        get_client.clear()
    logger.info("store.close_completed")
