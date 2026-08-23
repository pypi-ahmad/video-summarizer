# How to use Video Summarizer

This guide covers local setup and the five workflows implemented by the current Streamlit app. For internals, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Index

- [Prerequisites](#prerequisites)
- [Start on Windows](#start-on-windows)
- [Start manually](#start-manually)
- [Configure LLM providers](#configure-llm-providers)
- [Process a video](#process-a-video)
- [Choose a workflow](#choose-a-workflow)
- [Use the sidebar tools](#use-the-sidebar-tools)
- [Local files and retention](#local-files-and-retention)
- [Troubleshooting](#troubleshooting)
- [Current operating limits](#current-operating-limits)

## Prerequisites

Install or provide:

- Windows 11 for the bundled `launch.bat` workflow, or another OS with `uv`
- `uv`
- `ffmpeg` and `ffprobe` on `PATH`
- an Adversal account; authentication opens in a local browser
- Python 3.13.13, installed automatically by `uv` when needed
- provider keys only for workflows that use an LLM

## Start on Windows

Run from the repository root:

```bat
launch.bat
```

The script:

1. verifies that `uv` exists;
2. creates `.venv` when missing;
3. copies `.env.example` to `.env` when missing;
4. runs `uv sync --all-groups`;
5. starts `uv run streamlit run app.py`.

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

## Start manually

```bash
uv python pin 3.13.13
uv sync --all-groups
cp .env.example .env
uv run streamlit run app.py
```

Skip `cp` when `.env` already exists or keys are configured as system environment variables. (On native PowerShell without Git Bash, use `Copy-Item .env.example .env` instead.)

## Configure LLM providers

Edit `.env` and fill only the providers you intend to use:

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=
AGNES_API_KEY=
GOOGLE_API_KEY=
```

| Variable | Used for |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI chat and all searchable-KB embeddings |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible gateway |
| `AGNES_API_KEY` | Agnes AI chat |
| `GOOGLE_API_KEY` | Gemini chat |

Study notes need no LLM key. Meeting summaries, content triage, and blog posts need the key for the selected backend. Searchable KB always needs `OPENAI_API_KEY` for embeddings and may need another key for the selected chat backend.

Never commit `.env`. It is already ignored by Git.

## Process a video

1. Choose a workflow under **Mode**.
2. Choose an **LLM backend**. Study notes ignore this choice.
3. Select **Upload file** or **Video URL**.
4. For uploads, choose an MP4, MOV, MKV, or WebM file. For URLs, enter a public video URL supported by Adversal's downloader.
5. Select **Process video**.
6. If the authentication banner appears, select **Authenticate** and finish Adversal sign-in in the browser opened on the server machine.
7. Leave the app running while it checks status every eight seconds.

Adversal writes Markdown notes and extracted images under `runs/<job>/`. The app renders the selected workflow after status becomes `COMPLETED`.

Video input is processed through Adversal. Do not submit material that you are not authorized to process.

## Choose a workflow

### Study notes

Use for lectures, lessons, and educational videos.

- Sends Adversal the `lesson` video type with `selective` image density.
- Displays chaptered notes and extracted images without another LLM call.

### Meeting/webinar summarizer

Use for recorded meetings and webinars.

- Sends the `meeting` video type with `minimal` images.
- Adds a Decisions and Action Items digest above the complete notes.
- Requires the selected chat-provider key.

The digest is cached for the current request and selected backend during the Streamlit session. Treat it as generated assistance, not an authoritative meeting record.

### Searchable knowledge base

Use when you want to ask questions about one completed video.

- Splits notes by Adversal chapter separators and headings.
- Creates OpenAI embeddings and stores them in `kb_index.npz` inside the job directory.
- Retrieves the five closest chunks using NumPy cosine similarity.
- Sends retrieved excerpts and your question to the selected chat backend.
- Shows cited chapter headings under **Sources**.

This mode searches one video, not every saved job. Answers remain model-generated; verify important claims against full notes or source video.

### Content triage

Use to decide whether a long video deserves full viewing.

- Sends the `generic` video type with `minimal` images.
- Produces short coverage bullets and a watch, skim, or skip recommendation.

This is editorial triage, not automated safety or policy moderation.

### Video to blog post

Use to turn completed notes into a Markdown draft.

- Sends the `lesson` video type with `generous` images.
- Adds a title, introduction, and conclusion while asking the model to retain chapters and image references.
- Caches one draft per request in the current Streamlit session.
- Provides **Download as Markdown**.

Changing the selected backend does not regenerate an already cached draft. Start a new session to generate another version.

## Use the sidebar tools

### Check quota

Open **Quota**, then select **Check remaining quota**. If authentication is required, complete the banner flow and retry.

### Resume a saved job

Open **Resume a previous job** and choose one of the ten newest entries. Jobs are restored from `runs/jobs.json` and assigned to their original mode.

### Start over after failure

Select **Start over** on a failed job. This clears the current session's job for that mode but does not delete its files or persisted history entry.

### Delete local run data

Open **Danger zone**, enable the confirmation checkbox, then select **Clear all runs**.

This permanently removes the local `runs/` directory, including uploaded videos, notes, images, indexes, and job history.

## Local files and retention

The app stores data under:

```text
runs/
├── jobs.json
└── <timestamp>_<uuid>_<video-slug>/
    ├── <uploaded-video>
    ├── notes.md
    ├── <extracted-images>
    └── kb_index.npz        # searchable-KB mode only
```

No automatic retention policy exists. Clear old runs manually when no longer needed.

> [!WARNING]
> Uploaded videos, notes, extracted images, chat-derived artifacts, and indexes are stored unencrypted. Keep the app and `runs/` directory local, restrict filesystem access, and clear sensitive runs when finished. Open only run directories created by this trusted local installation.

## Troubleshooting

### `uv is not installed`

Install `uv`, reopen the terminal, and run `launch.bat` again.

### `adversal-cli not found on PATH`

Synchronize dependencies:

```powershell
uv sync --all-groups
```

Then restart the app through `uv run streamlit run app.py`.

### Provider key is not set

Add the named variable to `.env` or the process environment, then restart Streamlit. Select a backend whose key is available.

### Authentication is required

Select **Authenticate** in the app banner. The browser opens on the computer running Streamlit, so this flow is intended for local use.

### Video processing fails

- Confirm `ffmpeg` and `ffprobe` are on `PATH`.
- Confirm the uploaded file is readable or the URL is public.
- Check remaining Adversal quota.
- Select **Start over** and submit again only after resolving the reported error.

Do not submit the same running video repeatedly. Resume and poll the existing request instead.

### A saved job cannot render

Confirm its job directory and `notes.md` still exist. Clearing `runs/` invalidates persisted output and history.

## Current operating limits

- Designed for local, single-user execution.
- Adversal OAuth opens on the Streamlit server machine.
- One selected job is held per mode in each Streamlit session; completed modes have no separate **New job** action.
- Saved jobs and output files are shared under one local `runs/` directory.
- Generated LLM output and KB indexes are cached only for the current Streamlit session.
- No automatic cleanup, remote deployment workflow, or automated test suite exists.
