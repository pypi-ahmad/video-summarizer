# ruff: noqa: ANN001, ANN003, ANN202, INP001, PLR2004, S101, SLF001

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from qdrant_client import QdrantClient

import app
import artifacts
import llm
import modes
import pipeline
import vector_store


def test_upload_path_stays_inside_job_directory(tmp_path: Path) -> None:
    for filename in ("../outside.mp4", "..\\outside.mp4", "C:\\outside.mp4"):
        destination = app._safe_upload_path(tmp_path, filename)
        assert destination.parent == tmp_path.resolve()
        assert destination.name == "outside.mp4"


def test_markdown_image_must_be_inside_base_directory(tmp_path: Path) -> None:
    base_dir = tmp_path / "job"
    base_dir.mkdir()
    image = base_dir / "frame.jpg"
    image.write_bytes(b"image")
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")

    assert pipeline._resolve_local_image(base_dir, "frame.jpg") == image.resolve()
    assert pipeline._resolve_local_image(base_dir, "../secret.jpg") is None
    assert pipeline._resolve_local_image(base_dir, str(outside.resolve())) is None


def test_native_and_okf_exports_include_only_safe_agent_artifacts(tmp_path: Path) -> None:
    image_dir = tmp_path / "img"
    image_dir.mkdir()
    (image_dir / "frame.jpg").write_bytes(b"frame")
    (tmp_path / "source.mp4").write_bytes(b"large-video")
    outside = tmp_path.parent / "outside.jpg"
    outside.write_bytes(b"secret")
    notes = (
        "# Introduction\n\nGrounded notes.\n\n"
        "![Slide](img/frame.jpg)\n\n![Unsafe](../outside.jpg)"
    )
    (tmp_path / "notes.md").write_text(notes, encoding="utf-8")
    job = pipeline.Job(
        mode="Source analysis",
        request_id="request-1",
        output_dir=str(tmp_path),
        source_name="Demo lecture",
        status="COMPLETED",
    )

    with zipfile.ZipFile(io.BytesIO(artifacts.build_native_bundle(job))) as native:
        assert set(native.namelist()) == {"notes.md", "img/frame.jpg"}

    with zipfile.ZipFile(io.BytesIO(artifacts.build_okf_bundle(job))) as okf:
        names = set(okf.namelist())
        chapter = next(name for name in names if name.startswith("chapters/"))
        chapter_text = okf.read(chapter).decode()
        assert {"index.md", "video.md", "assets/img/frame.jpg", chapter} <= names
        assert 'type: "Video Chapter"' in chapter_text
        assert "../assets/img/frame.jpg" in chapter_text
        assert "outside.jpg" not in names


def test_submit_job_persists_analysis_settings(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_process_video(**kwargs):
        calls.append(kwargs)
        return {"request_id": "request-1"}

    monkeypatch.setattr(pipeline.adversal_client, "process_video", fake_process_video)
    monkeypatch.setattr(pipeline, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "JOBS_FILE", tmp_path / "jobs.json")

    job = pipeline.submit_job(
        mode="Source analysis",
        job_dir=tmp_path,
        video_path="lecture.mp4",
        video_url=None,
        type="lesson",
        images="generous",
        source_name="lecture.mp4",
    )

    assert job.video_type == "lesson"
    assert job.image_density == "generous"
    assert job.source_name == "lecture.mp4"
    assert calls == [
        {
            "video_path": "lecture.mp4",
            "video_url": None,
            "output_path": str(tmp_path),
            "type": "lesson",
            "images": "generous",
        }
    ]


def test_qdrant_index_is_idempotent_and_filtered_by_video(monkeypatch) -> None:
    client = QdrantClient(location=":memory:")
    embedding_calls = []

    def fake_embed(texts):
        embedding_calls.append(list(texts))
        return [[1.0, 0.0] if "alpha" in text.lower() else [0.0, 1.0] for text in texts]

    monkeypatch.setattr(vector_store.llm, "embed", fake_embed)
    alpha_chunks = [modes.Chunk("Alpha", "alpha content", "00:10")]
    beta_chunks = [modes.Chunk("Beta", "beta content", "00:20")]

    vector_store.index_video(
        request_id="alpha-job",
        source_name="Alpha video",
        notes="alpha notes",
        chunks=alpha_chunks,
        client=client,
    )
    vector_store.index_video(
        request_id="alpha-job",
        source_name="Alpha video",
        notes="alpha notes",
        chunks=alpha_chunks,
        client=client,
    )
    vector_store.index_video(
        request_id="beta-job",
        source_name="Beta video",
        notes="beta notes",
        chunks=beta_chunks,
        client=client,
    )

    hits = vector_store.search_video("alpha-job", "alpha question", client=client)

    assert [(hit.heading, hit.text) for hit in hits] == [("Alpha", "alpha content")]
    assert embedding_calls.count(["alpha content"]) == 1
    assert client.count(vector_store.COLLECTION_NAME, exact=True).count == 2


def test_llm_result_is_cached_per_job_and_backend(monkeypatch) -> None:
    state = {"llm_option": "backend-a"}
    calls = []

    def fake_chat(*, system: str, user: str, option_key: str) -> str:
        calls.append((system, user, option_key))
        return f"digest-{option_key}"

    monkeypatch.setattr(modes.st, "session_state", state)
    monkeypatch.setattr(modes.llm, "chat", fake_chat)
    job = pipeline.Job(mode="Content triage", request_id="job", output_dir="unused")

    assert modes._cached_chat("digests", job, "system", "notes") == "digest-backend-a"
    assert modes._cached_chat("digests", job, "system", "notes") == "digest-backend-a"
    state["llm_option"] = "backend-b"
    assert modes._cached_chat("digests", job, "system", "notes") == "digest-backend-b"
    assert len(calls) == 2


def test_all_output_modes_have_matching_configs_and_renderers() -> None:
    expected_outputs = {
        "Meeting/webinar summarizer",
        "Content triage",
        "Video -> blog post",
        "Quiz and flashcards",
        "SOP/how-to guide",
        "Interview insight pack",
        "FAQ/help-center article",
    }

    assert set(modes.CREATE_RENDERERS) == expected_outputs
    assert set(app.VIDEO_TYPES.values()) == {"generic", "lesson", "interview", "meeting"}
    assert set(app.IMAGE_DENSITIES.values()) == {"minimal", "selective", "generous"}


def test_llm_provider_registry_has_fixed_models() -> None:
    assert llm.DEFAULT_LLM_OPTION == "openai-gpt-5.6-luna"
    assert {
        key: (option.label, option.provider, option.model)
        for key, option in llm.LLM_OPTIONS.items()
    } == {
        "openai-gpt-5.6-luna": ("OpenAI - GPT-5.6 Luna", "openai", "gpt-5.6-luna"),
        "agnes-2.5-flash": ("Agnes AI - Agnes 2.5 Flash", "agnes", "agnes-2.5-flash"),
        "gemini-3.5-flash-lite": (
            "Google - Gemini 3.5 Flash Lite",
            "gemini",
            "gemini-3.5-flash-lite",
        ),
        "gemini-3.7-flash": ("Google - Gemini 3.7 Flash", "gemini", "gemini-3.7-flash"),
    }


def test_openai_client_uses_environment_and_medium_reasoning(monkeypatch) -> None:
    constructor_calls = []
    request_calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            request_calls.append(kwargs)
            message = SimpleNamespace(content="openai result")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def fake_openai(**kwargs):
        constructor_calls.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    monkeypatch.setenv("OPENAI_API_KEY", "user-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setattr(llm, "OpenAI", fake_openai)

    assert llm._chat_openai("gpt-5.6-luna", "system", "user") == "openai result"
    assert constructor_calls == [
        {"api_key": "user-openai-key", "base_url": "https://gateway.example/v1"}
    ]
    assert request_calls == [
        {
            "model": "gpt-5.6-luna",
            "reasoning_effort": "medium",
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        }
    ]


def test_openai_client_omits_base_url_when_unset(monkeypatch) -> None:
    constructor_calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "user-openai-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(llm, "OpenAI", lambda **kwargs: constructor_calls.append(kwargs))

    llm._openai_client()

    assert constructor_calls == [{"api_key": "user-openai-key"}]


def test_agnes_client_uses_environment_and_official_endpoint(monkeypatch) -> None:
    constructor_calls = []
    monkeypatch.setenv("AGNES_API_KEY", "user-agnes-key")
    monkeypatch.setattr(llm, "OpenAI", lambda **kwargs: constructor_calls.append(kwargs))

    llm._agnes_client()

    assert constructor_calls == [
        {"api_key": "user-agnes-key", "base_url": "https://apihub.agnes-ai.com/v1"}
    ]
    assert llm.LLM_OPTIONS["agnes-2.5-flash"].model == "agnes-2.5-flash"


def test_gemini_models_use_environment_and_medium_thinking(monkeypatch) -> None:
    client_keys = []
    request_calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            request_calls.append(kwargs)
            return SimpleNamespace(text="gemini result")

    def fake_client(*, api_key: str):
        client_keys.append(api_key)
        return SimpleNamespace(models=FakeModels())

    monkeypatch.setenv("GOOGLE_API_KEY", "user-google-key")
    monkeypatch.setattr(llm.genai, "Client", fake_client)

    for model in ("gemini-3.5-flash-lite", "gemini-3.7-flash"):
        assert llm._chat_gemini(model, "system", "user") == "gemini result"

    assert client_keys == ["user-google-key", "user-google-key"]
    assert [call["model"] for call in request_calls] == [
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
    ]
    for call in request_calls:
        assert call["config"].thinking_config.thinking_level == llm.genai_types.ThinkingLevel.MEDIUM


def test_env_example_contains_safe_defaults() -> None:
    assignments = {
        name: value
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
        for name, value in [line.split("=", 1)]
    }

    assert assignments == {
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "",
        "AGNES_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "VIDEO_SUMMARIZER_LOG_LEVEL": "INFO",
    }


def test_generated_document_is_cached_per_job_and_backend(tmp_path: Path, monkeypatch) -> None:
    notes_path = tmp_path / "notes.md"
    notes_path.write_text("# Notes\n\nGrounded content", encoding="utf-8")
    state = {"llm_option": "backend-a"}
    calls = []

    def fake_chat(*, system: str, user: str, option_key: str) -> str:
        calls.append((system, user, option_key))
        return f"document-{option_key}"

    monkeypatch.setattr(modes.st, "session_state", state)
    monkeypatch.setattr(modes.llm, "chat", fake_chat)
    job = pipeline.Job(mode="Quiz and flashcards", request_id="job", output_dir=str(tmp_path))

    def generate() -> str:
        return modes._cached_document("documents", job, system="prompt", reduction_goal="goal")

    assert generate() == "document-backend-a"
    assert generate() == "document-backend-a"
    state["llm_option"] = "backend-b"
    assert generate() == "document-backend-b"
    assert len(calls) == 2


def test_long_notes_are_reduced_in_bounded_batches(monkeypatch) -> None:
    calls = []

    def fake_chat(*, system: str, user: str, option_key: str) -> str:
        calls.append((system, user, option_key))
        return "short summary"

    monkeypatch.setattr(modes, "LONG_NOTES_THRESHOLD", 20)
    monkeypatch.setattr(modes, "REDUCTION_BATCH_CHARS", 12)
    monkeypatch.setattr(modes.llm, "chat", fake_chat)
    monkeypatch.setattr(modes, "_active_llm_option", lambda: "backend")

    result = modes._reduce_notes(
        "first paragraph\n\nsecond paragraph", "make an SOP", preserve_images=True
    )

    assert result == "\n\n---\n\n".join(["short summary"] * 4)
    assert all(len(user) <= 12 for _, user, _ in calls)
    assert all(
        "Preserve every Markdown image reference exactly" in system for system, _, _ in calls
    )


def test_job_storage_handles_concurrent_updates_and_unique_directories(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "JOBS_FILE", tmp_path / "jobs.json")
    jobs = [
        pipeline.Job(mode="Study notes", request_id=f"job-{index}", output_dir="unused")
        for index in range(20)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(pipeline._save_job, jobs))
        directories = list(executor.map(lambda _: pipeline.new_job_dir("video"), range(20)))

    assert {job.request_id for job in pipeline.list_saved_jobs()} == {
        job.request_id for job in jobs
    }
    assert len(set(directories)) == 20
    assert not (tmp_path / "jobs.tmp").exists()
