# Architecture documentation

Architecture material is organized by reader intent:

- [Explanation](./EXPLANATION.md) discusses why the application uses a process-once
  workspace, artifact-first outputs, Qdrant retrieval, two persistence lifetimes, and a
  local single-process deployment model.
- [Reference](./REFERENCE.md) records exact runtime contracts, model settings, Qdrant
  behavior, storage paths, commands, and limits.
- [Codebase architecture](./codebase/ARCHITECTURE.md) maps the implementation layers,
  module responsibilities, patterns, and maintenance risks.

The current system diagram is available as
[HTML](./diagrams/video-summarizer-architecture.html),
[SVG](./diagrams/video-summarizer-architecture.svg), or
[PNG](./diagrams/video-summarizer-architecture.png).
