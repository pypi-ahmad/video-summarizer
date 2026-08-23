# Codebase Structure

## Core Sections (Required)

### 1) Top-Level Map

| Path | Purpose | Evidence |
|------|---------|----------|
| `app.py` | Streamlit entry point, source submission and process-once workspace routing | `main()`, `render_submit_form()`, `render_workspace()` |
| `adversal_client.py` | Stateless MCP stdio adapter around `adversal-cli` | `_call_tool()`, public wrapper functions |
| `pipeline.py` | Job model, JSON persistence, polling, result loading and image-aware Markdown rendering | `Job`, `_save_job()`, `render_job_progress()` |
| `artifacts.py` | Safe frame discovery and native/OKF exports | `find_local_images()`, `build_okf_bundle()` |
| `modes.py` | Qdrant chunking/chat and seven LLM-generated outputs | `CREATE_RENDERERS`, `render_knowledge_base()` |
| `vector_store.py` | Persistent local Qdrant indexing and request-filtered search | `index_video()`, `search_video()` |
| `llm.py` | OpenAI-compatible and Gemini provider dispatch; OpenAI embeddings | `LLM_OPTIONS`, `chat()`, `embed()` |
| `launch.cmd` | Self-contained Windows uv/Python/venv bootstrap and Streamlit launch | batch commands |
| `launch.bat` | Legacy compatibility launcher without the pinned/locked guarantees of `launch.cmd` | batch commands |
| `tests/` | Focused security, caching, and persistence regressions | `tests/test_regressions.py` |
| `docs/` | User guide, technical architecture, and codebase onboarding material | `docs/USAGE.md`, `docs/ARCHITECTURE.md` |
| `runs/` | Gitignored runtime jobs, notes, images, index and `jobs.json` | `pipeline.RUNS_DIR`, `.gitignore` |
| `docs/codebase/` | Generated codebase onboarding documents | this documentation set |

### 2) Entry Points

- Main runtime entry: `app.py:main()`.
- Secondary entry points: canonical `launch.cmd` bootstraps `.venv` and starts `.venv\Scripts\python.exe -m streamlit run app.py`; legacy `launch.bat` performs a less strict uv setup; `adversal-cli` is spawned as an integration subprocess, not an application entry point.
- Entry selection: Streamlit executes `app.py`; its `if __name__ == "__main__"` guard calls `main()`.

### 3) Module Boundaries

| Boundary | What belongs here | What must not be here |
|----------|-------------------|------------------------|
| `app.py` | Page composition, widgets, session routing | Provider SDK calls or MCP transport details |
| `adversal_client.py` | Adversal tool arguments, MCP lifecycle, integration error translation | Streamlit UI or mode-specific presentation |
| `pipeline.py` | Shared job lifecycle and local result files | Provider-specific LLM prompts |
| `artifacts.py` | Adversal artifact parsing and portable exports | UI routing or remote service calls |
| `modes.py` | Generated-output prompts, chunking, RAG chat and presentation | MCP session construction or Qdrant lifecycle details |
| `vector_store.py` | Qdrant collection, point payload and filtering policy | Streamlit presentation or MCP transport |
| `llm.py` | LLM clients, model selection and embeddings | Streamlit state or job persistence |

These are observed boundaries, not enforced package rules.

### 4) Naming and Organization Rules

- File naming: lowercase `snake_case.py`; application modules live at repository root.
- Directory organization: flat, layer-oriented layout rather than a package or feature tree.
- Python symbols: `snake_case` functions/variables, `PascalCase` dataclasses/exceptions, uppercase constants.
- Imports: absolute imports between root modules; no aliases or relative imports.
- Generated/runtime directories (`runs/`, caches, knowledge graphs) are not source modules.

### 5) Evidence

- repository scan output captured during documentation generation
- `app.py`
- `pipeline.py`
- `modes.py`
- `adversal_client.py`
- `llm.py`
- `.gitignore`
- `tests/test_regressions.py`
