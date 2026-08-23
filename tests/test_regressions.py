# ruff: noqa: ANN001, ANN003, ANN202, INP001, PLR2004, S101, SLF001

import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient

import adversal_client
import app
import artifacts
import llm
import modes
import pipeline
import vector_store
import visual_evidence


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


def test_download_filenames_use_safe_original_stem() -> None:
    assert artifacts.download_filename("My Lecture.mp4", "blog_post", "md") == (
        "My_Lecture_blog_post.md"
    )
    assert artifacts.download_filename("folder/Quarterly.demo.mov", "notes", "md") == (
        "Quarterly_demo_notes.md"
    )
    assert artifacts.download_filename("محاضرة.mp4", "notes", "md") == "محاضرة_notes.md"
    assert artifacts.download_filename("../?.mp4", "notes", "md") == "video_notes.md"


def test_download_all_contains_core_and_cached_generated_outputs(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# Notes\n\nGrounded content", encoding="utf-8")
    job = pipeline.Job(
        mode="Source analysis",
        request_id="request-1",
        output_dir=str(tmp_path),
        source_name="My Lecture.mp4",
        status="COMPLETED",
    )

    bundle = artifacts.build_all_downloads_bundle(
        job,
        {"blog_post": "# Blog post", "meeting_summary": "# Meeting summary"},
    )

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {
            "My_Lecture_notes.md",
            "My_Lecture_native_bundle.zip",
            "My_Lecture_okf_0_2_bundle.zip",
            "My_Lecture_blog_post.md",
            "My_Lecture_meeting_summary.md",
        }
        assert archive.read("My_Lecture_blog_post.md") == b"# Blog post"
        with zipfile.ZipFile(io.BytesIO(archive.read("My_Lecture_native_bundle.zip"))) as native:
            assert native.namelist() == ["notes.md"]
        with zipfile.ZipFile(io.BytesIO(archive.read("My_Lecture_okf_0_2_bundle.zip"))) as okf:
            assert {"index.md", "video.md"} <= set(okf.namelist())


def test_submit_job_persists_analysis_settings(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_process_video(**kwargs):
        calls.append(kwargs)
        return "request-1"

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
        start_time="00:10",
        end_time="01:20",
        timestamps=["00:20", "00:40"],
        source_name="lecture.mp4",
    )

    assert job.video_type == "lesson"
    assert job.image_density == "generous"
    assert job.start_time == "00:10"
    assert job.end_time == "01:20"
    assert job.timestamps == ["00:20", "00:40"]
    assert job.source_name == "lecture.mp4"
    assert calls == [
        {
            "video_path": "lecture.mp4",
            "video_url": None,
            "output_path": str(tmp_path),
            "type": "lesson",
            "images": "generous",
            "start_time": "00:10",
            "end_time": "01:20",
            "timestamps": ["00:20", "00:40"],
        }
    ]


def test_adversal_process_error_preserves_remote_message(monkeypatch) -> None:
    monkeypatch.setattr(
        adversal_client,
        "_call_tool",
        lambda *_args, **_kwargs: "Video URL download timed out after 10 minutes.",
    )

    with pytest.raises(adversal_client.AdversalError) as exc_info:
        adversal_client.process_video(video_url="https://example.com/video", output_path="out")
    assert str(exc_info.value) == "Video URL download timed out after 10 minutes."


def test_adversal_authentication_must_report_success(monkeypatch) -> None:
    monkeypatch.setattr(
        adversal_client,
        "_call_tool",
        lambda *_args, **_kwargs: "AUTHENTICATION FAILED.\n\nBrowser flow expired.",
    )

    with pytest.raises(adversal_client.AdversalError) as exc_info:
        adversal_client.authenticate()
    assert "AUTHENTICATION FAILED" in str(exc_info.value)


def test_adversal_status_parsing_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(
        adversal_client,
        "_call_tool",
        lambda *_args, **_kwargs: "UNKNOWN — no job found for request_id request-1.",
    )

    result = adversal_client.check_video_status("request-1")

    assert result.status == "UNKNOWN"
    assert result.error == "UNKNOWN — no job found for request_id request-1."

    monkeypatch.setattr(
        adversal_client,
        "_call_tool",
        lambda *_args, **_kwargs: "HTTP connection error while recovering: offline",
    )
    with pytest.raises(adversal_client.AdversalError) as exc_info:
        adversal_client.check_video_status("request-1")
    assert str(exc_info.value) == "HTTP connection error while recovering: offline"


def test_adversal_connection_is_reused_and_reset_after_failure(monkeypatch) -> None:
    created = []

    class FakeConnection:
        def __init__(self) -> None:
            self.closed = False
            self.fail = False
            created.append(self)

        def call_tool(self, tool_name, _arguments):
            if self.fail:
                error_message = "connection lost"
                raise OSError(error_message)
            return SimpleNamespace(
                content=[],
                structuredContent={"result": f"{tool_name}: ok"},
                isError=False,
            )

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(adversal_client, "_MCPConnection", FakeConnection)
    monkeypatch.setattr(adversal_client, "_connection", None)

    assert adversal_client._call_tool("first", {}) == "first: ok"
    assert adversal_client._call_tool("second", {}) == "second: ok"
    assert len(created) == 1

    created[0].fail = True
    with pytest.raises(adversal_client.AdversalError):
        adversal_client._call_tool("broken", {})
    assert created[0].closed

    assert adversal_client._call_tool("reconnected", {}) == "reconnected: ok"
    assert len(created) == 2


def test_requested_frames_are_contained_and_discovered(tmp_path: Path) -> None:
    requested_dir = tmp_path / "requested_frames"
    requested_dir.mkdir()
    frame = requested_dir / "00-20.jpg"
    frame.write_bytes(b"frame")
    (requested_dir / "ignore.txt").write_text("not an image", encoding="utf-8")

    assert pipeline.find_requested_frames(tmp_path) == [frame.resolve()]


def test_timestamp_input_accepts_commas_and_lines() -> None:
    assert app._parse_timestamps("00:10, 00:20\n35") == ["00:10", "00:20", "35"]


def test_legacy_job_records_get_focused_processing_defaults(tmp_path: Path, monkeypatch) -> None:
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(
        json.dumps(
            {
                "request-1": {
                    "mode": "Source analysis",
                    "request_id": "request-1",
                    "output_dir": str(tmp_path),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline, "JOBS_FILE", jobs_file)

    job = pipeline.list_saved_jobs()[0]

    assert job.start_time is None
    assert job.end_time is None
    assert job.timestamps == []


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


def test_visual_evidence_is_resumable_and_path_safe(tmp_path: Path, monkeypatch) -> None:
    image_dir = tmp_path / "frames"
    image_dir.mkdir()
    first = image_dir / "frame_00_10-slide.jpg"
    second = image_dir / "frame_00_20-code.jpg"
    first.write_bytes(b"first-image")
    second.write_bytes(b"second-image")
    (tmp_path / "notes.md").write_text(
        "# Slides\n\n![Slide](frames/frame_00_10-slide.jpg)\n\n"
        "* * *\n\n# Code\n\n![Code](frames/frame_00_20-code.jpg)\n\n"
        "![Unsafe](../outside.jpg)",
        encoding="utf-8",
    )
    job = pipeline.Job(
        mode="Source analysis", request_id="visual-job", output_dir=str(tmp_path)
    )
    calls = []

    def fake_describe(image, *, context, option_key):
        calls.append((image.path.name, context, option_key))
        if len(calls) == 2:
            message = "provider rejected image"
            raise RuntimeError(message)
        return f"Description of {image.path.name}"

    monkeypatch.setattr(visual_evidence.llm, "describe_image", fake_describe)

    with pytest.raises(RuntimeError, match="provider rejected"):
        visual_evidence.build_evidence(job, llm.DEFAULT_LLM_OPTION)

    assert [item.relative_path for item in visual_evidence.load_evidence(job)] == [
        "frames/frame_00_10-slide.jpg"
    ]

    monkeypatch.setattr(
        visual_evidence.llm,
        "describe_image",
        lambda image, **_kwargs: f"Description of {image.path.name}",
    )
    completed = visual_evidence.build_evidence(job, llm.DEFAULT_LLM_OPTION)

    assert len(completed) == 2
    assert completed[0].timestamp == "00:10"
    assert all("outside" not in item.relative_path for item in completed)


def test_qdrant_searches_text_and_described_frames(monkeypatch) -> None:
    client = QdrantClient(location=":memory:")

    def fake_embed(texts):
        return [
            [1.0, 0.0] if "diagram" in text.lower() else [0.0, 1.0]
            for text in texts
        ]

    monkeypatch.setattr(vector_store.llm, "embed", fake_embed)
    frame = visual_evidence.FrameEvidence(
        relative_path="frames/diagram.jpg",
        alt="Architecture",
        heading="System design",
        timestamp="01:20",
        content_hash="hash",
        caption="A diagram linking the API to Qdrant.",
        provider="openai",
        model="vision-model",
    )
    vector_store.index_video(
        request_id="mixed-job",
        source_name="Demo",
        notes="spoken notes",
        chunks=[modes.Chunk("Transcript", "spoken notes", "00:10")],
        frames=[frame],
        evidence_hash="visual-hash",
        client=client,
    )

    text_hits, frame_hits = vector_store.search_video_evidence(
        "mixed-job", "diagram", client=client
    )

    assert [hit.kind for hit in text_hits] == ["text"]
    assert [(hit.kind, hit.image_path) for hit in frame_hits] == [
        ("frame", "frames/diagram.jpg")
    ]


def test_openai_multimodal_request_contains_image_data_url(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"png-bytes")
    requests = []

    class FakeCompletions:
        def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="description"))]
            )

    monkeypatch.setattr(
        llm,
        "_openai_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
    )

    result = llm._chat_openai(
        "vision-model",
        "system",
        "question",
        [llm.ImageInput(image_path, "Frame 1")],
    )

    content = requests[0]["messages"][1]["content"]
    assert result == "description"
    assert content[1] == {"type": "text", "text": "Frame 1"}
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")


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
        "VIDEO_SUMMARIZER_DATA_DIR": "/data",
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


def test_cached_generated_documents_are_scoped_to_job_and_backend(monkeypatch) -> None:
    state = {
        "meeting_digests": {
            ("active-job", "backend-a"): "active meeting",
            ("other-job", "backend-a"): "other meeting",
        },
        "blog_drafts": {
            ("active-job", "backend-a"): "active blog",
            ("active-job", "backend-b"): "other backend blog",
        },
    }
    monkeypatch.setattr(modes.st, "session_state", state)
    job = pipeline.Job(mode="Source analysis", request_id="active-job", output_dir="unused")

    assert modes.cached_generated_documents(job, "backend-a") == {
        "meeting_summary": "active meeting",
        "blog_post": "active blog",
    }


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
