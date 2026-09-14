"""Durable, path-safe visual descriptions for Adversal frames.

Owns the on-disk visual-evidence.json manifest: discovering frames,
captioning them via llm.describe_image, and safely resolving them again
before use. Must not send a frame to a provider without re-validating its
path stays inside the job directory. Next: vector_store.py, which embeds
these captions alongside text chunks.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import artifacts
import llm
import observability
import pipeline
from pipeline import Job

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

MANIFEST_NAME = "visual-evidence.json"
# load_evidence() below discards the whole manifest if this doesn't match,
# so bump it whenever the on-disk shape of a frame record changes — that is
# the mechanism that forces existing jobs to rebuild their visual index.
MANIFEST_VERSION = 1
KEY_FRAME_TS_RE = re.compile(r"frame_(\d{2})_(\d{2})-")
REQUESTED_FRAME_TS_RE = re.compile(r"-(\d+)ms$")

logger = observability.get_logger("visual_evidence")


@dataclass(frozen=True)
class VisualFrame:
    path: Path
    relative_path: str
    alt: str
    heading: str
    timestamp: str | None
    content_hash: str


@dataclass(frozen=True)
class FrameEvidence:
    relative_path: str
    alt: str
    heading: str
    timestamp: str | None
    content_hash: str
    caption: str
    provider: str
    model: str


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as image_file:
        for block in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _key_frame_timestamp(markdown: str) -> str | None:
    match = KEY_FRAME_TS_RE.search(markdown)
    return f"{match.group(1)}:{match.group(2)}" if match else None


# Adversal requested frame convention: files end with -<milliseconds>ms.
# Unit conversion: converts integer milliseconds to "HH:MM:SS" or "MM:SS".
def _requested_frame_timestamp(path: Path) -> str | None:
    match = REQUESTED_FRAME_TS_RE.search(path.stem)
    if not match:
        return None
    seconds = int(match.group(1)) // 1000
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return (
        f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
        if hours
        else f"{minutes:02d}:{remaining_seconds:02d}"
    )


def discover_frames(job: Job) -> list[VisualFrame]:
    """Collect every safe referenced and requested frame with stable context."""
    notes = pipeline.load_completed_notes(job)
    resolved_base = job.output_path.resolve()
    frames: list[VisualFrame] = []
    seen: set[Path] = set()

    for section in artifacts.split_sections(notes):
        timestamp = _key_frame_timestamp(section.markdown)
        for image in artifacts.find_local_images(section.markdown, resolved_base):
            if image.path in seen:
                continue
            seen.add(image.path)
            frames.append(
                VisualFrame(
                    path=image.path,
                    relative_path=image.relative_path.as_posix(),
                    alt=image.alt,
                    heading=section.heading,
                    timestamp=timestamp,
                    content_hash=_file_hash(image.path),
                )
            )

    for path in pipeline.find_requested_frames(resolved_base):
        if path in seen:
            continue
        seen.add(path)
        frames.append(
            VisualFrame(
                path=path,
                relative_path=path.relative_to(resolved_base).as_posix(),
                alt=f"Requested frame {path.stem}",
                heading="Requested frame",
                timestamp=_requested_frame_timestamp(path),
                content_hash=_file_hash(path),
            )
        )
    return frames


def _manifest_path(job: Job) -> Path:
    return job.output_path / MANIFEST_NAME


# Validation and security boundary: rejects manifests with mismatched version,
# verifies that referenced frame files remain strictly inside job.output_path, and
# discards records if the on-disk image SHA-256 hash has changed since captioning.
def load_evidence(job: Job) -> list[FrameEvidence]:
    """Load valid current evidence and silently discard stale or unsafe records."""
    manifest_path = _manifest_path(job)
    if not manifest_path.is_file():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        observability.log_failure(logger, "manifest.load", exc, request_id=job.request_id)
        return []
    if payload.get("version") != MANIFEST_VERSION or not isinstance(payload.get("frames"), list):
        return []

    evidence: list[FrameEvidence] = []
    for item in payload["frames"]:
        if not isinstance(item, dict):
            continue
        required = ("relative_path", "alt", "heading", "content_hash", "caption")
        if not all(isinstance(item.get(key), str) for key in required):
            continue
        path = pipeline._resolve_local_image(job.output_path, item["relative_path"])  # noqa: SLF001
        if path is None or _file_hash(path) != item["content_hash"]:
            continue
        timestamp = item.get("timestamp")
        provider = item.get("provider")
        model = item.get("model")
        evidence.append(
            FrameEvidence(
                relative_path=item["relative_path"],
                alt=item["alt"],
                heading=item["heading"],
                timestamp=timestamp if isinstance(timestamp, str) else None,
                content_hash=item["content_hash"],
                caption=item["caption"],
                provider=provider if isinstance(provider, str) else "unknown",
                model=model if isinstance(model, str) else "unknown",
            )
        )
    return evidence


# Atomic write boundary: writes JSON payload to a temporary file before renaming
# over the destination to prevent manifest corruption on process interruption.
def _save_evidence(job: Job, evidence: list[FrameEvidence]) -> None:
    manifest_path = _manifest_path(job)
    payload = {
        "version": MANIFEST_VERSION,
        "frames": [asdict(item) for item in evidence],
    }
    temporary_path = manifest_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary_path.replace(manifest_path)


def build_evidence(
    job: Job,
    option_key: str,
    *,
    force: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
) -> list[FrameEvidence]:
    """Describe all frames, persisting each success so interrupted runs can resume."""
    frames = discover_frames(job)
    existing = {} if force else {item.relative_path: item for item in load_evidence(job)}
    completed: list[FrameEvidence] = []
    option = llm.LLM_OPTIONS[option_key]

    for index, frame in enumerate(frames, start=1):
        cached = existing.get(frame.relative_path)
        if cached is not None and cached.content_hash == frame.content_hash:
            completed.append(cached)
        else:
            context = frame.heading
            if frame.timestamp:
                context += f" at approximately {frame.timestamp}"
            if frame.alt:
                context += f". Existing frame label: {frame.alt}"
            caption = llm.describe_image(
                llm.ImageInput(path=frame.path, label=f"Frame {index}: {frame.relative_path}"),
                context=context,
                option_key=option_key,
            ).strip()
            if not caption:
                msg = "The selected model returned an empty frame description."
                raise RuntimeError(msg)
            completed.append(
                FrameEvidence(
                    relative_path=frame.relative_path,
                    alt=frame.alt,
                    heading=frame.heading,
                    timestamp=frame.timestamp,
                    content_hash=frame.content_hash,
                    caption=caption,
                    provider=option.provider,
                    model=option.model,
                )
            )
            _save_evidence(job, completed)
        if progress is not None:
            progress(index, len(frames), frame.relative_path)

    _save_evidence(job, completed)
    logger.info(
        "manifest.completed request_id=%s frames=%s provider=%s model=%s",
        job.request_id,
        len(completed),
        option.provider,
        option.model,
    )
    return completed


def evidence_hash(evidence: list[FrameEvidence]) -> str:
    # "text-only" is a real sentinel value, not just a placeholder: modes.py
    # matches on this exact string to recognize cache entries generated
    # without any visual evidence.
    if not evidence:
        return "text-only"
    stable = [
        (item.relative_path, item.content_hash, item.caption)
        for item in sorted(evidence, key=lambda item: item.relative_path)
    ]
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False).encode()).hexdigest()


def image_inputs(job: Job, evidence: list[FrameEvidence]) -> list[llm.ImageInput]:
    """Resolve persisted relative paths again before sending pixels to a provider.

    Re-resolving (instead of trusting the stored relative_path) re-applies
    the same containment check as pipeline._resolve_local_image, in case the
    manifest was hand-edited or came from an older format.
    """
    inputs = []
    for index, item in enumerate(evidence, start=1):
        path = pipeline._resolve_local_image(job.output_path, item.relative_path)  # noqa: SLF001
        if path is None:
            continue
        label = (
            f"Frame {index} | path={item.relative_path} | chapter={item.heading} | "
            f"timestamp={item.timestamp or 'unknown'}"
        )
        inputs.append(llm.ImageInput(path=path, label=label))
    return inputs
