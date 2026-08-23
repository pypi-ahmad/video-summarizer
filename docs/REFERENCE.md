# Reference

This page records the application's supported inputs, configuration, controls, storage,
and runtime contracts. For task instructions, use the [how-to guides](./HOW_TO.md).

## Runtime

| Item | Value |
| --- | --- |
| Python | 3.13 or newer; launch workflow pins 3.13.13 |
| Environment manager | uv with `.venv` in the project root |
| Application entry point | `uv run streamlit run app.py` |
| Canonical Windows entry point | `launch.cmd` |
| Video integration | `adversal-cli` over MCP stdio |
| Poll interval | 8 seconds |
| Job root | `runs/` |
| Vector store | Embedded persistent Qdrant at `runs/qdrant/` |

`ffmpeg` and `ffprobe` must be available on `PATH` for local video inspection by
Adversal.

### Hugging Face Space

| Item | Value |
| --- | --- |
| Space | `pypi-ahmad/video-summarizer` |
| Visibility | Private |
| SDK | Docker |
| Hardware | CPU Basic |
| Application port | `7860` |
| Persistent bucket | `pypi-ahmad/video-summarizer-data` |
| Bucket mount | `/data` |

Hugging Face currently requires a PRO subscription to create this Docker Space. CPU
Basic has no hourly hardware charge, but compute-Space creation is subscription-gated.
The private bucket exists; the Space itself is pending that subscription requirement.
The table describes the checked-in deployment target, not a currently running service.

The container startup script maps these persistent paths:

| Persistent path | Runtime path | Contents |
| --- | --- | --- |
| `/data/runs` | `/home/user/app/runs` | Jobs, uploads, notes, frames, Qdrant |
| `/data/adversal` | `/home/user/.adversal` | Adversal OAuth session and job registry |
| `/data/logs` | `/home/user/app/logs` | Rotating application logs |

Space secrets are exposed as environment variables at runtime. Secret values are never
part of the image or repository. Adversal authentication is completed interactively
from the private runtime-log URL and persisted in `/data/adversal`.

## Environment variables

| Variable | Required for | Default or behavior |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI chat and every Ask embedding operation | No default |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible proxy or gateway | OpenAI SDK default endpoint |
| `AGNES_API_KEY` | Agnes chat | No default |
| `GOOGLE_API_KEY` | Gemini chat | No default |
| `VIDEO_SUMMARIZER_LOG_LEVEL` | Application logging verbosity | `INFO` |

`python-dotenv` loads `.env` with `override=False`; existing process environment values
win. Adversal authentication is managed by `adversal-cli` through browser OAuth and has
no application environment variable.

## Chat and embedding models

| Sidebar label | Provider | Model | Reasoning setting |
| --- | --- | --- | --- |
| OpenAI - GPT-5.6 Luna | OpenAI | `gpt-5.6-luna` | `reasoning_effort="medium"` |
| Agnes AI - Agnes 2.5 Flash | Agnes AI | `agnes-2.5-flash` | Provider default |
| Google - Gemini 3.5 Flash Lite | Google | `gemini-3.5-flash-lite` | `thinking_level=MEDIUM` |
| Google - Gemini 3.7 Flash | Google | `gemini-3.7-flash` | `thinking_level=MEDIUM` |

The first option, GPT-5.6 Luna, is the UI default. Embeddings always use OpenAI
`text-embedding-3-small`; the sidebar selection affects chat generation only.

## Video inputs

| Input | Accepted values |
| --- | --- |
| Upload | `.mp4`, `.mov`, `.mkv`, `.webm` |
| URL | Public video URL accepted by Adversal |

Uploaded files are written beneath a UUID-bearing job directory. The application keeps
only the client filename's basename and verifies that the resolved destination remains
inside that directory.

## Analysis options

### Video type

| UI label | Adversal value |
| --- | --- |
| Generic | `generic` |
| Lesson / tutorial | `lesson` |
| Interview | `interview` |
| Meeting / webinar | `meeting` |

Default: `Generic`.

### Key visual frames

| UI label | Adversal value |
| --- | --- |
| Minimal | `minimal` |
| Selective | `selective` |
| Generous | `generous` |

Default: `Selective`.

## Job states

| State | Meaning |
| --- | --- |
| `RUNNING` | A request ID exists and the fragment continues polling |
| `COMPLETED` | Adversal reported completion; workspace views read `notes.md` and images |
| `FAILED` | Adversal or polling failed; the stored job includes an error when available |

Unknown Adversal status text remains in the polling state. A completed job records
`completed_at`. Selecting **Start over** after failure clears the active session pointer
but does not remove the persisted job or files.

## Workspace controls

| View | Behavior |
| --- | --- |
| Notes | Source Markdown, metrics, rendered referenced images, and three downloads |
| Key frames | Referenced safe local images, 12 per page in three columns |
| Ask | Active-video Qdrant retrieval, chat answer, sources, and full notes |
| Create | One of seven generated Markdown documents |

Only one video is active in a browser session. **Process another video** clears that
selection; it does not delete the job.

## Output contracts

### Source downloads

- **Markdown:** the completed job's configured notes filename, normally `notes.md`.
- **Native ZIP:** notes plus referenced images whose resolved paths remain inside the
  job directory.
- **OKF 0.2 ZIP:** `index.md`, `video.md`, numbered chapter files under `chapters/`, and
  referenced images under `assets/`.

The OKF index declares `okf_version: "0.2"`. Video and chapter concepts contain YAML
frontmatter, source metadata, draft status, and generation metadata.

### Generated documents

| Output | Download filename |
| --- | --- |
| Meeting/webinar summarizer | `meeting_summary.md` |
| Content triage | `content_triage.md` |
| Video to blog post | `blog_post.md` |
| Quiz and flashcards | `quiz_flashcards.md` |
| SOP/how-to guide | `sop_guide.md` |
| Interview insight pack | `interview_insights.md` |
| FAQ/help-center article | `faq_article.md` |

Each document is session-cached by `(request_id, selected_backend)`. Source notes at or
below 50,000 characters go directly to the final prompt. Longer notes are condensed in
batches of at most 30,000 characters until they fit the final generation step.

## Qdrant retrieval

| Item | Contract |
| --- | --- |
| Collection | `video_chunks_text_embedding_3_small_v1` |
| Distance | Cosine |
| Default result count | 5 |
| Required filter | Payload `request_id` equals the active job |
| Point identity | Deterministic UUID derived from request ID, notes hash, and chunk index |
| Idempotency | Matching request ID, notes hash, model, and chunk count skips re-indexing |

Chunks are built from Adversal chapter separators and headings with a target maximum of
1,500 characters. Payloads include source, heading, approximate timestamp, text, chunk
index, notes hash, and embedding model. Changed notes replace only that request's points.

## Local storage

```text
runs/
├── jobs.json
├── qdrant/
└── <timestamp>_<uuid>_<video-slug>/
    ├── <uploaded-video>       # uploads only
    ├── notes.md
    └── <Adversal images>
```

`jobs.json` is updated through a process-local lock and atomic temporary-file
replacement. Run data is unencrypted and has no automatic retention policy. Generated
documents and chat history remain in Streamlit session state rather than being written
to this tree.

## Logging

Application events are written to the visible terminal and to
`logs/video-summarizer.log`. The rotating file is limited to 5 MiB with three backups.
Supported levels are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`; an invalid
value falls back to `INFO` and emits a warning.

Logging setup is process-wide and idempotent across Streamlit reruns. Application logs
record only operational metadata. Known provider-key values and common token formats
are redacted, and handled failures omit exception messages that could contain remote or
user content. Streamlit writes its own server messages directly to the terminal; uv and
first-time launcher output are not copied into the application log file.

## Sidebar controls

- **LLM backend:** selects the chat provider.
- **Quota:** calls Adversal's remaining-quota tool.
- **Resume a previous job:** shows the ten newest saved jobs.
- **Danger zone:** closes Qdrant and removes the complete `runs/` directory after
  confirmation.

## Development commands

```bash
uv sync --locked --all-groups
uv run streamlit run app.py
uv run pytest -q
uv run ruff check .
uv run ty check
```

CI runs dependency sync, Ruff, ty, and pytest on Windows for pushes and pull requests
targeting `main`. The GitHub branch currently has no protection rule requiring that
check before merge.

## Operating limits

- Designed for one trusted user and one Streamlit server process, either locally or in
  a private Docker Space.
- Local OAuth opens on the server computer. In the private Space workflow, its temporary
  sign-in URL is read from runtime logs.
- Local Qdrant storage must not be shared by multiple app processes.
- No automatic retry, provider fallback, retention cleanup, or encryption is implemented.
- A private Hugging Face Docker deployment workflow is checked in, but the target Space
  is not yet created. Public or multi-user deployment is unsupported.
- Provider output and retrieval scores require human verification for important use.
