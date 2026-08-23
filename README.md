<div align="center">

# Video Summarizer

Process one video into structured notes, visual frames, answers with sources, and content
you can reuse for learning or publishing.

[![CI](https://img.shields.io/github/actions/workflow/status/pypi-ahmad/video-summarizer/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/pypi-ahmad/video-summarizer/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.62-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![uv](https://img.shields.io/badge/managed%20with-uv-DE5FE9?style=flat-square)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](./LICENSE)

[Get started](#getting-started) · [Workflows](#what-you-can-create) ·
[Architecture](#architecture) · [Documentation](#documentation)

</div>

Video Summarizer is a Streamlit workspace for one user, built around
[Adversal](https://adversal.ai). Upload a video or provide a public URL once. Adversal
returns chaptered Markdown and selected screenshots. The app reuses those files for
semantic search, study material, operating documents, and publishable content without
running another analysis on the video.

> [!IMPORTANT]
> Adversal is a remote video-understanding service exposed through a local
> `adversal-cli` MCP subprocess. Video analysis happens on Adversal's infrastructure;
> this application stores the returned Markdown, frames, and request metadata locally.

## Why this project exists

Long videos are difficult inputs for language models. Full transcripts consume large
context windows, while transcript-only pipelines miss slides, diagrams, code, and other
useful scenes. This project keeps the expensive video pass separate from later reuse:

1. Adversal extracts structured chapters and representative visual frames.
2. The app keeps those artifacts as the source you can inspect.
3. Qdrant retrieves only relevant chapters for questions.
4. A selected LLM turns the notes into a document for the chosen task.

This gives each video one durable workspace instead of a separate pipeline for every
output.

## What you can create

| Workflow | Output |
| --- | --- |
| **Study notes** | Original chaptered Markdown with timestamps and referenced screenshots |
| **Meeting/webinar summary** | Two compact bullet sections: Decisions and Action Items, including owners when identified |
| **Searchable knowledge base** | Grounded answers from the five nearest video chunks, with chapter headings, timestamps, and scores |
| **Content triage** | Three to five summary bullets plus a watch-in-full, skim, or skip recommendation with a reason |
| **Blog post** | Title, opening hook, preserved chapter body and screenshots, and conclusion |
| **Quiz and flashcards** | Six multiple-choice questions, four short-answer questions, an explained answer key, and fifteen flashcards |
| **SOP/how-to guide** | Purpose, prerequisites, numbered procedure, cautions, verification, troubleshooting, and supported screenshots |
| **Interview insight pack** | Executive summary, themes, Q&A insights, paraphrased statements, and follow-up questions |
| **FAQ/help-center article** | Title, overview, organized FAQs, supported troubleshooting, related topics, and useful screenshots |

## Feature guide

### Video input and source analysis

The submission form accepts one source at a time:

| Feature | Behavior |
| --- | --- |
| **Local upload** | Accepts `.mp4`, `.mov`, `.mkv`, and `.webm`; stores the file inside a unique UUID-bearing job directory |
| **Public URL** | Passes the URL to Adversal's remote downloader; the app does not download it itself |
| **Analysis profile** | Generic, Lesson/tutorial, Interview, or Meeting/webinar changes how Adversal structures the source analysis |
| **Visual-frame density** | Minimal, Selective, or Generous controls how many representative frames Adversal returns |
| **Process-once model** | The selected profile and density apply once; all later views reuse the completed Markdown and images |
| **Non-blocking progress** | A Streamlit fragment polls Adversal every eight seconds while the rest of the application remains responsive |

Uploaded filenames are reduced to a safe basename and verified to remain inside their
job directory. URL access, authentication, and download duration still depend on the
source host and Adversal.

### Notes and visual evidence

The completed Adversal result appears directly before any LLM summary:

- **Notes** renders the original chaptered Markdown and its local image references.
- **Metrics** show section count, safe referenced-frame count, and analysis profile.
- **Key frames** presents screenshots in a three-column gallery, twelve per page, with
  captions taken from Markdown alt text or filenames.
- **Path containment** rejects Markdown images outside the owning job directory before
  they can be displayed or archived.
- **Missing-artifact handling** reports when Adversal marked a job complete but
  `notes.md` is absent, or when no safe referenced frames were returned.

### Searchable video knowledge base

The **Ask** view turns completed notes into persistent video RAG:

1. Notes are split along Adversal chapter separators and headings into chunks targeting
   at most 1,500 characters.
2. OpenAI `text-embedding-3-small` embeds each chunk.
3. Qdrant stores deterministic points under `runs/qdrant` with heading, approximate
   timestamp, text, notes hash, model, and active request ID.
4. Each question retrieves the five nearest chunks with a mandatory filter for the
   current video.
5. The selected chat model answers only from those excerpts and is instructed to say
   when they do not contain the answer.

Answers include an expandable **Sources** list with chapter headings, timestamps when
available, and cosine scores. **Full notes** remains available beside the chat so users
can verify model output. Indexing is idempotent for unchanged notes; changed notes
replace only that video's points.

> [!NOTE]
> Ask always requires `OPENAI_API_KEY` for embeddings. Agnes or Gemini may answer the
> final question, but they do not replace the fixed OpenAI embedding model.

### Generated documents

The **Create** view offers seven grounded transformations listed in
[What you can create](#what-you-can-create). Every generated document:

- uses the completed Adversal notes rather than the raw video;
- exposes the source notes in an expander for verification;
- renders supported local screenshots where the workflow preserves image references;
- downloads as a workflow-specific Markdown file; and
- is cached by `(request_id, selected_backend)` so Streamlit reruns do not repeat paid
  calls.

Notes up to 50,000 characters are sent to final generation directly. Longer notes are
condensed in batches of at most 30,000 characters until they fit. Blog, SOP, and FAQ
workflows explicitly preserve supported Markdown image references during reduction.
Changing the backend creates a separate cached version without processing the video
again.

### Downloads and agent-ready exports

The **Notes** view provides three source-artifact formats:

| Download | Contents | Best for |
| --- | --- | --- |
| **Markdown** | Adversal's completed `notes.md` | Reading, editing, or passing text to another tool |
| **Native bundle** | Source Markdown plus only its safely resolved referenced images | Moving the original Adversal result as one ZIP |
| **OKF 0.2 bundle** | `index.md`, `video.md`, chapter concepts, and image assets | Ingestion by agents or knowledge-catalog workflows |
| **Download all** | The three source downloads plus Create documents already cached for the active video and backend | Collecting available outputs without new LLM calls |

Every filename starts with a safe form of the original video stem, such as
`My_Lecture_notes.md`, `My_Lecture_blog_post.md`, or
`My_Lecture_all_downloads.zip`. Generated Create outputs retain their own **Download as
Markdown** action. Download all does not generate missing documents; it includes only
the versions already cached for the selected backend. Exports exclude the uploaded
video, Qdrant data, job history, and unreferenced files.

### Provider selection

The **LLM backend** sidebar control switches chat and document generation without code
changes:

- OpenAI `gpt-5.6-luna` with medium reasoning effort;
- Agnes AI `agnes-2.5-flash`;
- Google `gemini-3.5-flash-lite` with medium thinking; or
- Google `gemini-3.7-flash` with medium thinking.

Provider credentials come from environment variables or an optional gitignored
`.env`. Existing environment values win. There is no automatic provider fallback, so a
missing key or provider failure stays visible. The app does not silently change models.

### Authentication and quota

Adversal uses browser OAuth, not an application API key. When an Adversal tool returns
`AUTHENTICATION REQUIRED`, the app pauses and shows an
**Authenticate** action:

- locally, the browser flow opens on the computer running Streamlit;
- in a private Hugging Face Space, the app instructs the user to open the temporary URL
  printed in runtime logs; and
- the persisted Adversal directory lets later MCP subprocesses reuse the authenticated
  session.

The sidebar **Quota** panel calls Adversal's `check_remaining_quota` tool and displays
the current response without starting video processing.

### Resumable jobs and workspace controls

Each successful submission is stored in `runs/jobs.json` with its request ID, status,
source, profile, density, output directory, and timestamps. Writes use a process-local
lock and atomic replacement.

- **Resume a previous job** lists the ten newest records with source, status, and request
  prefix.
- **Process another video** leaves a completed workspace without deleting it.
- **Start over** leaves a failed workspace while retaining its persisted record.
- **Danger zone → Clear all runs** closes the embedded Qdrant client and permanently
  deletes uploads, jobs, notes, frames, and vectors after explicit confirmation.

Generated documents and Ask chat history stay in the session instead of being persisted.
Source artifacts, jobs, and vectors are durable.

### Logging and diagnostics

Application progress appears in the `launch.cmd` terminal and in
`logs/video-summarizer.log`. Logging is safe across Streamlit reruns, rotates at 5 MiB,
and retains three backups. `VIDEO_SUMMARIZER_LOG_LEVEL` selects `DEBUG`, `INFO`,
`WARNING`, `ERROR`, or `CRITICAL`.

Events contain operational metadata such as components, request IDs, models, counts,
durations, statuses, and error types. The application deliberately omits filenames,
URLs, prompts, transcripts, generated content, and exception messages; configured keys
and common token formats are redacted.

### Local and private hosted operation

- **Windows launcher:** installs uv when needed, pins Python 3.13.13, creates `.venv`,
  performs a locked sync, creates `.env` when missing, checks FFmpeg, and starts the app.
- **Manual uv workflow:** supports developers who manage the environment directly.
- **Docker image:** packages Python, uv, FFmpeg, the app, and `adversal-cli` for port
  7860.
- **Persistent Space storage:** maps `/data/runs`, `/data/adversal`, and `/data/logs` so
  application data and OAuth state survive container restarts.
- **Private single-user boundary:** public/shared hosting is intentionally unsupported
  because users would share identity, files, vectors, history, and deletion controls.

## Architecture

[![Video Summarizer system architecture](./docs/diagrams/system-architecture.svg)](./docs/diagrams/video-summarizer-architecture.html)

The Streamlit app launches a fresh `adversal-cli` MCP subprocess for each submission,
status, quota, or authentication call. Adversal's local registry keeps the remote request
state, so a new subprocess can poll an earlier `request_id`. Completed artifacts feed
four workspace views:

| View | Responsibility |
| --- | --- |
| **Notes** | Inspect source Markdown and download Markdown, native, or OKF bundles |
| **Key frames** | Browse only safe, locally referenced images |
| **Ask** | Index, retrieve, answer, and expose supporting chapters |
| **Create** | Generate one of seven cached Markdown documents |

More diagrams: [processing sequence](./docs/diagrams/video-processing-sequence.svg) ·
[job lifecycle](./docs/diagrams/job-lifecycle.svg) ·
[private Space deployment](./docs/diagrams/private-space-deployment.html)

## Getting started

### Prerequisites

- Windows 11 for the one-command launcher, or any environment capable of running the
  manual uv workflow
- `ffmpeg` and `ffprobe` on `PATH`
- An [Adversal](https://adversal.ai) account
- A provider key only for the LLM-backed features you plan to use

Notes, frames, and artifact downloads do not require an LLM key. **Ask always requires
`OPENAI_API_KEY`** because embeddings use OpenAI regardless of the selected chat model.

### Windows quick start

From the repository root:

```bat
launch.cmd
```

On its first run, the launcher:

1. installs uv for the current Windows user when missing;
2. installs Python 3.13.13;
3. creates `.venv` in the project root;
4. synchronizes the locked production and development dependencies;
5. creates `.env` from `.env.example` when needed; and
6. starts Streamlit with live logs in the same terminal.

Open the URL printed by Streamlit, normally <http://localhost:8501>. The first Adversal
operation may request browser authentication.

### Manual uv setup

```bash
uv python pin 3.13.13
uv sync --locked --all-groups
cp .env.example .env   # optional when keys already exist in the environment
uv run streamlit run app.py
```

On PowerShell, replace the copy command with:

```powershell
Copy-Item .env.example .env
```

## Configuration

The app reads credentials from the process environment. A local `.env` is an optional
fallback and never overrides existing environment variables.

| Variable | Used for | Required? |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI chat and all Ask embeddings | For OpenAI or Ask |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible gateway | No |
| `AGNES_API_KEY` | Agnes AI chat | For Agnes |
| `GOOGLE_API_KEY` | Gemini chat | For Gemini |
| `VIDEO_SUMMARIZER_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` | No; defaults to `INFO` |
| `VIDEO_SUMMARIZER_DATA_DIR` | Persistent container-data root | No; container defaults to `/data` |

Configured model choices:

| Provider | Model | Reasoning setting |
| --- | --- | --- |
| OpenAI | `gpt-5.6-luna` | medium reasoning effort |
| Agnes AI | `agnes-2.5-flash` | provider default |
| Google | `gemini-3.5-flash-lite` | medium thinking |
| Google | `gemini-3.7-flash` | medium thinking |

> [!CAUTION]
> Never commit `.env`, paste secret values into issues, or store provider keys as
> non-secret Hugging Face variables.

## Using the app

1. Select **Upload file** or **Public URL**.
2. Choose the video type: Generic, Lesson/tutorial, Interview, or Meeting/webinar.
3. Choose Minimal, Selective, or Generous key-frame extraction.
4. Select **Process video** and let the status panel poll Adversal.
5. Review **Notes** and **Key frames** before relying on generated material.
6. Use **Ask** for grounded questions or **Create** for a reusable document.

The sidebar can check Adversal quota, resume one of the ten newest persisted jobs, switch
the generation backend, or permanently clear all run data.

> [!TIP]
> If Adversal cannot download a long or protected URL, upload an authorized local file.
> Remote URL ingestion is limited by the source host and Adversal's download timeout.

## Data and persistence

```text
runs/
├── jobs.json
├── qdrant/
└── <timestamp>_<uuid>_<video-slug>/
    ├── <uploaded-video>
    ├── notes.md
    └── <referenced frames>
```

Generated documents and Ask chat history live in Streamlit session state. Jobs, source
artifacts, and vectors persist on disk. Run data is not encrypted and has no automatic
retention period; use **Danger zone → Clear all runs** when it is no longer needed.

## Private Hugging Face deployment

The repository includes a Docker image and entrypoint for a **private, single-user**
Hugging Face Space. A private bucket is mounted at `/data` so these survive restarts:

- `/data/runs`: uploaded videos, jobs, Markdown, frames, and Qdrant data;
- `/data/adversal`: Adversal OAuth state and local request registry; and
- `/data/logs`: rotating application logs.

Creating a Docker Space requires a paid Hugging Face plan. See the
[deployment procedure](./docs/HOW_TO.md#deploy-to-hugging-face-spaces) for the checked-in
target configuration.

> [!WARNING]
> Do not deploy this application publicly or for several users. Visitors would share one
> Adversal identity, job history, Qdrant index, uploaded data, and destructive controls.

## Technology stack

| Area | Technology |
| --- | --- |
| UI and session orchestration | Streamlit |
| Runtime and dependency management | Python 3.13.13 and uv |
| Video understanding | Adversal through MCP stdio |
| Retrieval | Qdrant Client with OpenAI embeddings |
| Text generation | OpenAI, Agnes AI, and Google Gemini |
| Media inspection | FFmpeg and ffprobe |
| Quality | Ruff, ty, pytest, and GitHub Actions |
| Hosted packaging | Docker and Hugging Face Spaces |

## Project structure

```text
video-summarizer/
├── app.py                    # Streamlit entry point and workspace routing
├── pipeline.py               # Job persistence, polling, and artifact rendering
├── adversal_client.py        # MCP adapter for adversal-cli
├── artifacts.py              # Safe frame discovery and ZIP/OKF exports
├── modes.py                  # Search and seven generated-document workflows
├── vector_store.py           # Persistent, active-video Qdrant retrieval
├── llm.py                    # Chat-provider dispatch and OpenAI embeddings
├── observability.py          # Terminal/file logging and secret redaction
├── launch.cmd                # Canonical Windows bootstrap and launcher
├── Dockerfile                # Private Hugging Face runtime image
├── container-entrypoint.sh   # Persistent /data path mapping
├── tests/                    # Regression and observability tests
└── docs/                     # User, operator, architecture, and codebase guides
```

## Development

Install the locked environment and run the same quality gates used by CI:

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ty check
uv run pytest -q
```

The current suite covers filesystem containment, export safety, provider contracts,
cache behavior, long-note reduction, Qdrant filtering and idempotency, concurrent job
persistence, and logging redaction/rotation. External Adversal and model services are
not called during tests.

For module ownership and safe change paths, read the
[developer/operator technical guide](./docs/TECHNICAL_GUIDE.md).

## Current limitations

- One video workspace is active per browser session.
- Generated documents and chat history stay in the session and are not persisted.
- Embedded Qdrant and `jobs.json` locking support one server process only.
- Public video URLs do not have an application-level host or private-network policy.
- There is no automatic provider fallback, retention cleanup, or application-level
  encryption.
- Model output and retrieval similarity require human verification for consequential
  use.

## Documentation

| Need | Start here |
| --- | --- |
| Complete a first run | [Tutorial](./docs/TUTORIAL.md) |
| Perform a specific task or troubleshoot | [How-to guides](./docs/HOW_TO.md) |
| Look up exact inputs, models, paths, and contracts | [Reference](./docs/REFERENCE.md) |
| Understand design decisions | [Explanation](./docs/EXPLANATION.md) |
| Develop or operate the system | [Technical guide](./docs/TECHNICAL_GUIDE.md) |
| Browse architecture diagrams | [Architecture index](./docs/ARCHITECTURE.md) |
| Onboard into the codebase | [Codebase documentation](./docs/codebase/ARCHITECTURE.md) |
| Browse every page offline | [Interactive HTML docs](./docs/site.html) |

The [interactive HTML docs](./docs/site.html) are a self-contained, hash-routed site
with a zero-to-mastery learning path. Rebuild it after Markdown changes with:

```bash
uv run python scripts/build_docs_site.py
```

Use `uv run python scripts/build_docs_site.py --check` to verify that the checked-in
HTML is synchronized with the tracked Markdown files.

## Getting help

Check [Recover from common failures](./docs/HOW_TO.md#recover-from-common-failures) and
the terminal or `logs/video-summarizer.log` first. If the problem is reproducible and
project-specific, [open a GitHub issue](https://github.com/pypi-ahmad/video-summarizer/issues)
with the failing operation, sanitized log metadata, and your platform details. Never
include API keys, video contents, transcripts, URLs, or OAuth tokens.

---

<p align="center">Built by Ahmad Mujtaba</p>
