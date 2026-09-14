"""Streamlit entry point for the process-once video workspace.

Owns page routing and widget/session-state wiring only; delegates all
Adversal, LLM, and Qdrant calls to adversal_client/llm/vector_store via
pipeline.py and modes.py so retries, caching, and safety checks stay
centralized. Next: pipeline.py for the submit/poll/render flow.
"""

from __future__ import annotations

import math
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st

import adversal_client
import artifacts
import llm
import modes
import observability
import pipeline
import vector_store
from adversal_client import ImageDensity, VideoType
from pipeline import Job

logger = observability.get_logger("app")

VIDEO_TYPES: dict[str, VideoType] = {
    "Generic": "generic",
    "Lesson / tutorial": "lesson",
    "Interview": "interview",
    "Meeting / webinar": "meeting",
}
IMAGE_DENSITIES: dict[str, ImageDensity] = {
    "Minimal": "minimal",
    "Selective": "selective",
    "Generous": "generous",
}
FRAME_PAGE_SIZE = 12


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "video"


# Streamlit hands us the browser-supplied filename verbatim (untrusted):
# strip any path component and confirm the resolved destination still sits
# inside job_dir before writing, so a crafted name like "../../x" can't
# escape the job's own directory.
def _safe_upload_path(job_dir: Path, filename: str) -> Path:
    name = Path(filename.replace("\\", "/")).name
    if not name:
        msg = "invalid upload filename"
        raise ValueError(msg)
    base_dir = job_dir.resolve()
    destination = (base_dir / name).resolve()
    if not destination.is_relative_to(base_dir):
        msg = "upload filename escapes job directory"
        raise ValueError(msg)
    return destination


def _url_source_name(url: str) -> str:
    parsed = urlsplit(url)
    return Path(parsed.path).name or parsed.netloc or "Video URL"


def _parse_timestamps(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]


# Runtime environment boundary: on local desktop, OAuth opens a local browser tab.
# In headless container deployments like private Hugging Face Spaces (SPACE_ID set),
# browser auto-open is unavailable, so the user must retrieve the temporary OAuth URL
# from the container runtime logs.
def render_auth_banner_if_needed() -> bool:
    if not st.session_state.get("auth_required"):
        return False
    if os.environ.get("SPACE_ID"):
        st.warning("Adversal needs you to sign in from this private Hugging Face Space.")
        st.info(
            "Open the Space runtime logs in another tab, then select Authenticate below. "
            "Open the temporary Adversal URL printed in the logs and finish signing in."
        )
    else:
        st.warning("Adversal needs you to sign in. This opens a browser window on this machine.")
    if st.button("Authenticate"):
        logger.info("auth.started")
        with st.spinner("Waiting for browser sign-in to complete..."):
            try:
                adversal_client.authenticate()
            except adversal_client.AdversalError as exc:
                observability.log_failure(logger, "auth", exc)
                st.error(str(exc))
                return True
        logger.info("auth.completed")
        st.session_state.auth_required = False
        st.rerun()
    return True


def render_quota_sidebar() -> None:
    with st.sidebar.expander("Quota", expanded=False):
        if st.button("Check remaining quota"):
            logger.info("quota.started")
            try:
                quota = adversal_client.check_remaining_quota()
            except adversal_client.AdversalAuthRequiredError:
                logger.warning("quota.authentication_required")
                st.session_state.auth_required = True
                st.rerun()
            except adversal_client.AdversalError as exc:
                observability.log_failure(logger, "quota", exc)
                st.error(str(exc))
            else:
                logger.info("quota.completed")
                st.write(quota)


def render_resume_picker() -> None:
    saved = pipeline.list_saved_jobs()
    if not saved:
        return
    with st.sidebar.expander("Resume a previous job", expanded=False):
        for job in sorted(saved, key=lambda item: item.submitted_at, reverse=True)[:10]:
            label = f"{job.source_name} - {job.status} - {job.request_id[:8]}"
            if st.button(label, key=f"resume-{job.request_id}"):
                logger.info("job.resumed request_id=%s status=%s", job.request_id, job.status)
                st.session_state.active_job = job
                st.rerun()


def render_clear_runs() -> None:
    with st.sidebar.expander("Danger zone", expanded=False):
        confirm = st.checkbox("I understand this deletes all local run data")
        if st.button("Clear all runs", disabled=not confirm):
            logger.warning("runs.clear_started")
            # Qdrant's local mode holds an OS-level file lock under
            # runs/qdrant; it must be released before the tree can be
            # removed (rmtree fails on Windows otherwise). This permanently
            # deletes uploads, jobs, notes, frames, and vectors with no undo.
            try:
                vector_store.close_local_store()
                shutil.rmtree(pipeline.RUNS_DIR, ignore_errors=False)
            except FileNotFoundError:
                pass
            except OSError as exc:
                observability.log_failure(logger, "runs.clear", exc)
                st.error(f"Could not clear local run data: {exc}")
                return
            logger.warning("runs.clear_completed")
            st.session_state.clear()
            st.rerun()


def render_submit_form() -> None:
    source_kind = st.segmented_control(
        "Video source",
        ["Upload file", "Video URL"],
        default="Upload file",
        key="video-source-kind",
    )
    uploaded_file = None
    video_url = None
    if source_kind == "Upload file":
        uploaded_file = st.file_uploader("Video file", type=["mp4", "mov", "mkv", "webm"])
    else:
        video_url = st.text_input("Public video URL")

    video_type_label = st.selectbox("Video type", list(VIDEO_TYPES), index=0)
    image_density_label = st.selectbox("Key visual frames", list(IMAGE_DENSITIES), index=1)
    with st.expander("Advanced processing controls"):
        st.caption("Use seconds, MM:SS, or HH:MM:SS. Leave blank to process the full video.")
        start_time_input = st.text_input("Start time", placeholder="00:10")
        end_time_input = st.text_input("End time", placeholder="01:20")
        timestamps_input = st.text_area(
            "Exact frame timestamps",
            placeholder="00:20, 00:40\n01:00",
            help="Separate timestamps with commas or new lines.",
        )
    st.caption("The video is processed once. Notes, frames, search, and outputs reuse it.")

    if not st.button("Process video", type="primary"):
        return
    if not uploaded_file and not video_url:
        st.error("Provide a file or a URL first.")
        return
    if video_type_label not in VIDEO_TYPES or image_density_label not in IMAGE_DENSITIES:
        st.error("Invalid analysis settings.")
        return

    source_name = uploaded_file.name if uploaded_file else _url_source_name(video_url or "")
    start_time = start_time_input.strip() or None
    end_time = end_time_input.strip() or None
    timestamps = _parse_timestamps(timestamps_input)
    logger.info(
        "job.submit_requested source_kind=%s video_type=%s image_density=%s",
        "upload" if uploaded_file else "url",
        VIDEO_TYPES[video_type_label],
        IMAGE_DENSITIES[image_density_label],
    )
    job_dir = pipeline.new_job_dir(slugify(source_name))
    video_path = None
    if uploaded_file:
        try:
            destination = _safe_upload_path(job_dir, uploaded_file.name)
        except ValueError:
            st.error("Invalid upload filename.")
            return
        destination.write_bytes(uploaded_file.getvalue())
        video_path = str(destination)
    try:
        job = pipeline.submit_job(
            mode="Source analysis",
            job_dir=job_dir,
            video_path=video_path,
            video_url=video_url,
            type=VIDEO_TYPES[video_type_label],
            images=IMAGE_DENSITIES[image_density_label],
            start_time=start_time,
            end_time=end_time,
            timestamps=timestamps,
            source_name=source_name,
            source_url=video_url,
        )
    except adversal_client.AdversalAuthRequiredError:
        logger.warning("job.submit_authentication_required")
        st.session_state.auth_required = True
        st.rerun()
    except adversal_client.AdversalError as exc:
        observability.log_failure(logger, "job.submit", exc)
        st.error(str(exc))
    else:
        logger.info("job.submit_completed request_id=%s", job.request_id)
        st.session_state.active_job = job
        st.rerun()


def render_failure(job: Job) -> None:
    st.error(f"Processing failed: {job.error or 'unknown error'}")
    with st.container(horizontal=True):
        if st.button("Retry status check", icon=":material/refresh:"):
            logger.info("job.status_retry request_id=%s", job.request_id)
            pipeline.retry_job(job)
            st.rerun()
        if st.button("Start over"):
            logger.info("job.start_over request_id=%s", job.request_id)
            st.session_state.active_job = None
            st.rerun()


def render_notes(job: Job) -> None:
    try:
        notes = pipeline.load_completed_notes(job)
    except FileNotFoundError:
        logger.warning("notes.missing request_id=%s", job.request_id)
        st.error("Adversal marked this job complete, but its Markdown file is missing.")
        return
    images = artifacts.find_local_images(notes, job.output_path)
    requested_frames = pipeline.find_requested_frames(job.output_path)
    with st.container(horizontal=True):
        st.metric("Sections", len(artifacts.split_sections(notes)))
        st.metric("Key frames", len(images) + len(requested_frames))
        st.metric("Analysis profile", job.video_type)
    with st.container(horizontal=True):
        st.download_button(
            "Download Markdown",
            notes,
            file_name=artifacts.download_filename(job.source_name, "notes", "md"),
            mime="text/markdown",
            icon=":material/download:",
        )
        st.download_button(
            "Download native bundle",
            artifacts.build_native_bundle(job),
            file_name=artifacts.download_filename(job.source_name, "native_bundle", "zip"),
            mime="application/zip",
            icon=":material/archive:",
        )
        st.download_button(
            "Download OKF 0.2 bundle",
            artifacts.build_okf_bundle(job),
            file_name=artifacts.download_filename(job.source_name, "okf_0_2_bundle", "zip"),
            mime="application/zip",
            icon=":material/account_tree:",
        )
    pipeline.render_markdown_with_images(notes, job.output_path)


def render_frames(job: Job) -> None:
    notes = pipeline.load_completed_notes(job)
    images = artifacts.find_local_images(notes, job.output_path)
    frames = [(image.path, image.alt or image.relative_path.name) for image in images]
    known_paths = {path.resolve() for path, _ in frames}
    frames.extend(
        (path, f"Requested frame · {path.stem}")
        for path in pipeline.find_requested_frames(job.output_path)
        if path.resolve() not in known_paths
    )
    if not frames:
        st.info("This Adversal analysis did not return any key or requested frames.")
        return
    page_count = math.ceil(len(frames) / FRAME_PAGE_SIZE)
    page = 1
    if page_count > 1:
        page = st.number_input(
            "Frame page",
            min_value=1,
            max_value=page_count,
            value=1,
            key=f"frame-page-{job.request_id}",
        )
    start = (page - 1) * FRAME_PAGE_SIZE
    visible = frames[start : start + FRAME_PAGE_SIZE]
    columns = st.columns(3)
    for index, (path, caption) in enumerate(visible):
        with columns[index % 3]:
            st.image(str(path), caption=caption)
    st.caption(f"Showing {start + 1}-{start + len(visible)} of {len(frames)} frames")


def render_create(job: Job) -> None:
    modes.render_visual_index_controls(job)
    workflow = st.selectbox("Output", list(modes.CREATE_RENDERERS), key="create-workflow")
    modes.CREATE_RENDERERS[workflow](job)


def render_workspace(job: Job) -> None:
    with st.container(horizontal=True, horizontal_alignment="distribute"):
        st.subheader(job.source_name)
        download_slot = st.empty()
        if st.button("Process another video", icon=":material/add:"):
            logger.info("workspace.closed request_id=%s", job.request_id)
            st.session_state.active_job = None
            st.rerun()
    time_window = "full video"
    if job.start_time or job.end_time:
        time_window = f"{job.start_time or 'start'} to {job.end_time or 'end'}"
    st.caption(
        f"Adversal request `{job.request_id}` · {job.video_type} · "
        f"{job.image_density} frames · {time_window}"
    )
    view = st.segmented_control(
        "Workspace",
        ["Notes", "Key frames", "Ask", "Create"],
        default="Notes",
        key=f"workspace-{job.request_id}",
    )
    if view == "Notes":
        render_notes(job)
    elif view == "Key frames":
        render_frames(job)
    elif view == "Ask":
        modes.render_knowledge_base(job)
    else:
        render_create(job)

    option_key = st.session_state.llm_option
    generated_documents = modes.cached_generated_documents(job, option_key)
    with download_slot:
        st.download_button(
            "Download all",
            lambda: artifacts.build_all_downloads_bundle(job, generated_documents),
            file_name=artifacts.download_filename(job.source_name, "all_downloads", "zip"),
            mime="application/zip",
            key=f"download-all-{job.request_id}-{option_key}-{len(generated_documents)}",
            on_click="ignore",
            icon=":material/folder_zip:",
        )


def main() -> None:
    observability.configure_logging()
    st.set_page_config(page_title="Video Summarizer", layout="wide")
    st.session_state.setdefault("active_job", None)

    if render_auth_banner_if_needed():
        st.stop()

    st.title("Video Summarizer")
    st.session_state.llm_option = st.sidebar.selectbox(
        "LLM backend",
        options=list(llm.LLM_OPTIONS),
        format_func=lambda key: llm.LLM_OPTIONS[key].label,
    )
    render_quota_sidebar()
    render_resume_picker()
    render_clear_runs()

    # A job moves through one linear state machine: no job -> RUNNING ->
    # FAILED or COMPLETED. The trailing `else` below means COMPLETED, the
    # only state that reaches the full workspace view.
    job: Job | None = st.session_state.active_job
    if job is None:
        render_submit_form()
    elif job.status == "RUNNING":
        pipeline.render_job_progress()
    elif job.status == "FAILED":
        render_failure(job)
    else:
        render_workspace(job)


if __name__ == "__main__":
    main()
