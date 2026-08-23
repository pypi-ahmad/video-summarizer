# External Integrations

## Core Sections (Required)

### 1) Integration Inventory

| System | Type | Purpose | Auth model | Criticality | Evidence |
|--------|------|---------|------------|-------------|----------|
| Adversal via `adversal-cli` | One process-wide MCP stdio subprocess plus remote backend | Video analysis, screenshots, status, quota | Browser OAuth persisted by Adversal locally | High | `adversal_client.py`, `README.md` |
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
| Streamlit session state | Active job, generated documents used by Download All, index-ready markers and chat history | `app.py`, `modes.py` | Lost on session expiry; separate from disk registry and Qdrant | source modules |
| `/data` bucket mount | Hosted runs, Adversal OAuth state, and rotating logs | `container-entrypoint.sh` | One shared trust boundary; private single-user deployment only | deployment files |

The application does not configure an external database, message queue, event bus,
service mesh, or shared cache. `adversal_client.py` does use an in-process thread-safe
queue to serialize MCP calls onto the coroutine that owns the stdio session.

### 3) Secrets and Credentials Handling

- Credential sources: process environment first; optional local `.env` loaded without overriding existing values.
- `.env` is gitignored and `.env.example` contains names only; no hardcoded secret values were found in tracked source.
- Adversal credentials are owned by `adversal-cli` browser OAuth, not this application.
- Rotation/lifecycle: `[TODO]` provider-key rotation and revocation procedures are not documented.

### 4) Reliability and Failure Behavior

- Adversal tool responses are validated against per-tool success contracts; authentication has a dedicated recovery UI. Ordinary `{"result": ...}` failure text therefore remains an Adversal error instead of becoming a misleading missing-request-ID error.
- The first tool action starts one worker-owned MCP session. Later submission, status, quota, and authentication actions reuse it until application exit or transport failure.
- No automatic retry, exponential backoff, timeout or circuit breaker is configured for Adversal or LLM calls. Failed jobs can manually retry a status check with the same request ID.
- Adversal status is polled every 8 seconds until `COMPLETED` or `FAILED`; `UNKNOWN` becomes a failed state that can retry the same request ID.
- No fallback provider is selected automatically when an LLM call fails.
- All seven generated documents are cached by request ID and selected backend in session state. Long-note reduction may make multiple sequential LLM calls before final generation.
- Download All reads the active backend's existing cache entries and packages them with the three core downloads; it never invokes a provider or generates a missing document.

### 5) Observability for Integrations

- UI shows Adversal status and last-check time; expected tool errors are displayed.
- Application events go to the terminal and a rotating file with component names, request IDs where applicable, timing, statuses, and error types.
- Log filtering omits user content and redacts configured provider keys and common token forms. Metrics, distributed traces, cost counters, and health endpoints do not exist.
- LLM failures and latency lack provider-labelled UI handling.
- The application records wrapper lifecycle, timing, status, and error-type events, but it does not retain a separate structured archive of raw MCP subprocess diagnostics.

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
