# Video Summarizer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)](https://streamlit.io/)
[![uv](https://img.shields.io/badge/managed%20with-uv-DE5FE9)](https://docs.astral.sh/uv/)

Process a video once with [Adversal](https://adversal.ai), inspect its Markdown and key frames, search it with Qdrant-backed RAG, and create study or publishing outputs from one Streamlit workspace.

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
- [Documentation](#documentation)
- [Resources](#resources)

## Overview

[Adversal](https://adversal.ai) ships as a local [Model Context Protocol](https://modelcontextprotocol.io) server (`adversal-cli`) that turns a video - a local file or a public URL - into chaptered Markdown notes with extracted screenshots. This project exposes those source artifacts directly, indexes the Markdown in local Qdrant, and lets the same analysis serve nine different jobs without processing the video again:

| Mode | What you get |
| --- | --- |
| **Study notes** | Chaptered notes + screenshots, rendered as-is - Adversal's own output is already the deliverable |
| **Meeting/webinar summarizer** | A "Decisions / Action Items" digest above the full notes |
| **Searchable knowledge base** | Ask questions about the video; answers are grounded in retrieved chapters with citations |
| **Content triage** | A few bullets plus a watch/skim/skip recommendation, so you don't have to read the full notes to decide |
| **Video &rarr; blog post** | A title, intro hook, and conclusion added on top of the already blog-shaped chapter notes, downloadable as Markdown |
| **Quiz and flashcards** | 10 questions, a separate answer key, and 15 flashcards |
| **SOP/how-to guide** | A practical procedure with prerequisites, cautions, verification, troubleshooting, and relevant screenshots |
| **Interview insight pack** | Executive summary, themes, Q&A insights, paraphrased statements, and follow-up questions |
| **FAQ/help-center article** | A support-ready overview, FAQs, troubleshooting, related topics, and relevant screenshots |

> [!NOTE]
> Adversal is not a REST API - there's no HTTP endpoint or API key to configure. It's a local subprocess launched over stdio via MCP, authenticated once through a browser OAuth flow. See [How it works](#how-it-works).

## Features

- **Process once, reuse everywhere.** Choose the Adversal video type and frame density once, then move between Notes, Key frames, Ask, and Create views.
- **Agent-ready exports.** Download the original Markdown + referenced images or a chapter-level [OKF 0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) bundle.
- **Multi-provider LLM backend.** Switch between OpenAI (`gpt-5.6-luna`, medium reasoning effort), [Agnes AI](https://www.agnes-ai.com) (`agnes-2.5-flash`), and Google Gemini (`gemini-3.5-flash-lite` or `gemini-3.7-flash`, medium thinking effort) from the sidebar - no code changes.
- **Non-blocking async polling.** Adversal's video pipeline can take minutes; the app polls it with a `st.fragment` timer instead of freezing the whole page.
- **Resumable jobs.** Every submitted job is persisted to `runs/jobs.json`, so closing the tab (or restarting the app) doesn't lose track of a still-running job.
- **Persistent Qdrant RAG.** Chapter-aware chunks use OpenAI `text-embedding-3-small` and a disk-backed Qdrant collection under `runs/qdrant`; searches are filtered to the active video.

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
   one reusable workspace
      |-- Notes + key-frame gallery + native/OKF exports
      |-- Qdrant index -> active-video semantic search -> grounded answer
      `-- selected LLM -> meeting/blog/quiz/SOP/interview/FAQ output
      |
      v
   rendered in Streamlit
```

Each call to Adversal (`process_video`, `check_video_status`, `check_remaining_quota`, `authenticate`) spawns a fresh `adversal-cli` subprocess, makes one MCP tool call, and exits. This works because Adversal's local job registry persists on disk across restarts - a brand-new subprocess can still poll an old `request_id`. See [`adversal_client.py`](./adversal_client.py).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) - manages the Python interpreter, virtual environment, and dependencies
- `ffmpeg` / `ffprobe` on `PATH` - required by `adversal-cli` for local video inspection
- An [Adversal](https://adversal.ai) account (free tier: 100 minutes/month) - sign-in happens via a browser popup on first use, no API key needed
- A provider key for LLM-backed modes: [OpenAI](https://platform.openai.com/api-keys), [Agnes AI](https://www.agnes-ai.com), and/or [Google AI Studio](https://aistudio.google.com/apikey) for Gemini. Notes, key-frame viewing, and artifact downloads need no LLM key; Ask always needs OpenAI embeddings.

## Getting started

### Quick start (Windows)

```bat
launch.cmd
```

On first run this installs `uv` for the current Windows user when needed, installs Python 3.13.13 through uv, creates `.venv` in the project root, copies `.env.example` to `.env` if missing, installs the locked dependencies, and starts the app through the venv's Python. Re-running it is safe - it synchronizes the environment and launches.

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

1. Upload a video or paste a public URL, then choose its Adversal video type and key-frame density.
2. Click **Process video**. A status panel polls Adversal until the one reusable analysis completes.
3. Use **Notes** for Markdown and agent bundles, **Key frames** for the visual gallery, **Ask** for Qdrant-backed RAG, or **Create** for an LLM-generated output.
4. Use **Process another video** when you want a new source; previous jobs remain resumable.

The sidebar also has:

- **Quota** - check remaining Adversal minutes for the month
- **Resume a previous job** - reattach to one of the ten newest persisted jobs
- **Danger zone** - clear all local run data (`runs/`)

## Project structure

```
video-summarizer/
├── app.py               # Streamlit entry point: sidebar, mode dispatch
├── adversal_client.py   # MCP stdio wrapper around adversal-cli
├── pipeline.py           # Job persistence, async status polling, markdown+image rendering
├── artifacts.py           # Key-frame discovery and native/OKF ZIP exports
├── modes.py              # Qdrant chunking/chat and seven generated-output renderers
├── vector_store.py       # Persistent local Qdrant indexing and active-video search
├── llm.py                # Multi-provider chat/embeddings wrapper
├── launch.cmd             # One-file Windows bootstrap + launch
├── launch.bat             # Legacy compatibility launcher; launch.cmd is canonical
├── .env.example           # Required environment variables, documented
├── pyproject.toml         # uv-managed dependencies
├── tests/                 # Security, caching, and concurrent-persistence regressions
├── docs/
│   ├── ARCHITECTURE.md    # Technical reference: modules, data flow, design decisions
│   └── USAGE.md            # Step-by-step how-to guide for every mode
└── runs/                  # Gitignored jobs plus persistent qdrant/ vector storage
```

## Known limitations

- Adversal's OAuth sign-in opens a browser **on the machine running the Streamlit server**. Fine for local single-user use (the target for this project); not suited to a shared/remote deployment as-is.
- One video workspace is active per browser session; use the resume picker to switch to another persisted job.
- Local run data (`runs/`) is never auto-deleted; use the sidebar's "Clear all runs" when needed.
- Uploaded videos, generated notes, images, and indexes are stored unencrypted under `runs/`; avoid shared or remote deployment for sensitive content.
- Qdrant runs in local mode for this single-process desktop app. Move to Qdrant Server or Cloud before using multiple Streamlit server processes.

## Documentation

- [Tutorial: process your first video](./docs/TUTORIAL.md)
- [How-to guides](./docs/HOW_TO.md)
- [Reference](./docs/REFERENCE.md)
- [Explanation and design rationale](./docs/EXPLANATION.md)
- [Documentation chooser](./docs/USAGE.md)
- [Architecture chooser and diagrams](./docs/ARCHITECTURE.md)
- [Codebase onboarding](./docs/codebase/ARCHITECTURE.md)

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
