"""Mode configs + the five thin per-mode renderers built on the shared pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import streamlit as st

import llm
import pipeline
from pipeline import Job

if TYPE_CHECKING:
    import adversal_client

MODE_CONFIG: dict[str, tuple[adversal_client.VideoType, adversal_client.ImageDensity]] = {
    "Study notes": ("lesson", "selective"),
    "Meeting/webinar summarizer": ("meeting", "minimal"),
    "Searchable knowledge base": ("generic", "selective"),
    "Content triage": ("generic", "minimal"),
    "Video -> blog post": ("lesson", "generous"),
}

CHAPTER_SPLIT_RE = re.compile(r"\n\s*\*\s*\*\s*\*\s*\n")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)
FRAME_TS_RE = re.compile(r"frame_(\d{2})_(\d{2})-")


@dataclass
class Chunk:
    heading: str
    text: str
    timestamp: str | None


def split_notes_into_chunks(md_text: str, max_chars: int = 1500) -> list[Chunk]:
    """Chunk on Adversal's own chapter separator and headings, not a generic splitter."""
    chunks: list[Chunk] = []
    for section in CHAPTER_SPLIT_RE.split(md_text):
        if not section.strip():
            continue
        heading_match = HEADING_RE.search(section)
        heading = heading_match.group(2).strip() if heading_match else "Untitled"
        ts_match = FRAME_TS_RE.search(section)
        timestamp = f"{ts_match.group(1)}:{ts_match.group(2)}" if ts_match else None
        buf = ""
        for para in section.split("\n\n"):
            if buf and len(buf) + len(para) > max_chars:
                chunks.append(Chunk(heading, buf.strip(), timestamp))
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            chunks.append(Chunk(heading, buf.strip(), timestamp))
    return chunks


def build_or_load_kb_index(job: Job) -> tuple[list[Chunk], np.ndarray]:
    cache_path = job.output_path / "kb_index.npz"
    notes = pipeline.load_completed_notes(job)
    chunks = split_notes_into_chunks(notes)
    if cache_path.exists():
        cached = np.load(cache_path, allow_pickle=True)
        if list(cached["texts"]) == [c.text for c in chunks]:
            return chunks, cached["embeddings"]
    embeddings = np.array(llm.embed([c.text for c in chunks]))
    np.savez(cache_path, embeddings=embeddings, texts=[c.text for c in chunks])
    return chunks, embeddings


def search_kb(
    query: str, chunks: list[Chunk], embeddings: np.ndarray, top_k: int = 5
) -> list[tuple[Chunk, float]]:
    query_vec = np.array(llm.embed([query])[0])
    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec) + 1e-8
    sims = embeddings @ query_vec / norms
    top_indices = np.argsort(-sims)[:top_k]
    return [(chunks[i], float(sims[i])) for i in top_indices]


def _active_llm_option() -> str:
    return st.session_state.get("llm_option", llm.DEFAULT_LLM_OPTION)


def render_study_notes(job: Job) -> None:
    notes = pipeline.load_completed_notes(job)
    pipeline.render_markdown_with_images(notes, job.output_path)


def render_meeting_summary(job: Job) -> None:
    notes = pipeline.load_completed_notes(job)
    digest = llm.chat(
        system=(
            "Extract a compact digest from these meeting notes. "
            "Use two sections: 'Decisions' and 'Action Items' (owner if named). "
            "Bullet points only, no preamble."
        ),
        user=notes,
        option_key=_active_llm_option(),
    )
    st.subheader("Action Items / Decisions")
    st.markdown(digest)
    st.divider()
    st.subheader("Full notes")
    pipeline.render_markdown_with_images(notes, job.output_path)


def render_triage(job: Job) -> None:
    notes = pipeline.load_completed_notes(job)
    digest = llm.chat(
        system=(
            "You help a reviewer decide whether to watch a long video. "
            "Give a 3-5 bullet summary of what it covers, then one line: "
            "'Recommendation: watch in full / skim / skip', with a one-sentence reason."
        ),
        user=notes,
        option_key=_active_llm_option(),
    )
    st.subheader("Triage digest")
    st.markdown(digest)
    with st.expander("Full notes"):
        pipeline.render_markdown_with_images(notes, job.output_path)


def render_blog_post(job: Job) -> None:
    notes = pipeline.load_completed_notes(job)
    if "blog_draft" not in st.session_state:
        st.session_state.blog_draft = {}
    if job.request_id not in st.session_state.blog_draft:
        st.session_state.blog_draft[job.request_id] = llm.chat(
            system=(
                "Turn these video notes into a polished blog post: add a title, "
                "a short intro hook, and a brief conclusion. Keep the existing "
                "chapter headings, body text, and image references as-is."
            ),
            user=notes,
            option_key=_active_llm_option(),
        )
    draft = st.session_state.blog_draft[job.request_id]
    pipeline.render_markdown_with_images(draft, job.output_path)
    st.download_button("Download as Markdown", draft, file_name="blog_post.md")


def render_knowledge_base(job: Job) -> None:
    if "kb_index" not in st.session_state:
        st.session_state.kb_index = {}
    if job.request_id not in st.session_state.kb_index:
        with st.spinner("Building searchable index..."):
            st.session_state.kb_index[job.request_id] = build_or_load_kb_index(job)
    chunks, embeddings = st.session_state.kb_index[job.request_id]

    if "kb_chat" not in st.session_state:
        st.session_state.kb_chat = {}
    history = st.session_state.kb_chat.setdefault(job.request_id, [])

    for role, content in history:
        with st.chat_message(role):
            st.markdown(content)

    question = st.chat_input("Ask something about the video")
    if question:
        history.append(("user", question))
        with st.chat_message("user"):
            st.markdown(question)
        hits = search_kb(question, chunks, embeddings)
        context = "\n\n".join(f"[{c.heading} ~{c.timestamp or '?'}]\n{c.text}" for c, _ in hits)
        answer = llm.chat(
            system=(
                "Answer the question using only the provided video excerpts. "
                "If the excerpts don't cover it, say so. Cite chapter headings you used."
            ),
            user=f"Excerpts:\n{context}\n\nQuestion: {question}",
            option_key=_active_llm_option(),
        )
        history.append(("assistant", answer))
        with st.chat_message("assistant"):
            st.markdown(answer)
            with st.expander("Sources"):
                for chunk, score in hits:
                    ts = chunk.timestamp or "n/a"
                    st.markdown(f"**{chunk.heading}** (~{ts}, score {score:.2f})")

    with st.expander("Full notes"):
        pipeline.render_markdown_with_images(pipeline.load_completed_notes(job), job.output_path)


MODE_RENDERERS = {
    "Study notes": render_study_notes,
    "Meeting/webinar summarizer": render_meeting_summary,
    "Searchable knowledge base": render_knowledge_base,
    "Content triage": render_triage,
    "Video -> blog post": render_blog_post,
}
