# External Integrations

## Core Sections (Required)

### 1) Integration Inventory

| System | Type | Purpose | Auth model | Criticality | Evidence |
|--------|------|---------|------------|-------------|----------|
| Adversal via `adversal-cli` | Local MCP stdio subprocess plus remote backend | Video analysis, screenshots, status, quota | Browser OAuth persisted by Adversal locally | High | `adversal_client.py`, `README.md` |
| OpenAI | HTTPS API through SDK | Chat and all knowledge-base embeddings | `OPENAI_API_KEY`; optional `OPENAI_BASE_URL` | Medium | `llm.py`, `.env.example` |
| Agnes AI | OpenAI-compatible HTTPS API | Optional chat backend | `AGNES_API_KEY` | Medium | `llm.py` |
| Google Gemini | HTTPS API through `google-genai` | Optional chat backend | `GOOGLE_API_KEY` | Medium | `llm.py` |
| Public video sources | URL input consumed by Adversal/its `yt-dlp` dependency | Remote video ingestion | Source-dependent | High | `app.py`, `README.md`, `uv.lock` |

### 2) Data Stores

| Store | Role | Access layer | Key risk | Evidence |
|-------|------|--------------|----------|----------|
| `runs/jobs.json` | Persistent request registry | `pipeline._load_all_jobs()`, `_save_job()` | Non-atomic shared read-modify-write and malformed-file failure | `pipeline.py` |
| `runs/<job>/` | Uploaded video, `notes.md`, images and generated cache | `app.py`, `pipeline.Job` | Unbounded retention and path-containment gaps | `README.md`, `app.py`, `pipeline.py` |
| `kb_index.npz` | Local embedding cache per job | `modes.build_or_load_kb_index()` | Loaded with `allow_pickle=True` | `modes.py` |
| Streamlit session state | Per-browser job pointers, drafts, index and chat history | `app.py`, `modes.py` | Lost on session expiry; separate from disk registry | source modules |

No database, queue, event bus, service mesh or external cache is configured.

### 3) Secrets and Credentials Handling

- Credential sources: process environment first; optional local `.env` loaded without overriding existing values.
- `.env` is gitignored and `.env.example` contains names only; no hardcoded secret values were found in tracked source.
- Adversal credentials are owned by `adversal-cli` browser OAuth, not this application.
- Rotation/lifecycle: `[TODO]` provider-key rotation and revocation procedures are not documented.

### 4) Reliability and Failure Behavior

- Adversal tool-level errors become typed exceptions; authentication has a dedicated recovery UI.
- No explicit retry, exponential backoff, timeout or circuit breaker is configured for Adversal or LLM calls.
- Adversal status is polled every 8 seconds until `COMPLETED` or `FAILED`; `UNKNOWN` remains in polling state.
- No fallback provider is selected automatically when an LLM call fails.

### 5) Observability for Integrations

- UI shows Adversal status and last-check time; expected tool errors are displayed.
- No application logs, request correlation, metrics, traces, cost counters or health endpoints exist.
- LLM failures and latency lack provider-labelled UI handling.
- MCP subprocess stderr/diagnostic retention is `[TODO]`; source only consumes returned MCP content.

### 6) Evidence

- `adversal_client.py`
- `llm.py`
- `pipeline.py`
- `modes.py`
- `.env.example`
- `README.md`
- `uv.lock`

