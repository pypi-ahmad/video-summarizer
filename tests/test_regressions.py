# ruff: noqa: ANN001, ANN002, ANN003, ANN202, INP001, PLR2004, S101, SLF001

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import app
import modes
import pipeline


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


def test_kb_cache_disables_pickle(tmp_path: Path, monkeypatch) -> None:
    notes = "# Chapter\n\nContent"
    job = pipeline.Job(mode="Searchable knowledge base", request_id="job", output_dir=str(tmp_path))
    job.notes_path.write_text(notes, encoding="utf-8")
    chunks = modes.split_notes_into_chunks(notes)
    np.savez(
        tmp_path / "kb_index.npz",
        embeddings=np.array([[1.0, 0.0]]),
        texts=[chunk.text for chunk in chunks],
    )
    original_load = np.load
    calls = []

    def tracked_load(*args, **kwargs):
        calls.append(kwargs)
        return original_load(*args, **kwargs)

    monkeypatch.setattr(modes.np, "load", tracked_load)

    modes.build_or_load_kb_index(job)

    assert calls == [{"allow_pickle": False}]


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
