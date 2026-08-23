# Architecture documentation

Architecture material is organized by reader intent:

- [Explanation](./EXPLANATION.md) discusses why the application uses a process-once
  workspace, artifact-first and aggregate downloads, Qdrant retrieval, two persistence
  lifetimes, and a trusted single-process deployment model for local and private Docker
  execution.
- [Reference](./REFERENCE.md) records exact runtime contracts, model settings, Qdrant
  behavior, storage paths, commands, and limits.
- [Codebase architecture](./codebase/ARCHITECTURE.md) maps the implementation layers,
  module responsibilities, persistent MCP worker/session, failure recovery, patterns,
  and maintenance risks.
- [Technical guide](./TECHNICAL_GUIDE.md) provides the developer/operator view of
  runtime contracts, export composition, persistence, integrations, security,
  deployment, and change paths.

The current system diagram is available as
[HTML](./diagrams/video-summarizer-architecture.html),
[SVG](./diagrams/video-summarizer-architecture.svg), or
[PNG](./diagrams/video-summarizer-architecture.png).

For a guided, searchable view of this documentation set, open the
[offline HTML documentation site](./site.html).

Focused diagrams:

- [System architecture](./diagrams/system-architecture.svg) shows the complete process-once and reuse path ([Mermaid source](./diagrams/system-architecture.mmd)).
- [Video-processing sequence](./diagrams/video-processing-sequence.svg) traces submission, persistent-session polling, and authentication ([Mermaid source](./diagrams/video-processing-sequence.mmd)).
- [Job lifecycle](./diagrams/job-lifecycle.svg) shows terminal states and retrying the same request ID ([Mermaid source](./diagrams/job-lifecycle.mmd)).
- [Private Hugging Face deployment](./diagrams/private-space-deployment.html)
