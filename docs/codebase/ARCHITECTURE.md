# Architecture

## Core Sections (Required)

### 1) Architectural Style

- Style: a small layered Streamlit application with adapters around external services.
- Structure: UI orchestration (`app.py`) calls workflow and persistence (`pipeline.py`), artifact and export logic (`artifacts.py`), feature renderers (`modes.py`), Qdrant storage (`vector_store.py`), and integration adapters.
- Constraints: one trusted user and one process; Streamlit reruns; multi-minute asynchronous Adversal jobs; file-backed resume support; a fresh MCP subprocess per tool call; and an optional private Docker deployment with a persistent `/data` mount.

### 2) System Flow

```text
Streamlit widget -> local upload or public URL -> adversal-cli over MCP stdio
-> Adversal background job -> 8-second fragment polling -> notes.md + images
-> one workspace -> notes/frames/exports, Qdrant RAG, or selected LLM output
```

1. `app.py:main()` initializes one active workspace job, selects the chat backend, and dispatches current state.
2. `app.py:render_submit_form()` stores an upload under `runs/<job>/` or passes a URL, then calls `pipeline.submit_job()`.
3. `pipeline.submit_job()` calls `adversal_client.process_video()`, extracts a request ID, creates a `Job`, and persists it in `runs/jobs.json`.
4. `pipeline.render_job_progress()` polls `check_video_status()` every 8 seconds through `st.fragment`; terminal status is persisted and triggers rerender.
5. Completed jobs expose Notes, Key frames, Ask, and Create. `modes.CREATE_RENDERERS` selects one of seven generated outputs, and the workspace header packages core and already-cached outputs through Download All.
6. Ask embeds chapter-aware chunks with OpenAI and stores/searches them in local Qdrant with a request-ID filter.
7. `llm.chat()` dispatches grounded prompts to OpenAI, Agnes through the OpenAI-compatible client, or Gemini.

Authentication branch: an Adversal response containing `AUTHENTICATION REQUIRED` becomes `AdversalAuthRequiredError`; `app.py` sets session state, shows an authentication banner, invokes browser OAuth, then reruns.

### 3) Layer/Module Responsibilities

| Layer or module | Owns | Must not own | Evidence |
|-----------------|------|--------------|----------|
| Presentation/orchestration (`app.py`) | Widgets, active workspace routing, destructive-run confirmation | MCP protocol and provider SDK construction | `app.py` |
| Workflow/persistence (`pipeline.py`) | `Job`, status polling, local JSON/file paths, common rendering | Mode-specific prompts and provider credentials | `pipeline.py` |
| Artifact layer (`artifacts.py`) | Safe frame resolution, portable filenames, native/OKF exports, and Download All packaging | UI state or remote service calls | `artifacts.py` |
| Feature layer (`modes.py`) | Prompts, chunking, RAG chat, generated-output UI, and active-backend cache discovery | Adversal transport | `modes.py` |
| Vector store (`vector_store.py`) | Qdrant collection, indexing, payload filtering and retrieval | Chat generation or Streamlit UI | `vector_store.py` |
| Adversal adapter (`adversal_client.py`) | MCP subprocess/session, tool calls, tool-error translation | Streamlit rendering | `adversal_client.py` |
| LLM adapter (`llm.py`) | Environment-backed clients, model dispatch, embeddings | Job/session persistence | `llm.py` |
| Observability (`observability.py`) | Rerun-safe terminal/file logging, rotation, levels, and secret redaction | User content or secret persistence | `observability.py` |
| Container runtime (`Dockerfile`, `container-entrypoint.sh`) | Reproducible Space image and persistent path mapping | Multi-user coordination or application authentication | deployment files |

### 4) Reused Patterns

| Pattern | Where found | Why it exists |
|---------|-------------|---------------|
| Adapter | `adversal_client.py`, `llm.py` | Isolates MCP and provider SDK details from UI/features |
| Strategy table | `llm._DISPATCH`, `modes.CREATE_RENDERERS` | Selects provider or output behavior without branching chains |
| Data transfer object | `pipeline.Job`, `modes.Chunk`, `llm.LLMOption` | Carries persisted job, retrieval and provider data |
| Streamlit session cache | Generated documents, index-ready markers and chats in `modes.py` | Preserves generated state across reruns for one browser session |
| Persistent vector store | `runs/qdrant/` through `vector_store.py` | Reuses embeddings across sessions and filters retrieval by active request |
| File-backed registry | `runs/jobs.json` | Resumes Adversal jobs after app restart |
| Deferred export composition | `app.render_workspace()`, `artifacts.build_all_downloads_bundle()` | Builds the aggregate ZIP only when clicked and makes no provider call |

### 5) Known Architectural Risks

- `jobs.json` locking is process-local; multiple server processes would not share it.
- Generated mode caches are session-local and disappear when the browser session ends.
- Persistent Qdrant local mode supports this single process; multi-process deployment needs Qdrant Server or Cloud.
- The private Docker target preserves state in one mounted bucket but does not isolate several users from each other.
- The Windows `quality` workflow runs dependency sync, Ruff, ty, and pytest; non-Windows behavior is not covered by CI.

### 6) Evidence

- `README.md`
- `app.py`
- `pipeline.py`
- `modes.py`
- `artifacts.py`
- `vector_store.py`
- `adversal_client.py`
- `llm.py`
- `observability.py`
- `Dockerfile`
- `container-entrypoint.sh`
- `tests/test_regressions.py`
- `.github/workflows/ci.yml`
