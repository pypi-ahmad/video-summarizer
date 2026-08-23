# Architecture

## Core Sections (Required)

### 1) Architectural Style

- Primary style: small layered Streamlit application with adapters around external services.
- Classification: UI orchestration (`app.py`) calls shared workflow/persistence (`pipeline.py`), feature renderers (`modes.py`), and integration adapters (`adversal_client.py`, `llm.py`).
- Primary constraints: local single-user target; Streamlit reruns; multi-minute asynchronous Adversal jobs; file-backed resumability; fresh MCP subprocess per tool call.

### 2) System Flow

```text
Streamlit widget -> local upload or public URL -> adversal-cli over MCP stdio
-> Adversal background job -> 8-second fragment polling -> notes.md + images
-> selected mode renderer -> optional LLM/embedding call -> Streamlit output
```

1. `app.py:main()` initializes per-session jobs, selects mode/backend, and dispatches current state.
2. `app.py:render_submit_form()` stores an upload under `runs/<job>/` or passes a URL, then calls `pipeline.submit_job()`.
3. `pipeline.submit_job()` calls `adversal_client.process_video()`, extracts a request ID, creates a `Job`, and persists it in `runs/jobs.json`.
4. `pipeline.render_job_progress()` polls `check_video_status()` every 8 seconds through `st.fragment`; terminal status is persisted and triggers rerender.
5. `modes.MODE_RENDERERS` selects direct notes, meeting digest, triage digest, blog draft, or searchable knowledge-base behavior.
6. `llm.chat()` dispatches to OpenAI, Agnes through the OpenAI-compatible client, or Gemini. Knowledge-base mode uses OpenAI embeddings and NumPy cosine similarity.

Authentication branch: an Adversal response containing `AUTHENTICATION REQUIRED` becomes `AdversalAuthRequiredError`; `app.py` sets session state, shows an authentication banner, invokes browser OAuth, then reruns.

### 3) Layer/Module Responsibilities

| Layer or module | Owns | Must not own | Evidence |
|-----------------|------|--------------|----------|
| Presentation/orchestration (`app.py`) | Widgets, global session state, mode dispatch, destructive-run confirmation | MCP protocol and provider SDK construction | `app.py` |
| Workflow/persistence (`pipeline.py`) | `Job`, status polling, local JSON/file paths, common rendering | Mode-specific prompts and provider credentials | `pipeline.py` |
| Feature layer (`modes.py`) | Mode configuration, prompts, retrieval, mode UI | Adversal transport | `modes.py` |
| Adversal adapter (`adversal_client.py`) | MCP subprocess/session, tool calls, tool-error translation | Streamlit rendering | `adversal_client.py` |
| LLM adapter (`llm.py`) | Environment-backed clients, model dispatch, embeddings | Job/session persistence | `llm.py` |

### 4) Reused Patterns

| Pattern | Where found | Why it exists |
|---------|-------------|---------------|
| Adapter | `adversal_client.py`, `llm.py` | Isolates MCP and provider SDK details from UI/features |
| Strategy table | `llm._DISPATCH`, `modes.MODE_RENDERERS` | Selects provider or output behavior without branching chains |
| Data transfer object | `pipeline.Job`, `modes.Chunk`, `llm.LLMOption` | Carries persisted job, retrieval and provider data |
| Streamlit session cache | `blog_draft`, `kb_index`, `kb_chat` in `modes.py` | Preserves generated state across reruns for one browser session |
| File-backed registry | `runs/jobs.json` | Resumes Adversal jobs after app restart |

### 5) Known Architectural Risks

- Local paths and `jobs.json` are shared process-wide while session state is per user; concurrent sessions can collide or lose read-modify-write updates.
- Trust boundaries are implicit: uploaded filenames and generated Markdown image references become local filesystem paths without containment checks.
- Meeting and triage renderers call paid LLMs during every rerun; unlike blog and knowledge-base paths, results are not cached.
- No test or CI layer protects parsing, persistence, retrieval or integration-error behavior.

### 6) Evidence

- `README.md`
- `app.py`
- `pipeline.py`
- `modes.py`
- `adversal_client.py`
- `llm.py`

