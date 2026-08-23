# Testing Patterns

## Core Sections (Required)

### 1) Test Stack and Commands

- Primary test framework: pytest 9.1.1 is installed in the `dev` dependency group.
- Assertion/mocking tools: pytest assertions are available; no mocking dependency or established mock pattern exists.
- Commands:

```bash
uv run pytest -q              # exits with "no tests ran"
uv run ruff check .           # passes
uv run ty check               # passes
# [TODO] no unit-only, integration/E2E, or coverage command exists
```

### 2) Test Layout

- Test file placement: none exists.
- Naming convention: `[TODO]` not established by repository examples.
- Setup files: no `conftest.py`, pytest config, fixtures or CI workflow exists.

### 3) Test Scope Matrix

| Scope | Covered? | Typical target | Notes |
|-------|----------|----------------|-------|
| Unit | No | Request/status parsing, chunking, cosine search, path handling | Pure functions exist but have no regression checks |
| Integration | No | MCP adapter, provider dispatch, JSON/NPZ persistence | External SDK and filesystem boundaries are untested |
| E2E | No | Upload/URL through completion and mode rendering | No Streamlit app tests or smoke automation exists |

### 4) Mocking and Isolation Strategy

- Main mocking approach: `[TODO]` none established.
- Isolation guarantees: `[TODO]` no temporary `RUNS_DIR`, environment isolation or session-state reset fixture exists.
- Likely isolation boundary: mock public functions in `adversal_client.py` and `llm.py`, and redirect filesystem paths to pytest `tmp_path`; this is a recommendation, not current behavior.
- Common failure mode: absent tests allow parser, persistence, rerun-cost and path-containment regressions to ship undetected.

### 5) Coverage and Quality Signals

- Coverage tool + threshold: `[TODO]` not configured.
- Current reported coverage: `[TODO]` no coverage run is possible without tests.
- Static quality: Ruff and ty pass on 2026-08-23.
- Known gaps: every runtime flow; especially upload paths, Markdown images, MCP result parsing, job persistence, status transitions, LLM dispatch and KB indexing/search.

### 6) Evidence

- `pyproject.toml`
- `uv.lock`
- `uv run pytest -q` output: `no tests ran in 0.01s`
- `uv run ruff check .` output: `All checks passed!`
- `uv run ty check` output: `All checks passed!`
- CodeGraph reports no covering tests for core symbols.

