# How-to guides

Use these recipes when you already know the application and need to complete a
specific task. For a guided first run, start with the [tutorial](./TUTORIAL.md).

## Choose a recipe

| Goal | Section |
| --- | --- |
| Launch locally | [Start on Windows](#start-on-windows) or [Start manually](#start-manually) |
| Sign in to Adversal | [Authenticate Adversal locally](#authenticate-adversal-locally) |
| Configure generation | [Configure an LLM provider](#configure-an-llm-provider) |
| Analyze a source | [Process an uploaded video](#process-an-uploaded-video) or [Process a public video URL](#process-a-public-video-url) |
| Inspect or export evidence | [Browse key frames](#browse-key-frames) or [Download agent-ready artifacts](#download-agent-ready-artifacts) |
| Ask questions or create content | [Search the active video](#search-the-active-video) or [Create a derived document](#create-a-derived-document) |
| Recover work or diagnose a problem | [Resume a saved job](#resume-a-saved-job) or [Recover from common failures](#recover-from-common-failures) |

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

## Authenticate Adversal locally

Authentication is requested only when an Adversal operation needs it.

1. Start the app and submit a video or open **Quota** and select
   **Check remaining quota**.
2. When the authentication banner appears, select **Authenticate**.
3. Complete the browser sign-in on the same computer that runs Streamlit.
4. Return to the app. It clears the authentication state and reruns automatically.

Adversal owns this OAuth session; there is no `ADVERSAL_API_KEY` environment variable.
If authentication fails, keep the launch terminal open and use the newest sign-in flow.

## Deploy to Hugging Face Spaces

The supported hosted configuration is a private Docker Space with a private bucket.
Public or protected deployment is unsafe because all visitors would share the same
Adversal account, run history, uploaded files, Qdrant index, and deletion control.
The Hugging Face account must have a PRO subscription before it can create a Docker
Space, even when the selected hardware is CPU Basic.

The deployment target is:

- Space: `pypi-ahmad/video-summarizer`
- Bucket: `pypi-ahmad/video-summarizer-data`
- Bucket mount: `/data`
- Streamlit port: `7860`

The private bucket exists. The Space is not yet created because the target Hugging Face
account does not currently meet the PRO requirement. The repository's Docker files are
ready to publish after that requirement is met.

The container maps `/data/runs`, `/data/adversal`, and `/data/logs` to the paths used by
the application and `adversal-cli`. Hugging Face restarts therefore preserve jobs,
uploads, notes, frames, vectors, Adversal login state, and rotating logs.

Configure provider credentials yourself in **Space Settings > Secrets**. Use only the
names below; do not commit or upload a `.env` file:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
AGNES_API_KEY
GOOGLE_API_KEY
```

`OPENAI_BASE_URL` is optional. The other keys are required only for their corresponding
provider, except Ask/search embeddings always require `OPENAI_API_KEY`.

After the Space is created, authenticate Adversal for the first time:

1. Open the private Space and its **Runtime logs** in separate tabs.
2. Trigger an Adversal operation, such as **Check remaining quota**.
3. Select **Authenticate** in the app.
4. Open the temporary Adversal sign-in URL printed in the runtime logs.
5. Complete sign-in and return to the app.

The login session is stored in the private bucket, not in Git or a Space environment
variable. After deployment, inspect hosted logs from an authenticated terminal with:

```powershell
hf spaces logs pypi-ahmad/video-summarizer --tail 100
hf spaces logs pypi-ahmad/video-summarizer --build --tail 100
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

### Switch the generation backend

Use **LLM backend** in the sidebar before asking a question or creating a document.
Changing the backend does not reprocess the video or rebuild compatible embeddings.
Create caches a distinct document for each `(request_id, backend)` pair, while Ask uses
the selected backend for the next answer.

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

## Browse key frames

1. Open **Key frames** in a completed workspace.
2. Review the three-column gallery and image captions.
3. When the analysis contains more than 12 referenced images, use **Frame page** to move
   through pages.

The gallery includes only files referenced by the Markdown that resolve inside the job
directory. If no safe referenced images exist, the app reports that the analysis did
not return key frames.

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

## Leave, restart, or delete a workspace

- **Process another video** leaves the completed workspace and returns to submission;
  it does not delete files.
- **Start over** leaves a failed job; the failed record and directory remain persisted.
- **Resume a previous job** restores a persisted job as the active workspace.
- **Clear all runs** permanently removes every job, upload, artifact, and Qdrant vector.

## Recover from common failures

### Inspect live and saved logs

Keep the `launch.cmd` terminal open to see Streamlit messages and application progress.
The same application events are retained in `logs/video-summarizer.log`; older files
rotate to `.1`, `.2`, and `.3` when the active file reaches 5 MiB.

For additional stack-frame locations and cache details, set:

```dotenv
VIDEO_SUMMARIZER_LOG_LEVEL=DEBUG
```

Restart the app after changing the level. Logs contain operation metadata, IDs, models,
counts, timing, statuses, and error types. They intentionally omit filenames, URLs,
prompts, transcripts, generated content, exception messages, and secret values.

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

### A public URL download times out

Adversal downloads URL sources on its remote infrastructure. A long, protected, or slow
source may exceed its download window before a request ID is created. Confirm that the
URL is publicly reachable; if it still fails, download the video through an authorized
route and use **Upload file** instead.

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
