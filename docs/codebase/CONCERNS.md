# Codebase Concerns

## Core Sections (Required)

### 1) Top Risks (Prioritized)

| Severity | Concern | Evidence | Impact | Suggested action |
|----------|---------|----------|--------|------------------|
| Medium | User-controlled public URL reaches downloader | `app.py`, `adversal_client.py` | The private hosted runtime could expose server-side network access | Add URL/network policy before enabling URL ingestion for untrusted users |
| Medium | Raw integration errors are displayed | `app.py` | Provider/tool details may reach UI | Add an error-redaction contract before shared deployment |
| Medium | Local Qdrant is single-process | `vector_store.py` | A second Streamlit process cannot safely share the embedded storage directory | Use Qdrant Server or Cloud before multi-process deployment |

### 2) Technical Debt

| Debt item | Why it exists | Where | Risk if ignored | Suggested fix |
|-----------|---------------|-------|-----------------|---------------|
| Partial exception handling | Adversal errors handled; file/LLM/Qdrant errors mostly left to Streamlit | `app.py`, `modes.py`, `vector_store.py` | Raw failure pages and poor recovery | Catch errors at owning UI boundary with provider/job context |
| Runtime storage has manual cleanup only | Local and private-hosted workflows retain completed artifacts | `runs/`, `/data/runs`, `app.py` | Disk or bucket growth | Keep manual cleanup for one trusted user; define retention before broader use |

### 3) Security Concerns

| Risk | OWASP category | Evidence | Current mitigation | Gap |
|------|----------------|----------|--------------------|-----|
| User-controlled public URL reaches downloader | A10 SSRF | `app.py`, `adversal_client.py`, `uv.lock` | Supported deployment is private and single-user | No scheme/host/network validation in this layer; downstream behavior is unverified |
| Raw integration errors shown in UI | A09 Security Logging and Monitoring Failures / information exposure | `app.py` error handlers and `modes.py` provider calls | Keys are not logged by application code | Error-redaction contract is absent |

### 4) Performance and Scaling Concerns

| Concern | Evidence | Current symptom | Scaling risk | Suggested improvement |
|---------|----------|-----------------|-------------|-----------------------|
| Serialized process-wide MCP session | `adversal_client._MCPConnection`, `_call_tool()` | One worker thread and queue run one tool call at a time | A long tool or recovery call delays quota, authentication, and status actions behind it | Retain the single-user boundary; add bounded call timeouts or separate connection ownership only if measured latency requires it |
| Full JSON registry rewrite per status change | `pipeline.py` | O(number of jobs) write | Slower as history grows | Use a database only when measured scale requires it |
| Embedded Qdrant local mode | `vector_store.py` | Serialized in-process access | Not suitable for multiple app processes or large shared corpora | Move the same client API to Qdrant Server or Cloud when deployment scope changes |

### 5) Fragile/High-Churn Areas

The repository history remains shallow and concentrated in a short development window,
so churn counts are too volatile to distinguish stable from fragile areas reliably.

| Area | Why fragile | Churn signal | Safe change strategy |
|------|-------------|-------------|----------------------|
| `app.py` + `pipeline.py` | Upload, persistence, polling and filesystem boundaries cross modules | Low-confidence short history | Keep focused path/persistence regressions passing |
| `modes.py` | Seven renderers plus reduction, chunking, and RAG chat | Broad feature responsibility | Test pure generation/chunk functions and rerun behavior separately |
| `adversal_client.py` | One daemon thread owns the async MCP context while synchronous callers wait on queued futures | Integration boundary with limited live-test coverage | Preserve same-coroutine context ownership, serialized calls, reset-on-transport-failure behavior, and mocked response-contract tests |

### 6) Confirmed Product Boundary

The supported remote path is a private Hugging Face Docker Space for one trusted user.
Public, protected-but-shared, and multi-process deployments remain unsupported because
they would share Adversal identity, run data, Qdrant state, and destructive controls.

### 7) Evidence

- repository scan output captured during documentation generation
- `git log --format='%h %ad %s' --date=short -20`
- `app.py`
- `pipeline.py`
- `modes.py`
- `adversal_client.py`
- `pyproject.toml`
- `README.md`
- `.github/workflows/ci.yml`
- `Dockerfile`
- `container-entrypoint.sh`
- `observability.py`
