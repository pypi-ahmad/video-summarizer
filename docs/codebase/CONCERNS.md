# Codebase Concerns

## Core Sections (Required)

### 1) Top Risks (Prioritized)

| Severity | Concern | Evidence | Impact | Suggested action |
|----------|---------|----------|--------|------------------|
| High | Uploaded filename is joined directly to job directory | `app.py:91-92` | Crafted filename can write outside intended job directory | Use basename plus resolved-parent containment check |
| High | Markdown image paths are resolved without containment | `pipeline.py:141-150` | Generated/untrusted Markdown can cause local files outside job output to be served | Render only regular files beneath resolved job directory |
| High | NumPy cache enables pickle loading | `modes.py:64-67` | A replaced/malicious cache can execute Python during load | Use `allow_pickle=False`; current saved string/float arrays support it |
| Medium | Meeting and triage call LLM on every rerun | `modes.py:92-120` | Repeated latency and paid API use from unrelated widget reruns | Cache by request ID and selected backend in session state |
| Medium | Shared JSON persistence is unlocked and non-atomic | `pipeline.py:42-52` | Concurrent sessions can lose updates or observe partial JSON | Serialize updates and replace a temporary file atomically |
| Medium | No automated tests or CI | `pyproject.toml`, scan, pytest output | Core parsing, persistence and trust-boundary regressions have no gate | Add focused unit tests first; add CI only if repository workflow needs it |

### 2) Technical Debt

| Debt item | Why it exists | Where | Risk if ignored | Suggested fix |
|-----------|---------------|-------|-----------------|---------------|
| Second-resolution job directories | Simple local prototype naming | `pipeline.py:59-62` | Same-slug concurrent submissions can share output | Add UUID suffix |
| Partial exception handling | Adversal errors handled; file/LLM/NumPy errors left to Streamlit | `app.py`, `modes.py`, `pipeline.py` | Raw failure pages and poor recovery | Catch errors at owning UI boundary with provider/job context |
| Runtime storage has manual cleanup only | README documents local single-user scope | `runs/`, `app.py:65-71` | Disk growth | Retain manual cleanup while local-only; add policy only if observed need appears |
| Heavy direct dependencies | Torch/torchvision are declared but not imported by app modules | `pyproject.toml`, tracked Python files | Large CUDA install and slower setup | Confirm Adversal runtime need; remove only if dependency ownership proves them unnecessary |

### 3) Security Concerns

| Risk | OWASP category | Evidence | Current mitigation | Gap |
|------|----------------|----------|--------------------|-----|
| Upload path traversal | A01 Broken Access Control | `app.py:91-92` | File extension filter and slugged directory name | Uploaded filename itself is not normalized/contained |
| Local-file disclosure through images | A01 Broken Access Control | `pipeline.py:148-150` | Existence check | No base-directory or regular-file check |
| Pickle deserialization | A08 Software and Data Integrity Failures | `modes.py:65` | Cache stored under local run directory | `allow_pickle=True` is unnecessary and unsafe |
| User-controlled public URL reaches downloader | A10 SSRF | `app.py:81`, `adversal_client.py:99-105`, `uv.lock` | README limits app to local single-user use | No scheme/host/network validation in this layer; downstream behavior is unverified |
| Raw integration errors shown in UI | A09 Security Logging and Monitoring Failures / information exposure | `app.py:31-32`, `app.py:47-48`, `app.py:105-106` | Keys are not logged by application code | Error-redaction contract is absent |

### 4) Performance and Scaling Concerns

| Concern | Evidence | Current symptom | Scaling risk | Suggested improvement |
|---------|----------|-----------------|-------------|-----------------------|
| Repeated LLM digest generation | `modes.py:92-120` | Every rerun repeats work | API cost and latency multiply | Session-cache digest per job/backend |
| Fresh MCP subprocess for every 8-second poll | `adversal_client.py:38-54`, `pipeline.py:112-134` | Process startup per poll | CPU/process overhead across sessions | Keep current simple design for local use; measure before changing |
| Full JSON registry rewrite per status change | `pipeline.py:42-52` | O(number of jobs) write | Slower and race-prone as history grows | Atomic store or small database only when scale requires it |
| In-memory exact cosine scan | `modes.py:73-80` | O(chunks × dimensions) per query | Slow only for much larger corpora | Keep NumPy scan for documented few-hundred-chunk target |

### 5) Fragile/High-Churn Areas

All tracked files were introduced in five commits on 2026-08-23, so the 90-day history has one touch per file and cannot distinguish stable from fragile areas.

| Area | Why fragile | Churn signal | Safe change strategy |
|------|-------------|-------------|----------------------|
| `app.py` + `pipeline.py` | Upload, persistence, polling and filesystem boundaries cross modules | One initial commit each; low-confidence history | Add path/status regression tests before edits |
| `modes.py` | Five renderers plus retrieval and cache logic in one module | One initial commit; largest application source | Test pure chunk/search functions and rerun behavior separately |
| `adversal_client.py` | Async MCP task-group behavior has deliberate exception placement | One initial commit | Preserve outside-context exception translation; mock MCP responses |

### 6) `[ASK USER]` Questions

1. [ASK USER] Is local single-user execution a permanent product boundary, or should remote/shared Streamlit deployment be supported?
2. [ASK USER] Should meeting and triage outputs remain stable per job/backend, or is regeneration on every rerun intentional?
3. [ASK USER] Is the absence of tests and CI deliberate for this prototype, or should a minimal regression gate be added?
4. [ASK USER] Are direct Torch and torchvision dependencies required by an intended local workflow, or only transitively by Adversal?

### 7) Evidence

- `docs/codebase/.codebase-scan.txt` (scan-time metrics/history; removed after validation)
- `git log --format='%h %ad %s' --date=short -20`
- `app.py`
- `pipeline.py`
- `modes.py`
- `adversal_client.py`
- `pyproject.toml`
- `README.md`

