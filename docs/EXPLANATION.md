# Explanation: why the application is designed this way

Video Summarizer separates video analysis from the work that follows. This page explains
the design decisions behind that boundary and the tradeoffs they create.

## Process once, use many ways

Adversal performs the costly multimodal work: it reads the video's audio and visual
tracks, creates structured Markdown, and selects important frames. Meeting summaries,
quizzes, FAQs, and other outputs are different presentations of that same evidence; they
do not need another pass over the raw video.

The app therefore has one active video workspace instead of a separate processing job
for every output. Video type and frame density belong to source analysis. Notes, Key
frames, Ask, and Create reuse that result. This avoids duplicate processing and keeps
all derived outputs tied to one source artifact.

## Why Adversal sits behind MCP

The application does not call an Adversal REST endpoint. It launches `adversal-cli` as
a local MCP server over standard input/output, opens one client session, calls one tool,
and closes the subprocess.

This short-lived adapter fits Streamlit's rerun model. Submission, status checks, quota
checks, and authentication can each run independently. Adversal's own local registry
preserves request IDs between subprocesses, while this app keeps the UI-facing job
record in `runs/jobs.json`.

The boundary also keeps Adversal-specific tool names and response parsing out of the
workspace and document generators. Its cost is that response wording and browser-based
OAuth remain integration dependencies that need focused testing.

## Artifacts are the source of truth

The completed `notes.md` and its referenced images are the durable result of video
understanding. The app renders them before offering any LLM transformation. Users can
inspect what Adversal produced, verify generated documents, and export the evidence
without another model call.

The native bundle preserves that source shape. The OKF 0.2 bundle adds a portable
knowledge structure: a root index, source metadata, chapter concepts, and assets. It is
designed for downstream agents that work more reliably with bounded Markdown concepts
than with a raw multi-hour video.

Browser downloads keep the source recognizable without trusting it as a path. The app
removes the video extension, converts unsafe separators to underscores, and appends the
output type. **Download all** composes the existing notes, native bundle, OKF bundle,
and generated documents already cached for the selected backend. The native and OKF
ZIPs stay nested so their internal contracts do not change.

Image paths are treated as untrusted input. Rendering and export resolve each reference
against the job directory and reject paths outside it. That rule keeps generated or
altered Markdown from exposing unrelated local files through Streamlit or ZIP downloads.

## Why retrieval uses Qdrant

Sending an entire long transcript with every question wastes context and makes relevant
details harder for a chat model to identify. Ask instead divides the notes along
Adversal's chapter structure, embeds those chunks, and retrieves a small evidence set.

Qdrant provides durable vector search without requiring a separate service for the
local desktop target. One shared collection stores all completed videos, while a
mandatory request-ID filter limits every query to the active source. A notes hash and
deterministic point IDs make repeated indexing idempotent and allow changed notes to
replace only their own points.

Retrieval narrows the evidence; it does not guarantee truth. The final answer is still
model-generated, so the UI exposes source headings, timestamps when available,
similarity scores, and full notes for verification.

## Why embeddings do not follow the chat selector

The sidebar can switch generated text among OpenAI, Agnes AI, and Gemini. Embeddings,
however, always use OpenAI `text-embedding-3-small`.

Vectors from different embedding models do not share a reliable coordinate space.
Silently changing models when the user changes chat provider would mix incompatible
vectors in one collection and corrupt similarity results. Fixing one embedding model
and naming it in the collection keeps retrieval consistent. The tradeoff is that Ask
always requires an OpenAI key even when another provider writes the answer.

## Persistence has two lifetimes

Durable state lives under `runs/`:

- uploaded source files;
- Adversal Markdown and images;
- `jobs.json`; and
- the Qdrant collection.

Interactive state lives in Streamlit session state:

- the active job pointer;
- generated document caches; and
- Ask chat history.

This split makes expensive source processing and indexing resumable without turning the
app into a multi-user database system. Generated documents are cheap enough to recreate
and are keyed by request and provider to prevent repeated paid calls during ordinary
Streamlit reruns.

Download all reads only those existing cache entries. It never generates missing
documents, so collecting files cannot silently trigger additional provider cost.

The tradeoff is straightforward: restarting a browser session can restore a saved video
and its vectors, but not its previous conversation or generated drafts.

## Why the app targets one trusted process

The job registry uses a process-local lock, and embedded Qdrant owns files beneath
`runs/qdrant`. These choices are simple and appropriate for one Streamlit process,
whether it runs on a local computer or in the supported private Docker Space. They are
not coordination mechanisms for several servers or users.

The hosted configuration mounts one private bucket at `/data` for runs, Adversal OAuth
state, and rotating logs. It preserves the same single-process behavior across container
restarts; it does not turn the application into a shared service. A public or multi-user
deployment would still need application authentication, encrypted storage, retention
rules, shared locking or a transactional job store, and Qdrant Server or Cloud.

## Long notes and bounded generation

Generated documents use the complete notes when they are at most 50,000 characters.
Longer notes are condensed in batches no larger than 30,000 characters before the final
prompt. This bounds individual requests and reduces context pressure while preserving
grounded facts and, for visual documents, Markdown image references.

Reduction is separate from retrieval. Ask needs the most relevant
excerpts for one question; document generation needs broad coverage of the whole video.
They solve different context problems.

## Security and trust boundaries

There are three important boundaries:

1. Video and Markdown content are untrusted input. Paths are constrained to job
   directories before files are served or archived.
2. API keys come from the process environment or a gitignored `.env`; the application
   neither logs nor persists them in job records.
3. LLM output is assistance, not authoritative evidence. Prompts require grounding, but
   users still need to verify consequential claims.

Files and vectors are not encrypted and are retained until the user clears all runs.
Keep the application local or private and single-user, and avoid sensitive video unless
the underlying machine or bucket has an appropriate storage and retention policy.

## Where to go next

- Follow the [tutorial](./TUTORIAL.md) for a complete first run.
- Use the [how-to guides](./HOW_TO.md) for specific operations.
- Consult the [reference](./REFERENCE.md) for exact values and contracts.
- Read the [codebase documentation](./codebase/ARCHITECTURE.md) for implementation-level
  module evidence and maintenance risks.
