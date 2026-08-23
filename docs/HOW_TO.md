# How-to guides

Use these recipes when you already know the application and need to complete a
specific task. For a guided first run, start with the [tutorial](./TUTORIAL.md).

## Start on Windows

Run the canonical launcher from the repository root:

```bat
launch.cmd
```

It installs the required uv-managed Python, creates `.venv`, synchronizes the locked
environment, creates `.env` when needed, warns about missing FFmpeg tools, and starts
Streamlit. The older `launch.bat` is retained for compatibility but does not provide
the same pinned and locked setup guarantees.

## Start manually

Use this route on another operating system or when managing uv yourself:

```bash
uv python pin 3.13.13
uv sync --locked --all-groups
uv run streamlit run app.py
```

Copy `.env.example` to `.env` only when the keys are not already available as process
environment variables. On PowerShell:

```powershell
Copy-Item .env.example .env
```

## Configure an LLM provider

Set only the providers you intend to use:

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=
AGNES_API_KEY=
GOOGLE_API_KEY=
```

Environment variables take precedence because `.env` is loaded without overriding
them. Restart Streamlit after changing the environment.

- Use `OPENAI_API_KEY` for GPT-5.6 Luna and for all Ask embeddings.
- Set `OPENAI_BASE_URL` only for an OpenAI-compatible gateway or proxy.
- Use `AGNES_API_KEY` for Agnes 2.5 Flash.
- Use `GOOGLE_API_KEY` for Gemini 3.5 Flash Lite or Gemini 3.7 Flash.

Choose the chat backend from the sidebar. Ask still requires OpenAI embeddings even
when Agnes or Gemini answers the final question.

## Process an uploaded video

1. Select **Upload file**.
2. Choose an `.mp4`, `.mov`, `.mkv`, or `.webm` file.
3. Select the video type and frame density.
4. Select **Process video**.
5. Complete Adversal authentication if prompted.

The uploaded filename is sanitized before the file is written inside its generated
job directory.

## Process a public video URL

1. Select **Video URL**.
2. Paste a public URL supported by Adversal's downloader.
3. Select the analysis profile and frame density.
4. Select **Process video**.

Authentication, access restrictions, and URL support are source-dependent. The app
does not download the URL itself; it passes the URL to Adversal.

## Choose an analysis profile

- Use **Generic** when no specialized profile applies.
- Use **Lesson / tutorial** for instructional material.
- Use **Interview** for conversations and recorded Q&A.
- Use **Meeting / webinar** for collaborative sessions and presentations.

Choose **Minimal**, **Selective**, or **Generous** key frames according to how much
visual context the resulting notes need. These choices affect the one source analysis,
not which documents you can create afterward.

## Download agent-ready artifacts

Open **Notes**, then choose:

- **Download Markdown** for Adversal's source `notes.md`;
- **Download native bundle** for the Markdown plus its safely resolved referenced
  images; or
- **Download OKF 0.2 bundle** for `index.md`, `video.md`, chapter concepts, and assets.

The bundles exclude the uploaded video, Qdrant data, job history, and unreferenced
files.

## Search the active video

1. Open **Ask** and wait for indexing.
2. Enter a question about the active video.
3. Expand **Sources** to inspect headings, approximate timestamps, and scores.
4. Open **Full notes** when the retrieved evidence is insufficient.

Indexing is idempotent for an unchanged request and notes hash. Search always applies
the active request ID as a Qdrant payload filter.

## Create a derived document

Open **Create** and choose one of these outputs:

- Meeting/webinar summarizer
- Content triage
- Video to blog post
- Quiz and flashcards
- SOP/how-to guide
- Interview insight pack
- FAQ/help-center article

Each output is generated from the completed notes, displayed with access to the source
notes, and downloadable as Markdown. Notes longer than 50,000 characters are first
condensed in bounded batches. Image-oriented outputs preserve supported Markdown image
references.

## Resume a saved job

Open **Resume a previous job** in the sidebar and select one of the ten newest entries.
The label includes the source name, persisted status, and request-ID prefix.

Resuming restores the job as the active workspace. Generated documents and chat
history do not return after a Streamlit session ends, but source files and Qdrant
vectors remain on disk.

## Recover from common failures

### Adversal requests authentication

Select **Authenticate** in the banner and complete the browser flow on the Streamlit
server computer. Retry the operation if it does not resume automatically.

### A provider key is missing

Set the variable named in the error, restart Streamlit, and choose the matching backend.
Ask requires `OPENAI_API_KEY` regardless of the selected chat provider.

### Local video processing fails

Confirm both tools are available:

```powershell
ffmpeg -version
ffprobe -version
```

Then synchronize dependencies and restart:

```powershell
uv sync --locked --all-groups
uv run streamlit run app.py
```

### A completed job cannot render

Confirm the job directory and its `notes.md` still exist. Clearing `runs/` invalidates
all saved job records and artifacts together.

## Delete all local run data

1. Open **Danger zone**.
2. Enable **I understand this deletes all local run data**.
3. Select **Clear all runs**.

This closes the local Qdrant client and permanently removes `runs/`, including uploaded
videos, notes, images, vectors, and `jobs.json`. This operation cannot be undone from
the app.
