# External Integrations

## Core Sections (Required)

### 1) Integration Inventory

| System | Type | Purpose | Auth model | Criticality | Evidence |
|--------|------|---------|------------|-------------|----------|
| Adversal via `adversal-cli` | Local MCP stdio subprocess plus remote backend | Video analysis, screenshots, status, quota | Browser OAuth persisted by Adversal locally | High | `adversal_client.py`, `README.md` |
| OpenAI | HTTPS API through SDK | Chat and all knowledge-base embeddings | `OPENAI_API_KEY`; optional `OPENAI_BASE_URL` | Medium | `llm.py`, `.env.example` |
| Agnes AI | OpenAI-compatible HTTPS API | Optional chat backend | `AGNES_API_KEY` | Medium | `llm.py` |
| Google Gemini | HTTPS API through `google-genai` | Optional chat backend | `GOOGLE_API_KEY` | Medium | `llm.py` |
| Qdrant Client | Embedded persistent vector database | Store and retrieve active-video chunks | Local filesystem; no credentials | Medium | `vector_store.py` |
| Public video sources | URL input consumed by Adversal/its `yt-dlp` dependency | Remote video ingestion | Source-dependent | High | `app.py`, `README.md`, `uv.lock` |
| Hugging Face Spaces and Buckets | Private Docker hosting and persistent mounted storage | Optional hosted runtime | Hugging Face account; provider keys configured as Space secrets | Optional | `Dockerfile`, `container-entrypoint.sh`, `README.md` |

### 2) Data Stores

| Store | Role | Access layer | Key risk | Evidence |
|-------|------|--------------|----------|----------|
| `runs/jobs.json` | Persistent request registry | `pipeline._load_all_jobs()`, `_save_job()` | Lock is process-local; malformed files still fail loading | `pipeline.py` |
| `runs/<job>/` | Uploaded video, `notes.md`, and extracted images | `app.py`, `pipeline.Job`, `artifacts.py` | Unbounded retention; data is stored unencrypted | source modules |
| `runs/qdrant/` | Shared local Qdrant collection with request-filtered video chunks | `vector_store.index_video()` | Single-process local-mode lock; deleted by Clear all runs | `vector_store.py` |
| Streamlit session state | Active job, generated documents, index-ready markers and chat history | `app.py`, `modes.py` | Lost on session expiry; separate from disk registry and Qdrant | source modules |
| `/data` bucket mount | Hosted runs, Adversal OAuth state, and rotating logs | `container-entrypoint.sh` | One shared trust boundary; private single-user deployment only | deployment files |

No external database, queue, event bus, service mesh or cache is configured.

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
- All seven generated documents are cached by request ID and selected backend in session state. Long-note reduction may make multiple sequential LLM calls before final generation.

### 5) Observability for Integrations

- UI shows Adversal status and last-check time; expected tool errors are displayed.
- Application events go to the terminal and a rotating file with component names, request IDs where applicable, timing, statuses, and error types.
- Log filtering omits user content and redacts configured provider keys and common token forms. Metrics, distributed traces, cost counters, and health endpoints do not exist.
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
- `observability.py`
- `Dockerfile`
- `container-entrypoint.sh`
