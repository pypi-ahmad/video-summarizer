# Codebase Concerns

## Core Sections (Required)

### 1) Top Risks (Prioritized)

| Severity | Concern | Evidence | Impact | Suggested action |
|----------|---------|----------|--------|------------------|
| Medium | User-controlled public URL reaches downloader | `app.py`, `adversal_client.py` | A remote deployment could expose server-side network access | Keep local-only boundary or add URL/network policy before remote deployment |
| Medium | Raw integration errors are displayed | `app.py` | Provider/tool details may reach UI | Add an error-redaction contract before shared deployment |
| Medium | Local Qdrant is single-process | `vector_store.py` | A second Streamlit process cannot safely share the embedded storage directory | Use Qdrant Server or Cloud before multi-process deployment |

### 2) Technical Debt

| Debt item | Why it exists | Where | Risk if ignored | Suggested fix |
|-----------|---------------|-------|-----------------|---------------|
| Partial exception handling | Adversal errors handled; file/LLM/Qdrant errors mostly left to Streamlit | `app.py`, `modes.py`, `vector_store.py` | Raw failure pages and poor recovery | Catch errors at owning UI boundary with provider/job context |
| Runtime storage has manual cleanup only | README documents local single-user scope | `runs/`, `app.py:78-84` | Disk growth | Retain manual cleanup while local-only; add policy only if observed need appears |

### 3) Security Concerns

| Risk | OWASP category | Evidence | Current mitigation | Gap |
|------|----------------|----------|--------------------|-----|
| User-controlled public URL reaches downloader | A10 SSRF | `app.py:94,112-119`, `adversal_client.py:57-84`, `uv.lock` | README limits app to local single-user use | No scheme/host/network validation in this layer; downstream behavior is unverified |
| Raw integration errors shown in UI | A09 Security Logging and Monitoring Failures / information exposure | `app.py:42-45,55-61,120-124,130-134` | Keys are not logged by application code | Error-redaction contract is absent |

### 4) Performance and Scaling Concerns

| Concern | Evidence | Current symptom | Scaling risk | Suggested improvement |
|---------|----------|-----------------|-------------|-----------------------|
| Fresh MCP subprocess for every 8-second poll | `adversal_client.py:38-54`, `pipeline.py:118-140` | Process startup per poll | CPU/process overhead across sessions | Keep current simple design for local use; measure before changing |
| Full JSON registry rewrite per status change | `pipeline.py` | O(number of jobs) write | Slower as history grows | Use a database only when measured scale requires it |
| Embedded Qdrant local mode | `vector_store.py` | Serialized in-process access | Not suitable for multiple app processes or large shared corpora | Move the same client API to Qdrant Server or Cloud when deployment scope changes |

### 5) Fragile/High-Churn Areas

The repository history is only eight commits on 2026-08-23. `README.md`, `.gitignore`, and `pipeline.py` have two recorded touches; most other files have one, so churn is too shallow to distinguish stable from fragile areas reliably.

| Area | Why fragile | Churn signal | Safe change strategy |
|------|-------------|-------------|----------------------|
| `app.py` + `pipeline.py` | Upload, persistence, polling and filesystem boundaries cross modules | `pipeline.py` has two touches; `app.py` one; low-confidence history | Keep focused path/persistence regressions passing |
| `modes.py` | Seven renderers plus reduction, chunking, and RAG chat | Largest application source | Test pure generation/chunk functions and rerun behavior separately |
| `adversal_client.py` | Async MCP task-group behavior has deliberate exception placement | One initial commit | Preserve outside-context exception translation; mock MCP responses |

### 6) `[ASK USER]` Questions

1. [ASK USER] Is local single-user execution a permanent product boundary, or should remote/shared Streamlit deployment be supported?

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
