# Testing Patterns

## Core Sections (Required)

### 1) Test Stack and Commands

- The test framework is pytest 9.1.1, installed in the `dev` dependency group.
- Tests use pytest assertions and its built-in `monkeypatch` fixture.
- Commands:

```bash
uv run pytest -q
uv run ruff check .
uv run ty check
# [TODO] no unit-only, integration/E2E, or coverage command exists
```

### 2) Test Layout

- Test files live under `tests/` and follow the `test_*.py` naming pattern.
- `pyproject.toml` adds the repository root to pytest's Python path.
- No `conftest.py` or shared fixtures exist. `.github/workflows/ci.yml` runs the quality gate on Windows for pushes and pull requests targeting `main`.

### 3) Test Scope Matrix

| Scope | Covered? | Typical target | Notes |
|-------|----------|----------------|-------|
| Unit | Partial | Upload paths, Markdown images, Adversal contracts/lifecycle, provider and multimodal payloads, resumable frame evidence, text/frame Qdrant filtering, exports, caching, logging | Thirty-four focused regressions exist |
| Integration | Partial | Concurrent JSON persistence and directory allocation | Uses temporary local files; external services remain mocked/uncovered |
| E2E | No | Upload/URL through completion and mode rendering | No automated live-service flow exists |

### 4) Mocking and Isolation Strategy

- `monkeypatch` replaces session state, provider clients, LLM calls, embeddings, logging limits and pipeline paths; Qdrant tests use its in-memory client.
- ZIP regressions inspect Download All members, nested native/OKF layouts, cached-output scoping, and safe Unicode-aware filenames without making external calls.
- `tmp_path` isolates uploaded files, indexes and job persistence.
- External Adversal and provider calls are not made by the regression suite.

### 5) Coverage and Quality Signals

- Coverage tool + threshold: `[TODO]` not configured.
- Current reported coverage: `[TODO]` no coverage tool is configured.
- Static quality: Ruff and ty pass on 2026-08-23.
- Known gaps: MCP result parsing, status transitions, full mode rendering, authentication and live provider behavior.

### 6) Evidence

- `pyproject.toml`
- `uv.lock`
- `tests/test_regressions.py`
- `tests/test_observability.py`
- `.github/workflows/ci.yml`
- `uv run pytest -q`
- `uv run ruff check .` output: `All checks passed!`
- `uv run ty check` output: `All checks passed!`
