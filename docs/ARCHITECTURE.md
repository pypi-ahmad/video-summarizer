# Technical reference

This document describes how Video Summarizer is built: the modules, the data flow, the Adversal integration, and the non-obvious decisions behind them. It reflects the code as it exists in this repository - if something here disagrees with the source, the source is right.

Audience: someone extending or debugging this app, not just running it. For "how do I use this," see [USAGE.md](./USAGE.md).

## Index

- [Module map](#module-map)
- [Job lifecycle](#job-lifecycle)
- [The Adversal integration](#the-adversal-integration)
- [Async polling in a synchronous framework](#async-polling-in-a-synchronous-framework)
- [Response-shape handling](#response-shape-handling)
- [The five modes](#the-five-modes)
- [The multi-provider LLM layer](#the-multi-provider-llm-layer)
- [Persistence](#persistence)
- [Known limitations](#known-limitations)

## Module map

| File | Responsibility |
| --- | --- |
| `app.py` | Streamlit entry point. Page config, sidebar (mode, LLM backend, quota, resume, danger zone), and top-level dispatch by job state (`IDLE` / `RUNNING` / `FAILED` / `COMPLETED`). |
| `adversal_client.py` | Stateless MCP stdio wrapper around `adversal-cli`. One function per Adversal tool call. |
| `pipeline.py` | The `Job` dataclass, `runs/jobs.json` persistence, the async status-polling fragment, and a markdown renderer that handles local image references. |
| `modes.py` | The five mode configs and renderers, plus the knowledge-base chunking/embedding/retrieval logic. |
| `llm.py` | Provider-agnostic `chat()`/`embed()` wrapper over OpenAI, Agnes AI, and Google Gemini. |

Runtime dependencies point inward from orchestration to adapters:

```text
app.py -> adversal_client.py, llm.py, modes.py, pipeline.py
modes.py -> llm.py, pipeline.py
pipeline.py -> adversal_client.py
```

`adversal_client.py` and `llm.py` do not import application modules. Nothing imports `app.py`.

## Job lifecycle

A mode is idle when it has no `Job`. After submission, a `Job` (`pipeline.Job`) moves through three stored states, tracked in `st.session_state.jobs[mode]` and mirrored to `runs/jobs.json`:

```
no job --submit_job()--> RUNNING --check_video_status()--> COMPLETED
                           |                                 |
                           +-----------> FAILED <-------------+
```

- **No job**: the mode has no `Job` object yet. `app.py` renders the submit form.
- **RUNNING**: `submit_job()` returned a `request_id`. `pipeline.render_job_progress()` (an `st.fragment(run_every=8)`) polls `check_video_status` until it leaves this state.
- **COMPLETED**: `notes.md` and images exist in the job's `output_path`. `app.py` dispatches to the mode's renderer.
- **FAILED**: the pipeline errored. `app.py` shows `job.error` and a "Start over" button that clears the job from session state (the `runs/jobs.json` entry is left in place for the resume picker's history).

Each session stores at most one selected job per mode. The completed view has no per-mode **New job** control. A fresh session can submit another job for that mode; earlier `runs/<job>/` directories and `jobs.json` entries remain until all runs are cleared.

## The Adversal integration

Adversal is not a REST API. `adversal-cli` (PyPI) is a local executable that speaks MCP over stdio. `adversal_client.py` is deliberately **stateless**: every public function (`process_video`, `check_video_status`, `check_remaining_quota`, `authenticate`) spawns a brand-new `adversal-cli` subprocess, does one `session.call_tool(...)`, and exits.

```python
async def _call_tool(tool_name, arguments):
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool_name, arguments=arguments)
        ...
```

This works because Adversal's job registry persists across subprocess restarts, as documented in the module and project README. A fresh subprocess can query a `request_id` submitted by an earlier subprocess. It also fits Streamlit's execution model: every interaction reruns the script, so each operation can open and close its own MCP session.

### Why exceptions are raised outside the `async with` block

```python
async def _call_tool(tool_name, arguments):
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        ...
        is_error = result.isError
        structured = result.structuredContent
    # raised here, not above
    if "AUTHENTICATION REQUIRED" in text.upper():
        raise AdversalAuthRequiredError(text)
    ...
```

`stdio_client`/`ClientSession` use `anyio` task groups internally. An exception raised *inside* an `async with` block that wraps a task group gets re-raised as a `BaseExceptionGroup` when that block exits - a plain `except AdversalAuthRequiredError:` at the call site will not match an exception group containing it. This was a real bug caught during live testing: the auth-required path was silently falling through to an unhandled traceback instead of triggering the UI's auth banner. The fix is to compute everything needed inside the block, then raise after it exits cleanly.

## Async polling in a synchronous framework

Streamlit reruns the whole script on every interaction; there's no server-push. Adversal's `process_video` returns a `request_id` in seconds while the actual pipeline runs for minutes in the background. `pipeline.render_job_progress()` bridges this with `st.fragment(run_every=8)`:

```python
@st.fragment(run_every=POLL_INTERVAL_SECONDS)
def render_job_progress(mode: str) -> None:
    job = st.session_state.jobs[mode]
    if job.status != "RUNNING":
        return
    ...
    result = adversal_client.check_video_status(job.request_id)
    ...
    if status in ("COMPLETED", "FAILED"):
        job.status, job.error = status, error
        _save_job(job)
        st.rerun()
```

Only the fragment's own container re-executes on the timer - the rest of the page (sidebar, other widgets) stays interactive. On a terminal status, the fragment triggers a full `st.rerun()`; `app.py`'s top-level dispatch then sees the new `job.status` and stops calling the fragment. Each tick spawns a fresh `adversal-cli` subprocess (see above), so the cost of polling is one subprocess spawn + MCP handshake every 8 seconds while a job is running.

## Response-shape handling

The adapter accepts either structured dictionaries or textual tool output. `pipeline._extract_request_id()` first checks `request_id`, `requestId`, and `id`, then applies a bounded regular expression to serialized output. `_extract_status()` uses a structured `status` key when present, otherwise scans textual output for `COMPLETED`, `FAILED`, `RUNNING`, or `UNKNOWN`.

This compatibility logic is coupled to Adversal's response wording. Changes to either parser need focused unit cases plus a live integration check.

## The five modes

Every mode shares one pipeline (`pipeline.submit_job` / `render_job_progress` / `load_completed_notes`) and differs only in the `type`/`images` request and what happens after the notes are read from disk:

| Mode | `type` | `images` | Post-processing |
| --- | --- | --- | --- |
| Study notes | `lesson` | `selective` | None - rendered as-is |
| Meeting/webinar summarizer | `meeting` | `minimal` | `llm.chat()` &rarr; Decisions/Action Items digest |
| Searchable knowledge base | `generic` | `selective` | Chunk + embed + cosine search + chat loop |
| Content triage | `generic` | `minimal` | `llm.chat()` &rarr; watch/skim/skip digest |
| Video &rarr; blog post | `lesson` | `generous` | Cached session draft &rarr; title/intro/conclusion |

`modes.MODE_CONFIG` maps mode name to `(type, images)`; `modes.MODE_RENDERERS` maps mode name to its render function. `app.py` never branches on mode name directly beyond looking these two dicts up.

### Rendering markdown with local images

`st.markdown()` does not resolve local image file paths in `![alt](path)` syntax - it expects a URL. `pipeline.render_markdown_with_images()` splits the notes text on image references and calls `st.image()` (which does read local paths) for each one, interleaved with `st.markdown()` for the surrounding text.

### Knowledge-base chunking and retrieval

`modes.split_notes_into_chunks()` splits on Adversal's own chapter separator (`* * *`) and headings rather than a generic token-based splitter - Adversal already produces a reasonable chaptering, so there's no reason to re-derive one. Each chunk records its heading and a timestamp parsed from the nearest `frame_MM_SS-*.jpg` reference in that chunk's text.

Retrieval is plain NumPy cosine similarity (`modes.search_kb()`) over embeddings cached to `<job_dir>/kb_index.npz`. No vector database - a single video's notes top out at a few hundred chunks, well within what an `argsort` over a small matrix handles instantly.

## The multi-provider LLM layer

`llm.py` exposes one `chat(system, user, option_key)` function dispatching to three providers, all configured in `llm.LLM_OPTIONS`:

| Option key | Provider | Model | Effort/thinking |
| --- | --- | --- | --- |
| `openai-gpt-5.6-luna` | OpenAI | `gpt-5.6-luna` | `reasoning_effort="medium"` |
| `agnes-2.5-flash` | Agnes AI | `agnes-2.5-flash` | (not set) |
| `gemini-3.5-flash-lite` | Google Gemini | `gemini-3.5-flash-lite` | `thinking_level=MEDIUM` |
| `gemini-3.7-flash` | Google Gemini | `gemini-3.7-flash` | `thinking_level=MEDIUM` |

Agnes AI is OpenAI-compatible - `_agnes_client()` is just an `openai.OpenAI` client pointed at `https://apihub.agnes-ai.com/v1` with `AGNES_API_KEY`. Gemini uses the `google-genai` SDK's `ThinkingConfig(thinking_level=...)`, which is the Gemini-3-and-later mechanism (the older `thinking_budget` token-count approach is a Gemini-2.5-and-earlier concept and isn't used here).

`app.py` stores the sidebar's selection in `st.session_state.llm_option`; `modes._active_llm_option()` reads it with a default fallback so every mode's `llm.chat()` call responds to the sidebar switch without each mode needing its own plumbing.

`embed()` always uses OpenAI's `text-embedding-3-small`, independent of the selected chat backend - the knowledge-base mode's retrieval quality isn't part of the provider-switching feature, and mixing embedding spaces across providers would silently break cosine search if the backend were ever switched mid-session.

## Persistence

`runs/<unix_ts>_<slug>/` holds an uploaded file under its submitted filename, `notes.md`, extracted images, and (for KB mode) `kb_index.npz`. `runs/jobs.json` is a flat dictionary keyed by `request_id`, holding every submitted `Job` via `dataclasses.asdict`. It is updated on submission and terminal status changes. This makes the sidebar's "Resume a previous job" picker work after a closed tab or restarted server.

## Known limitations

- **Auth is machine-local.** Adversal's OAuth sign-in opens a browser on whatever machine runs the Streamlit *server* process, not the viewer's machine. Fine for local single-user use; not solved for a shared/remote deployment.
- **One job per mode.** No confirmation before a new submission overwrites the in-flight/completed job for that mode.
- **No response schema guarantee.** The free-text response handling in `pipeline.py` (see above) is based on live-observed behavior, not a documented contract - Adversal could change response wording without notice.
- **No automatic cleanup.** `runs/` grows indefinitely; the sidebar's "Clear all runs" is manual-only.
- **Rerun cost.** Meeting and triage outputs are regenerated on every full Streamlit rerun while their completed job is selected. Blog drafts and KB indexes use session-state caches.
- **Shared local persistence.** `jobs.json` uses an unlocked read-modify-write cycle and job directories use second-resolution names. Concurrent sessions can collide or lose updates.
- **Path trust.** Uploaded filenames and Markdown image references are used as filesystem paths without enforcing containment inside the job directory.
- **KB cache trust.** `kb_index.npz` is loaded with `allow_pickle=True`; only trusted local run directories should be opened until this is removed.
- **No automated regression suite.** pytest is installed, but the repository currently has no tests or CI workflow. Ruff and ty are the only configured gates.
