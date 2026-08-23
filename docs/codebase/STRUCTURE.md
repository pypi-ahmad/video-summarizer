# Codebase Structure

## Core Sections (Required)

### 1) Top-Level Map

| Path | Purpose | Evidence |
|------|---------|----------|
| `app.py` | Streamlit entry point, global UI, source submission, mode dispatch | `main()`, `render_submit_form()` |
| `adversal_client.py` | Stateless MCP stdio adapter around `adversal-cli` | `_call_tool()`, public wrapper functions |
| `pipeline.py` | Job model, JSON persistence, polling, result loading and image-aware Markdown rendering | `Job`, `_save_job()`, `render_job_progress()` |
| `modes.py` | Five output modes, LLM post-processing, embedding index and search | `MODE_CONFIG`, `MODE_RENDERERS` |
| `llm.py` | OpenAI-compatible and Gemini provider dispatch; OpenAI embeddings | `LLM_OPTIONS`, `chat()`, `embed()` |
| `launch.bat` | Windows environment bootstrap and Streamlit launch | batch commands |
| `runs/` | Gitignored runtime jobs, notes, images, index and `jobs.json` | `pipeline.RUNS_DIR`, `.gitignore` |
| `docs/codebase/` | Generated codebase onboarding documents | this documentation set |

### 2) Entry Points

- Main runtime entry: `app.py:main()`.
- Secondary entry points: `launch.bat` starts `uv run streamlit run app.py`; `adversal-cli` is spawned as an integration subprocess, not an application entry point.
- Entry selection: Streamlit executes `app.py`; its `if __name__ == "__main__"` guard calls `main()`.

### 3) Module Boundaries

| Boundary | What belongs here | What must not be here |
|----------|-------------------|------------------------|
| `app.py` | Page composition, widgets, session routing | Provider SDK calls or MCP transport details |
| `adversal_client.py` | Adversal tool arguments, MCP lifecycle, integration error translation | Streamlit UI or mode-specific presentation |
| `pipeline.py` | Shared job lifecycle and local result files | Provider-specific LLM prompts |
| `modes.py` | Mode behavior, prompts, retrieval and presentation | MCP session construction or credential lookup |
| `llm.py` | LLM clients, model selection and embeddings | Streamlit state or job persistence |

These are observed boundaries, not enforced package rules.

### 4) Naming and Organization Rules

- File naming: lowercase `snake_case.py`; all five Python modules live at repository root.
- Directory organization: flat, layer-oriented layout rather than a package or feature tree.
- Python symbols: `snake_case` functions/variables, `PascalCase` dataclasses/exceptions, uppercase constants.
- Imports: absolute imports between root modules; no aliases or relative imports.
- Generated/runtime directories (`runs/`, caches, knowledge graphs) are not source modules.

### 5) Evidence

- `docs/codebase/.codebase-scan.txt` (scan-time tree; removed after documentation validation)
- `app.py`
- `pipeline.py`
- `modes.py`
- `adversal_client.py`
- `llm.py`
- `.gitignore`

