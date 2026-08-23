# Coding Conventions

## Core Sections (Required)

### 1) Naming Rules

| Item | Rule | Example | Evidence |
|------|------|---------|----------|
| Files | Lowercase snake case | `adversal_client.py` | tracked Python files |
| Functions/methods | Snake case; leading underscore for module-private helpers | `_extract_status`, `render_submit_form` | `pipeline.py`, `app.py` |
| Types/interfaces | Pascal case; dataclasses for plain records; `Literal` aliases for bounded strings | `Job`, `Chunk`, `VideoType` | `pipeline.py`, `modes.py`, `adversal_client.py` |
| Constants/env vars | Upper snake case | `POLL_INTERVAL_SECONDS`, `OPENAI_API_KEY` | `pipeline.py`, `.env.example` |

### 2) Formatting and Linting

- Formatter/linter: Ruff configured in `pyproject.toml`; line length 100.
- Lint selection: `ALL`, excluding docstrings, copyright notice, formatter-conflicting comma/string rules, and `PLR0913`.
- Type checker: ty targets Python 3.13 through `[tool.ty.environment]`.
- Current check result: `uv run ruff check .` and `uv run ty check` both passed on 2026-08-23.
- Commands: `uv run ruff check .`, `uv run ruff format .`, `uv run ty check`.

### 3) Import and Module Conventions

- Imports follow standard-library, third-party, then project grouping as enforced by Ruff.
- Root modules use absolute imports such as `import pipeline`; no relative imports or barrel modules exist.
- `from __future__ import annotations` appears where deferred annotations are useful; `TYPE_CHECKING` guards type-only imports.
- Public exports are implicit; no `__all__` policy exists.

### 4) Error and Logging Conventions

- Integration layer: `AdversalAuthRequiredError` separates authentication from general `AdversalError`; invalid local argument combinations raise `ValueError`.
- UI layer: expected Adversal errors are caught and displayed with `st.error`; authentication sets session state and reruns.
- LLM SDK errors, malformed persisted JSON, missing result files and Qdrant failures currently propagate to Streamlit.
- Logging: no logging library, structured fields, metrics or tracing are configured.
- Sensitive data: API keys are read from environment or gitignored `.env`; code does not log key values. `[TODO]` No explicit error-redaction or telemetry policy exists.

### 5) Testing Conventions

- Tests live in `tests/` and use the `test_*.py` naming pattern.
- Tests use plain `assert`, `tmp_path`, and `monkeypatch`; no shared `conftest.py` fixtures exist.
- Regression tests name the behavior they protect, for example `test_upload_path_stays_inside_job_directory`.
- Coverage expectation: `[TODO]` no coverage tool or threshold is configured.

### 6) Evidence

- `pyproject.toml`
- `app.py`
- `pipeline.py`
- `adversal_client.py`
- `tests/test_regressions.py`
- `.env.example`
- `uv run ruff check .`
- `uv run ty check`
