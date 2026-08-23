"""Shared submit -> poll -> read-results pipeline used by all output modes."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import streamlit as st

import adversal_client
import observability

RUNS_DIR = Path("runs")
JOBS_FILE = RUNS_DIR / "jobs.json"
POLL_INTERVAL_SECONDS = 8
JOBS_LOCK = threading.Lock()

logger = observability.get_logger("pipeline")

IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}


@dataclass
class Job:
    mode: str
    request_id: str
    output_dir: str
    file_name: str = "notes.md"
    status: str = "RUNNING"  # RUNNING | COMPLETED | FAILED
    error: str | None = None
    submitted_at: float = field(default_factory=time.time)
    source_name: str = "Video"
    source_url: str | None = None
    video_type: adversal_client.VideoType = "generic"
    image_density: adversal_client.ImageDensity = "selective"
    start_time: str | None = None
    end_time: str | None = None
    timestamps: list[str] = field(default_factory=list)
    completed_at: float | None = None

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

    @property
    def notes_path(self) -> Path:
        return self.output_path / self.file_name


def _load_all_jobs() -> dict[str, dict]:
    if not JOBS_FILE.exists():
        return {}
    return json.loads(JOBS_FILE.read_text(encoding="utf-8"))


def _save_job(job: Job) -> None:
    with JOBS_LOCK:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        all_jobs = _load_all_jobs()
        all_jobs[job.request_id] = asdict(job)
        temp_file = JOBS_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(all_jobs, indent=2), encoding="utf-8")
        temp_file.replace(JOBS_FILE)
    logger.debug("job.persisted request_id=%s status=%s", job.request_id, job.status)


def list_saved_jobs() -> list[Job]:
    return [Job(**data) for data in _load_all_jobs().values()]


def new_job_dir(slug: str) -> Path:
    job_dir = RUNS_DIR / f"{int(time.time())}_{uuid.uuid4().hex}_{slug}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def submit_job(
    *,
    mode: str,
    job_dir: Path,
    video_path: str | None,
    video_url: str | None,
    type: adversal_client.VideoType,  # noqa: A002 - matches adversal-cli's own parameter name
    images: adversal_client.ImageDensity,
    start_time: str | None = None,
    end_time: str | None = None,
    timestamps: list[str] | None = None,
    source_name: str = "Video",
    source_url: str | None = None,
) -> Job:
    logger.info("job.submission_started video_type=%s image_density=%s", type, images)
    request_id = adversal_client.process_video(
        video_path=video_path,
        video_url=video_url,
        output_path=str(job_dir),
        type=type,
        images=images,
        start_time=start_time,
        end_time=end_time,
        timestamps=timestamps,
    )
    job = Job(
        mode=mode,
        request_id=request_id,
        output_dir=str(job_dir),
        source_name=source_name,
        source_url=source_url,
        video_type=type,
        image_density=images,
        start_time=start_time,
        end_time=end_time,
        timestamps=timestamps or [],
    )
    _save_job(job)
    logger.info("job.submission_completed request_id=%s", request_id)
    return job


@st.fragment(run_every=POLL_INTERVAL_SECONDS)
def render_job_progress() -> None:
    job: Job | None = st.session_state.get("active_job")
    if job is None:
        return
    if job.status != "RUNNING":
        return
    logger.info("job.poll_started request_id=%s", job.request_id)
    with st.status(f"Processing {job.source_name}...", expanded=True):
        try:
            result = adversal_client.check_video_status(job.request_id)
        except adversal_client.AdversalAuthRequiredError:
            logger.warning("job.poll_authentication_required request_id=%s", job.request_id)
            st.session_state.auth_required = True
            st.rerun()
            return
        except adversal_client.AdversalError as exc:
            observability.log_failure(logger, "job.poll", exc, request_id=job.request_id)
            job.status, job.error = "FAILED", str(exc)
            _save_job(job)
            st.rerun()
            return
        status, error = result.status, result.error
        logger.info("job.poll_completed request_id=%s status=%s", job.request_id, status)
        st.write(f"Status: {status} - last checked {time.strftime('%H:%M:%S')}")
        if status in ("COMPLETED", "FAILED", "UNKNOWN"):
            job.status = "FAILED" if status == "UNKNOWN" else status
            job.error = error
            if status == "COMPLETED":
                job.completed_at = time.time()
            _save_job(job)
            st.rerun()


def retry_job(job: Job) -> None:
    """Resume status checks for an existing Adversal request without resubmitting it."""
    job.status = "RUNNING"
    job.error = None
    job.completed_at = None
    _save_job(job)


def load_completed_notes(job: Job) -> str:
    return job.notes_path.read_text(encoding="utf-8")


def _resolve_local_image(base_dir: Path, src: str) -> Path | None:
    resolved_base = base_dir.resolve()
    image_path = (resolved_base / src).resolve()
    if not image_path.is_relative_to(resolved_base) or not image_path.is_file():
        return None
    return image_path


def find_requested_frames(base_dir: Path) -> list[Path]:
    """Return safe image files created by Adversal for explicit timestamps."""
    resolved_base = base_dir.resolve()
    requested_dir = (resolved_base / "requested_frames").resolve()
    if not requested_dir.is_relative_to(resolved_base) or not requested_dir.is_dir():
        return []
    return sorted(
        path.resolve()
        for path in requested_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in IMAGE_SUFFIXES
        and path.resolve().is_relative_to(resolved_base)
    )


def render_markdown_with_images(markdown_text: str, base_dir: Path) -> None:
    """st.markdown does not resolve local image paths - render each segment explicitly."""
    pos = 0
    for match in IMAGE_RE.finditer(markdown_text):
        if match.start() > pos:
            st.markdown(markdown_text[pos : match.start()])
        alt, src = match.group(1), match.group(2)
        image_path = _resolve_local_image(base_dir, src)
        if image_path is not None:
            st.image(str(image_path), caption=alt or None)
        pos = match.end()
    if pos < len(markdown_text):
        st.markdown(markdown_text[pos:])
