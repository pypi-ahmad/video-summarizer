# Video Summarizer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)](https://streamlit.io/)
[![uv](https://img.shields.io/badge/managed%20with-uv-DE5FE9)](https://docs.astral.sh/uv/)

Turn any video into study notes, a meeting digest, a searchable knowledge base, a triage summary, or a blog post - one Streamlit app, five modes, built on [Adversal](https://adversal.ai) for video understanding and a swappable multi-provider LLM layer for everything Adversal doesn't do on its own.

**Repository:** https://github.com/pypi-ahmad/video-summarizer

## Index

- [Overview](#overview)
- [Features](#features)
- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)
- [Resources](#resources)

## Overview

[Adversal](https://adversal.ai) ships as a local [Model Context Protocol](https://modelcontextprotocol.io) server (`adversal-cli`) that turns a video - a local file or a public URL - into chaptered Markdown notes with extracted screenshots. It's genuinely good output: chapters, prose, images tied to timestamps. But it only gives you one shape of output. This project wraps it in a Streamlit UI and adds a thin, mode-specific layer on top so the same underlying video analysis can serve five different jobs:

| Mode | What you get |
| --- | --- |
| **Study notes** | Chaptered notes + screenshots, rendered as-is - Adversal's own output is already the deliverable |
| **Meeting/webinar summarizer** | A "Decisions / Action Items" digest above the full notes |
| **Searchable knowledge base** | Ask questions about the video; answers are grounded in retrieved chapters with citations |
| **Content triage** | A few bullets plus a watch/skim/skip recommendation, so you don't have to read the full notes to decide |
| **Video &rarr; blog post** | A title, intro hook, and conclusion added on top of the already blog-shaped chapter notes, downloadable as Markdown |

> [!NOTE]
> Adversal is not a REST API - there's no HTTP endpoint or API key to configure. It's a local subprocess launched over stdio via MCP, authenticated once through a browser OAuth flow. See [How it works](#how-it-works).

## Features

- **Five modes, one pipeline.** Every mode shares the same submit &rarr; poll &rarr; read-results flow; only the `type`/`images` request and the post-processing step differ.
- **Multi-provider LLM backend.** Switch between OpenAI (`gpt-5.6-luna`, medium reasoning effort), [Agnes AI](https://www.agnes-ai.com) (`agnes-2.5-flash`), and Google Gemini (`gemini-3.5-flash-lite` or `gemini-3.7-flash`, medium thinking effort) from the sidebar - no code changes.
- **Non-blocking async polling.** Adversal's video pipeline can take minutes; the app polls it with a `st.fragment` timer instead of freezing the whole page.
- **Resumable jobs.** Every submitted job is persisted to `runs/jobs.json`, so closing the tab (or restarting the app) doesn't lose track of a still-running job.
- **No vector database.** The knowledge-base mode chunks notes on Adversal's own chapter headings and does plain NumPy cosine-similarity search - no extra infrastructure for a few hundred chunks.

## How it works

```
                 upload / URL
                      |
                      v
   Streamlit  --(MCP stdio)-->  adversal-cli  --(async)-->  Adversal backend
   (app.py)                    (subprocess per call)
      |                                                          |
      | poll check_video_status (st.fragment, every 8s)          |
      |<---------------------------------------------------------
      v
   notes.md + images written to runs/<job>/
      |
      v
   mode-specific post-processing (none, or one LLM call, or embed+search)
      |
      v
   rendered in Streamlit
```

Each call to Adversal (`process_video`, `check_video_status`, `check_remaining_quota`, `authenticate`) spawns a fresh `adversal-cli` subprocess, makes one MCP tool call, and exits. This works because Adversal's local job registry persists on disk across restarts - a brand-new subprocess can still poll an old `request_id`. See [`adversal_client.py`](./adversal_client.py).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) - manages the Python interpreter, virtual environment, and dependencies
- `ffmpeg` / `ffprobe` on `PATH` - required by `adversal-cli` for local video inspection
- An [Adversal](https://adversal.ai) account (free tier: 100 minutes/month) - sign-in happens via a browser popup on first use, no API key needed
- At least one LLM provider key: [OpenAI](https://platform.openai.com/api-keys), [Agnes AI](https://www.agnes-ai.com), and/or [Google AI Studio](https://aistudio.google.com/apikey) for Gemini

## Getting started

### Quick start (Windows)

```bat
launch.bat
```

On first run this creates the `.venv` (pinned to Python 3.13.13), copies `.env.example` to `.env` if missing, installs dependencies with `uv sync`, and starts the app. Re-running it is safe - it just syncs and launches.

### Manual setup

```bash
uv python pin 3.13.13
uv venv
uv sync --all-groups
cp .env.example .env   # fill in your keys
uv run streamlit run app.py
```

The first video you process will prompt an Adversal sign-in in your browser - this only happens once per machine.

## Configuration

Copy [`.env.example`](./.env.example) to `.env` and fill in whichever providers you plan to use. Keys already present as system environment variables are used as-is; `.env` is only a fallback (`python-dotenv` never overrides an already-set variable).

| Variable | Required for | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI backend, and embeddings for the knowledge-base mode | Embeddings always use OpenAI regardless of the selected chat backend |
| `OPENAI_BASE_URL` | Optional | Only set this to route through a proxy/gateway instead of the default OpenAI endpoint |
| `AGNES_API_KEY` | Agnes AI backend | [Agnes AI console](https://www.agnes-ai.com) |
| `GOOGLE_API_KEY` | Gemini backends | [Google AI Studio](https://aistudio.google.com/apikey) |

## Usage

1. Pick a **mode** and an **LLM backend** in the sidebar.
2. Provide a video: upload a file, or paste a public URL (downloaded via the bundled `yt-dlp`).
3. Click **Process video**. A status panel polls Adversal until the job completes.
4. Read the result. Knowledge-base mode adds a chat box for follow-up questions; blog-post mode adds a Markdown download button.

The sidebar also has:

- **Quota** - check remaining Adversal minutes for the month
- **Resume a previous job** - reattach to a job from an earlier session
- **Danger zone** - clear all local run data (`runs/`)

## Project structure

```
video-summarizer/
├── app.py               # Streamlit entry point: sidebar, mode dispatch
├── adversal_client.py   # MCP stdio wrapper around adversal-cli
├── pipeline.py           # Job persistence, async status polling, markdown+image rendering
├── modes.py              # The five mode renderers, plus KB chunking/retrieval
├── llm.py                # Multi-provider chat/embeddings wrapper
├── launch.bat             # One-file first-run setup + launch
├── .env.example           # Required environment variables, documented
├── pyproject.toml         # uv-managed dependencies
└── runs/                  # Per-job output (gitignored): notes.md, images, jobs.json
```

## Known limitations

- Adversal's OAuth sign-in opens a browser **on the machine running the Streamlit server**. Fine for local single-user use (the target for this project); not suited to a shared/remote deployment as-is.
- One in-flight job per mode - starting a second job in the same mode overwrites the first.
- Local run data (`runs/`) is never auto-deleted; use the sidebar's "Clear all runs" when needed.

## Resources

References for the APIs and tools this project builds on:

- [Adversal - MCP documentation](https://adversal.ai/documentation/mcp)
- [Model Context Protocol - Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OpenAI - Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning) (`reasoning_effort`)
- [Agnes AI - API overview](https://www.agnes-ai.com/en/docs/overview)
- [Agnes AI - Agnes 2.5 Flash](https://www.agnes-ai.com/en/docs/agnes-25-flash)
- [Google Gemini - Thinking / reasoning levels](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking)
- [google-genai - Python SDK](https://pypi.org/project/google-genai/)
- [Streamlit documentation](https://docs.streamlit.io/)
- [uv documentation](https://docs.astral.sh/uv/)
- [Ruff documentation](https://docs.astral.sh/ruff/)
- [ty documentation](https://docs.astral.sh/ty/)

---

<p align="center">Made with ❤️ by Ahmad Mujtaba</p>
