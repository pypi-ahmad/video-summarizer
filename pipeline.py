"""Shared submit -> poll -> read-results pipeline used by all five modes."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import streamlit as st

import adversal_client

RUNS_DIR = Path("runs")
JOBS_FILE = RUNS_DIR / "jobs.json"
POLL_INTERVAL_SECONDS = 8

IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
REQUEST_ID_RE = re.compile(r'request[_ ]?id["\':\s]+([\w-]+)', re.IGNORECASE)


@dataclass
class Job:
    mode: str
    request_id: str
    output_dir: str
    file_name: str = "notes.md"
    status: str = "RUNNING"  # RUNNING | COMPLETED | FAILED
    error: str | None = None
    submitted_at: float = field(default_factory=time.time)

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
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    all_jobs = _load_all_jobs()
    all_jobs[job.request_id] = asdict(job)
    JOBS_FILE.write_text(json.dumps(all_jobs, indent=2), encoding="utf-8")


def list_saved_jobs() -> list[Job]:
    return [Job(**data) for data in _load_all_jobs().values()]


def new_job_dir(slug: str) -> Path:
    job_dir = RUNS_DIR / f"{int(time.time())}_{slug}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _extract_request_id(result: dict | str) -> str:
    if isinstance(result, dict):
        for key in ("request_id", "requestId", "id"):
            if key in result:
                return str(result[key])
        text = json.dumps(result)
    else:
        text = str(result)
    match = REQUEST_ID_RE.search(text)
    if match:
        return match.group(1)
    msg = f"could not find request_id in adversal response: {text[:200]}"
    raise adversal_client.AdversalError(msg)


def _extract_status(result: dict | str) -> tuple[str, str | None]:
    if isinstance(result, dict) and "status" in result:
        return result["status"], result.get("error")
    text = json.dumps(result) if isinstance(result, dict) else str(result)
    for candidate in ("COMPLETED", "FAILED", "RUNNING", "UNKNOWN"):
        if candidate in text.upper():
            return candidate, text if candidate == "FAILED" else None
    return "UNKNOWN", None


def submit_job(
    *,
    mode: str,
    job_dir: Path,
    video_path: str | None,
    video_url: str | None,
    type: adversal_client.VideoType,  # noqa: A002 - matches adversal-cli's own parameter name
    images: adversal_client.ImageDensity,
) -> Job:
    result = adversal_client.process_video(
        video_path=video_path,
        video_url=video_url,
        output_path=str(job_dir),
        type=type,
        images=images,
    )
    request_id = _extract_request_id(result)
    job = Job(mode=mode, request_id=request_id, output_dir=str(job_dir))
    _save_job(job)
    return job


@st.fragment(run_every=POLL_INTERVAL_SECONDS)
def render_job_progress(mode: str) -> None:
    job: Job = st.session_state.jobs[mode]
    if job.status != "RUNNING":
        return
    with st.status(f"Processing your video ({mode})...", expanded=True):
        try:
            result = adversal_client.check_video_status(job.request_id)
        except adversal_client.AdversalAuthRequiredError:
            st.session_state.auth_required = True
            st.rerun()
            return
        except adversal_client.AdversalError as exc:
            job.status, job.error = "FAILED", str(exc)
            _save_job(job)
            st.rerun()
            return
        status, error = _extract_status(result)
        st.write(f"Status: {status} - last checked {time.strftime('%H:%M:%S')}")
        if status in ("COMPLETED", "FAILED"):
            job.status, job.error = status, error
            _save_job(job)
            st.rerun()


def load_completed_notes(job: Job) -> str:
    return job.notes_path.read_text(encoding="utf-8")


def render_markdown_with_images(markdown_text: str, base_dir: Path) -> None:
    """st.markdown does not resolve local image paths - render each segment explicitly."""
    pos = 0
    for match in IMAGE_RE.finditer(markdown_text):
        if match.start() > pos:
            st.markdown(markdown_text[pos : match.start()])
        alt, src = match.group(1), match.group(2)
        image_path = (base_dir / src).resolve()
        if image_path.exists():
            st.image(str(image_path), caption=alt or None)
        pos = match.end()
    if pos < len(markdown_text):
        st.markdown(markdown_text[pos:])
