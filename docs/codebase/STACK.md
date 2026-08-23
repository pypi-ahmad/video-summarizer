# Technology Stack

## Core Sections (Required)

### 1) Runtime Summary

| Area | Value | Evidence |
|------|-------|----------|
| Primary language | Python | `pyproject.toml`, five tracked `*.py` files |
| Runtime + version | CPython 3.13.13; project accepts Python 3.13+ | `.python-version`, `pyproject.toml` |
| Package manager | uv with a committed lockfile | `uv.lock`, `launch.bat` |
| Module/build system | Root-level Python modules; no package build backend | `app.py`, `pyproject.toml` |

### 2) Production Frameworks and Dependencies

Versions below are the resolved versions reported by `uv tree --depth 1` on 2026-08-23.

| Dependency | Version | Role in system | Evidence |
|------------|---------|----------------|----------|
| Streamlit | 1.62.0 | Web UI, session state, fragments, chat, rendering | `app.py`, `pipeline.py`, `modes.py` |
| adversal-cli | 0.1.2 | Local MCP server for video processing and OAuth | `adversal_client.py`, `uv.lock` |
| MCP | 1.29.0 | stdio client transport to `adversal-cli` | `adversal_client.py` |
| OpenAI | 3.3.1 | OpenAI/Agnes chat clients and OpenAI embeddings | `llm.py` |
| google-genai | 2.19.0 | Gemini chat client | `llm.py` |
| NumPy | 2.5.2 | Embedding cache and cosine-similarity retrieval | `modes.py` |
| python-dotenv | 1.2.3 | Optional local `.env` loading | `llm.py`, `.env.example` |
| torch / torchvision | 2.13.0+cu132 / 0.28.0+cu132 | CUDA 13.2 dependencies from explicit PyTorch index; direct application use is not present | `pyproject.toml`, `uv.lock` |

### 3) Development Toolchain

| Tool | Purpose | Evidence |
|------|---------|----------|
| uv | Python, environment, dependency, and command management | `launch.bat`, `uv.lock` |
| Ruff 0.16.4 | Linting and formatting | `pyproject.toml`, `uv tree --depth 1` |
| ty 0.0.74 | Static type checking for Python 3.13 | `pyproject.toml`, `uv tree --depth 1` |
| pytest 9.1.1 | Regression test runner | `pyproject.toml`, `tests/test_regressions.py` |

### 4) Key Commands

```bash
uv sync --all-groups
uv run streamlit run app.py
uv run pytest -q
uv run ruff check .
uv run ty check
```

Windows bootstrap and launch: `launch.bat`.

### 5) Environment and Config

- Config sources: `pyproject.toml`, `.python-version`, `.env.example`, environment variables.
- Required env vars depend on selected functionality: `OPENAI_API_KEY`, `AGNES_API_KEY`, `GOOGLE_API_KEY`; `OPENAI_BASE_URL` is optional.
- `OPENAI_API_KEY` is also required for knowledge-base embeddings regardless of selected chat backend.
- Runtime constraints: `uv`, Python 3.13+, `adversal-cli`, and `ffmpeg`/`ffprobe` on `PATH`; OAuth opens a browser on the server machine.
- No container or CI configuration was detected.

### 6) Evidence

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `.env.example`
- `launch.bat`
- `llm.py`
