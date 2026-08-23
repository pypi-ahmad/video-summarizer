"""Streamlit entry point: page config, sidebar, and per-mode dispatch."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import streamlit as st

import adversal_client
import llm
import modes
import pipeline
from adversal_client import ImageDensity, VideoType
from pipeline import Job


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "video"


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


def render_auth_banner_if_needed() -> bool:
    if not st.session_state.get("auth_required"):
        return False
    st.warning("Adversal needs you to sign in. This opens a browser window on this machine.")
    if st.button("Authenticate"):
        with st.spinner("Waiting for browser sign-in to complete..."):
            try:
                adversal_client.authenticate()
            except adversal_client.AdversalError as exc:
                st.error(str(exc))
                return True
        st.session_state.auth_required = False
        st.rerun()
    return True


def render_quota_sidebar() -> None:
    with st.sidebar.expander("Quota", expanded=False):
        if st.button("Check remaining quota"):
            try:
                quota = adversal_client.check_remaining_quota()
            except adversal_client.AdversalAuthRequiredError:
                st.session_state.auth_required = True
                st.rerun()
            except adversal_client.AdversalError as exc:
                st.error(str(exc))
            else:
                st.write(quota)


def render_resume_picker() -> None:
    saved = pipeline.list_saved_jobs()
    if not saved:
        return
    with st.sidebar.expander("Resume a previous job", expanded=False):
        for job in sorted(saved, key=lambda j: j.submitted_at, reverse=True)[:10]:
            label = f"{job.mode} - {job.status} - {job.request_id[:8]}"
            if st.button(label, key=f"resume-{job.request_id}"):
                st.session_state.jobs[job.mode] = job
                st.rerun()


def render_clear_runs() -> None:
    with st.sidebar.expander("Danger zone", expanded=False):
        confirm = st.checkbox("I understand this deletes all local run data")
        if st.button("Clear all runs", disabled=not confirm):
            shutil.rmtree(pipeline.RUNS_DIR, ignore_errors=True)
            st.session_state.jobs = {}
            st.rerun()


def render_submit_form(mode: str, video_type: VideoType, images: ImageDensity) -> None:
    source_kind = st.radio("Video source", ["Upload file", "Video URL"], horizontal=True)
    uploaded_file = None
    video_url = None
    if source_kind == "Upload file":
        uploaded_file = st.file_uploader("Video file", type=["mp4", "mov", "mkv", "webm"])
    else:
        video_url = st.text_input("Public video URL")

    if st.button("Process video", type="primary"):
        if not uploaded_file and not video_url:
            st.error("Provide a file or a URL first.")
            return
        slug = slugify(uploaded_file.name if uploaded_file else video_url or "video")
        job_dir = pipeline.new_job_dir(slug)
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
                mode=mode,
                job_dir=job_dir,
                video_path=video_path,
                video_url=video_url,
                type=video_type,
                images=images,
            )
        except adversal_client.AdversalAuthRequiredError:
            st.session_state.auth_required = True
            st.rerun()
        except adversal_client.AdversalError as exc:
            st.error(str(exc))
        else:
            st.session_state.jobs[mode] = job
            st.rerun()


def render_failure(job: Job) -> None:
    st.error(f"Processing failed: {job.error or 'unknown error'}")
    if st.button("Start over"):
        del st.session_state.jobs[job.mode]
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Video Summarizer", layout="wide")
    st.session_state.setdefault("jobs", {})

    if render_auth_banner_if_needed():
        st.stop()

    st.title("Video Summarizer")
    mode = st.sidebar.selectbox("Mode", list(modes.MODE_CONFIG))
    st.session_state.llm_option = st.sidebar.selectbox(
        "LLM backend",
        options=list(llm.LLM_OPTIONS),
        format_func=lambda key: llm.LLM_OPTIONS[key].label,
    )
    render_quota_sidebar()
    render_resume_picker()
    render_clear_runs()

    video_type, images = modes.MODE_CONFIG[mode]
    job = st.session_state.jobs.get(mode)

    if job is None:
        render_submit_form(mode, video_type, images)
    elif job.status == "RUNNING":
        pipeline.render_job_progress(mode)
    elif job.status == "FAILED":
        render_failure(job)
    else:
        modes.MODE_RENDERERS[mode](job)


if __name__ == "__main__":
    main()
