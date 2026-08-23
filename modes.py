"""Mode configs + thin per-mode renderers built on the shared pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass

import streamlit as st

import artifacts
import llm
import observability
import pipeline
import vector_store
from pipeline import Job

FRAME_TS_RE = re.compile(r"frame_(\d{2})_(\d{2})-")
LONG_NOTES_THRESHOLD = 50_000
REDUCTION_BATCH_CHARS = 30_000

logger = observability.get_logger("modes")


@dataclass
class Chunk:
    heading: str
    text: str
    timestamp: str | None


def split_notes_into_chunks(md_text: str, max_chars: int = 1500) -> list[Chunk]:
    """Chunk on Adversal's own chapter separator and headings, not a generic splitter."""
    chunks: list[Chunk] = []
    for section in artifacts.split_sections(md_text):
        ts_match = FRAME_TS_RE.search(section.markdown)
        timestamp = f"{ts_match.group(1)}:{ts_match.group(2)}" if ts_match else None
        buf = ""
        for para in section.markdown.split("\n\n"):
            if buf and len(buf) + len(para) > max_chars:
                chunks.append(Chunk(section.heading, buf.strip(), timestamp))
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            chunks.append(Chunk(section.heading, buf.strip(), timestamp))
    return chunks


def build_or_load_kb_index(job: Job) -> list[Chunk]:
    notes = pipeline.load_completed_notes(job)
    chunks = split_notes_into_chunks(notes)
    vector_store.index_video(
        request_id=job.request_id,
        source_name=job.source_name,
        notes=notes,
        chunks=chunks,
    )
    return chunks


def search_kb(query: str, job: Job, top_k: int = 5) -> list[vector_store.SearchHit]:
    return vector_store.search_video(job.request_id, query, top_k=top_k)


def _active_llm_option() -> str:
    return st.session_state.get("llm_option", llm.DEFAULT_LLM_OPTION)


def _cached_chat(cache_name: str, job: Job, system: str, user: str) -> str:
    option_key = _active_llm_option()
    cache = st.session_state.setdefault(cache_name, {})
    key = (job.request_id, option_key)
    if key not in cache:
        logger.info(
            "document.cache_miss cache=%s request_id=%s backend=%s",
            cache_name,
            job.request_id,
            option_key,
        )
        cache[key] = llm.chat(system=system, user=user, option_key=option_key)
    else:
        logger.debug(
            "document.cache_hit cache=%s request_id=%s backend=%s",
            cache_name,
            job.request_id,
            option_key,
        )
    return cache[key]


def _split_for_generation(text: str, max_chars: int = REDUCTION_BATCH_CHARS) -> list[str]:
    """Split Markdown on paragraph boundaries while keeping every batch bounded."""
    batches: list[str] = []
    buffer = ""
    for paragraph in text.split("\n\n"):
        if len(paragraph) > max_chars:
            if buffer:
                batches.append(buffer.strip())
                buffer = ""
            batches.extend(
                paragraph[start : start + max_chars]
                for start in range(0, len(paragraph), max_chars)
            )
        elif buffer and len(buffer) + len(paragraph) + 2 > max_chars:
            batches.append(buffer.strip())
            buffer = paragraph
        else:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
    if buffer:
        batches.append(buffer.strip())
    return batches


def _reduce_notes(notes: str, goal: str, *, preserve_images: bool) -> str:
    source = notes
    round_number = 0
    image_instruction = (
        " Preserve every Markdown image reference exactly as written with its nearby context."
        if preserve_images
        else ""
    )
    while len(source) > LONG_NOTES_THRESHOLD:
        round_number += 1
        batches = _split_for_generation(source, REDUCTION_BATCH_CHARS)
        logger.info(
            "reduction.round_started round=%s input_chars=%s batches=%s preserve_images=%s",
            round_number,
            len(source),
            len(batches),
            preserve_images,
        )
        summaries = [
            llm.chat(
                system=(
                    f"Condense this portion of video notes for this final task: {goal}. "
                    "Keep only grounded facts, steps, examples, and source headings. "
                    "Do not add information. Keep the result under 1,200 words."
                    f"{image_instruction}"
                ),
                user=batch,
                option_key=_active_llm_option(),
            )
            for batch in batches
        ]
        reduced = "\n\n---\n\n".join(summaries)
        logger.info(
            "reduction.round_completed round=%s output_chars=%s",
            round_number,
            len(reduced),
        )
        if len(reduced) >= len(source):
            return reduced
        source = reduced
    return source


def _cached_document(
    cache_name: str,
    job: Job,
    *,
    system: str,
    reduction_goal: str,
    preserve_images: bool = False,
) -> str:
    option_key = _active_llm_option()
    cache = st.session_state.setdefault(cache_name, {})
    key = (job.request_id, option_key)
    if key not in cache:
        logger.info(
            "document.generation_started cache=%s request_id=%s backend=%s",
            cache_name,
            job.request_id,
            option_key,
        )
        notes = pipeline.load_completed_notes(job)
        source = (
            _reduce_notes(notes, reduction_goal, preserve_images=preserve_images)
            if len(notes) > LONG_NOTES_THRESHOLD
            else notes
        )
        cache[key] = llm.chat(system=system, user=source, option_key=option_key)
        logger.info(
            "document.generation_completed cache=%s request_id=%s backend=%s",
            cache_name,
            job.request_id,
            option_key,
        )
    else:
        logger.debug(
            "document.cache_hit cache=%s request_id=%s backend=%s",
            cache_name,
            job.request_id,
            option_key,
        )
    return cache[key]


def _render_generated_document(
    job: Job,
    *,
    cache_name: str,
    heading: str,
    file_name: str,
    system: str,
    reduction_goal: str,
    preserve_images: bool = False,
) -> None:
    st.subheader(heading)
    with st.spinner(f"Generating {heading.lower()}..."):
        document = _cached_document(
            cache_name,
            job,
            system=system,
            reduction_goal=reduction_goal,
            preserve_images=preserve_images,
        )
    pipeline.render_markdown_with_images(document, job.output_path)
    st.download_button("Download as Markdown", document, file_name=file_name)
    with st.expander("Source notes"):
        pipeline.render_markdown_with_images(pipeline.load_completed_notes(job), job.output_path)


def render_study_notes(job: Job) -> None:
    notes = pipeline.load_completed_notes(job)
    pipeline.render_markdown_with_images(notes, job.output_path)


def render_meeting_summary(job: Job) -> None:
    _render_generated_document(
        job,
        cache_name="meeting_digests",
        heading="Action items and decisions",
        file_name="meeting_summary.md",
        reduction_goal="extract meeting decisions and action items",
        system=(
            "Extract a compact digest from these meeting notes. "
            "Use two sections: 'Decisions' and 'Action Items' (owner if named). "
            "Bullet points only, no preamble."
        ),
    )


def render_triage(job: Job) -> None:
    _render_generated_document(
        job,
        cache_name="triage_digests",
        heading="Content triage",
        file_name="content_triage.md",
        reduction_goal="decide whether a reviewer should watch, skim, or skip the video",
        system=(
            "You help a reviewer decide whether to watch a long video. "
            "Give a 3-5 bullet summary of what it covers, then one line: "
            "'Recommendation: watch in full / skim / skip', with a one-sentence reason."
        ),
    )


def render_blog_post(job: Job) -> None:
    _render_generated_document(
        job,
        cache_name="blog_drafts",
        heading="Blog post",
        file_name="blog_post.md",
        reduction_goal="create a grounded blog post that preserves useful screenshots",
        preserve_images=True,
        system=(
            "Turn these video notes into a polished blog post: add a title, "
            "a short intro hook, and a brief conclusion. Keep the existing "
            "chapter headings, body text, and image references as-is."
        ),
    )


def render_knowledge_base(job: Job) -> None:
    ready = st.session_state.setdefault("kb_ready", set())
    if job.request_id not in ready:
        logger.info("knowledge_base.index_requested request_id=%s", job.request_id)
        with st.spinner("Building searchable index..."):
            build_or_load_kb_index(job)
        ready.add(job.request_id)
    else:
        logger.debug("knowledge_base.index_ready request_id=%s", job.request_id)

    if "kb_chat" not in st.session_state:
        st.session_state.kb_chat = {}
    history = st.session_state.kb_chat.setdefault(job.request_id, [])

    for role, content in history:
        with st.chat_message(role):
            st.markdown(content)

    question = st.chat_input("Ask something about the video")
    if question:
        logger.info(
            "knowledge_base.question_started request_id=%s question_chars=%s",
            job.request_id,
            len(question),
        )
        history.append(("user", question))
        with st.chat_message("user"):
            st.markdown(question)
        hits = search_kb(question, job)
        context = "\n\n".join(
            f"[{hit.heading} ~{hit.timestamp or '?'}]\n{hit.text}" for hit in hits
        )
        answer = llm.chat(
            system=(
                "Answer the question using only the provided video excerpts. "
                "If the excerpts don't cover it, say so. Cite chapter headings you used."
            ),
            user=f"Excerpts:\n{context}\n\nQuestion: {question}",
            option_key=_active_llm_option(),
        )
        history.append(("assistant", answer))
        logger.info(
            "knowledge_base.question_completed request_id=%s sources=%s answer_chars=%s",
            job.request_id,
            len(hits),
            len(answer),
        )
        with st.chat_message("assistant"):
            st.markdown(answer)
            with st.expander("Sources"):
                for hit in hits:
                    ts = hit.timestamp or "n/a"
                    st.markdown(f"**{hit.heading}** (~{ts}, score {hit.score:.2f})")

    with st.expander("Full notes"):
        pipeline.render_markdown_with_images(pipeline.load_completed_notes(job), job.output_path)


def render_quiz_and_flashcards(job: Job) -> None:
    _render_generated_document(
        job,
        cache_name="quiz_flashcard_packs",
        heading="Quiz and flashcards",
        file_name="quiz_flashcards.md",
        reduction_goal="create a grounded quiz, answer key, and flashcard study pack",
        system=(
            "Create a study pack using only these video notes. Include exactly 10 quiz "
            "questions: 6 multiple-choice questions with four labeled options and 4 "
            "short-answer questions. Then include a separate answer key with concise "
            "explanations, followed by exactly 15 flashcards formatted as 'Front' and "
            "'Back'. Cover the important chapters without repeating questions. Do not "
            "invent facts or claim transcript-level detail."
        ),
    )


def render_sop_guide(job: Job) -> None:
    _render_generated_document(
        job,
        cache_name="sop_guides",
        heading="SOP/how-to guide",
        file_name="sop_guide.md",
        reduction_goal="create an actionable SOP with relevant screenshots",
        preserve_images=True,
        system=(
            "Turn these video notes into a practical SOP/how-to guide using only supported "
            "information. Include Purpose, Prerequisites, numbered Procedure steps, "
            "Cautions, Verification checklist, and Troubleshooting. Reuse relevant "
            "Markdown image references exactly as written and place them near the matching "
            "step. Never invent an image path, missing step, or safety requirement. Omit a "
            "section when the notes do not support it."
        ),
    )


def render_interview_insights(job: Job) -> None:
    _render_generated_document(
        job,
        cache_name="interview_insight_packs",
        heading="Interview insight pack",
        file_name="interview_insights.md",
        reduction_goal="extract grounded interview themes, answers, and follow-up questions",
        system=(
            "Create an interview insight pack using only these video notes. Include an "
            "Executive summary, Key themes, Question-and-answer insights, Notable "
            "statements, and Suggested follow-up questions. Label notable statements as "
            "paraphrases; do not fabricate direct quotations, speakers, or sentiment. "
            "State when the notes do not identify a speaker or answer."
        ),
    )


def render_faq_article(job: Job) -> None:
    _render_generated_document(
        job,
        cache_name="faq_articles",
        heading="FAQ/help-center article",
        file_name="faq_article.md",
        reduction_goal="create a grounded FAQ and help-center article",
        preserve_images=True,
        system=(
            "Turn these video notes into a concise help-center article using only supported "
            "information. Include a descriptive title, Overview, clearly organized FAQ "
            "entries, Troubleshooting when supported, and Related topics. Reuse useful "
            "Markdown image references exactly as written and never invent links, product "
            "behavior, policies, or image paths."
        ),
    )


CREATE_RENDERERS = {
    "Meeting/webinar summarizer": render_meeting_summary,
    "Content triage": render_triage,
    "Video -> blog post": render_blog_post,
    "Quiz and flashcards": render_quiz_and_flashcards,
    "SOP/how-to guide": render_sop_guide,
    "Interview insight pack": render_interview_insights,
    "FAQ/help-center article": render_faq_article,
}
