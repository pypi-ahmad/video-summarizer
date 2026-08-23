# Tutorial: process your first video

Follow this tutorial from a fresh checkout to a completed video workspace. You will
process one video with Adversal, inspect its notes and frames, ask a question with source
excerpts, and create a document you can download.

## What you will build

By the end, one source video will provide:

- chaptered Markdown notes and referenced screenshots;
- a persistent Qdrant search index;
- a grounded answer with chapter sources; and
- an LLM-generated document such as a quiz or meeting summary.

The app processes the video once. Each later view reuses that Adversal result.

This walkthrough keeps the default analysis settings. Use a short, non-sensitive video
whose contents you can verify.

## Before you begin

You need:

- Windows 11 for the guided `launch.cmd` path;
- `ffmpeg` and `ffprobe` available on `PATH`;
- an Adversal account; and
- an `OPENAI_API_KEY` for the Ask exercise and default OpenAI backend.

Agnes AI and Gemini are optional alternatives for generated text. They do not replace
the OpenAI embeddings used by Ask.

Before continuing, verify the media tools in PowerShell:

```powershell
ffmpeg -version
ffprobe -version
```

Each command should print version information.

## 1. Start the application

From the repository root, run:

```bat
launch.cmd
```

On its first run, the launcher installs `uv` when necessary, installs Python 3.13.13,
creates `.venv`, synchronizes the locked dependencies, and creates `.env` from
`.env.example` when missing.

Open `.env` and add your key:

```dotenv
OPENAI_API_KEY=your-key-here
```

Never commit `.env`. Restart `launch.cmd` after changing it, then open the Streamlit
address shown in the terminal, normally `http://localhost:8501`.

**Checkpoint:** the page title is **Video Summarizer**, and the sidebar contains
**LLM backend**, **Quota**, and **Danger zone**.

## 2. Submit a video

1. Keep **OpenAI - GPT-5.6 Luna** selected in the sidebar.
2. Select **Upload file**.
3. Choose an `.mp4`, `.mov`, `.mkv`, or `.webm` video that you are authorized to
   process.
4. Keep **Generic** as the video type and **Selective** as the key-frame density.
5. Leave **Advanced processing controls** empty for this first full-video run.
6. Select **Process video**.

If Adversal requests authentication, select **Authenticate** and complete the browser
flow on the same computer that runs Streamlit. The app resumes after the sign-in flow.

The status panel checks Adversal every eight seconds through one persistent local MCP
session. You can close the browser and resume the saved request later from the sidebar
because its job record is stored in `runs/jobs.json`.

If authentication fails, the banner remains visible and shows Adversal's message. Start
the browser flow again; the app does not treat a failed sign-in as success.

**Checkpoint:** while analysis is active, the page shows `RUNNING` and a last-checked
time. When it finishes, the workspace opens on **Notes** and shows the Adversal request
ID, analysis profile, and frame density.

## 3. Inspect the source artifacts

When processing completes, the **Notes** view opens.

1. Review the section and key-frame counts.
2. Scroll through the chaptered Markdown.
3. Open **Key frames** and inspect the extracted screenshots.
4. Return to **Notes** and download the Markdown or one of the ZIP bundles.
5. Select **Download all** beside the workspace title to collect all three source
   downloads in one ZIP.

The native bundle contains `notes.md` and only the local images referenced by those
notes. The OKF 0.2 bundle reorganizes the same material into a video concept, chapter
concepts, and assets suitable for agent ingestion.

**Checkpoint:** the section and key-frame metrics match the visible source artifacts.
If Key frames is empty, continue with the notes; the selected source may not contain
useful visual changes.

## 4. Ask a grounded question

1. Open **Ask**.
2. Wait while the app builds the searchable index.
3. Ask a question whose answer appears in the video, such as:

   ```text
   What are the three main recommendations in this video?
   ```

4. Expand **Sources** under the answer.

The app embeds chapter-aware chunks with OpenAI `text-embedding-3-small`, stores them
under `runs/qdrant`, retrieves the five nearest chunks for the active request, and asks
the selected chat model to answer only from those excerpts. A similarity score is not
proof, so verify important answers against the notes or original video.

**Checkpoint:** the answer includes chapter-based grounding, and **Sources** lists up
to five retrieved headings with timestamps when available and similarity scores.

## 5. Create a reusable document

1. Open **Create**.
2. Select **Quiz and flashcards** or another output.
3. Review the generated Markdown and its source-notes expander.
4. Select **Download as Markdown**.
5. Select **Download all**. The ZIP now includes this cached document without another
   model call.

The app caches the generated document for this browser session by request ID and
selected backend. Switching backends creates another version, but does not process the
video again. Download filenames use the safe original video stem followed by the output
type.

For the quiz workflow, confirm that the document contains ten questions, a separate
answer key, and fifteen flashcards. Those counts are part of the workflow contract.

## 6. Finish safely

Select **Process another video** to leave the current workspace without deleting its
files. To remove all local videos, notes, history, and Qdrant data, use **Danger zone**
in the sidebar and confirm **Clear all runs**.

For focused operational tasks, continue with [How-to guides](./HOW_TO.md). For exact
settings and contracts, see the [Reference](./REFERENCE.md). Developers and operators
can continue with the [technical guide](./TECHNICAL_GUIDE.md).
