# Using Video Summarizer

The user documentation now follows the Diátaxis structure. Choose the page that matches
what you need:

- [Tutorial: process your first video](./TUTORIAL.md): learn the complete workflow by
  completing one guided example.
- [How-to guides](./HOW_TO.md): start the app, configure providers, process sources,
  search, export individual artifacts or Download All, resume work, troubleshoot, and
  delete local data. It also covers focused clip ranges, exact frame timestamps, and
  retrying an existing Adversal request without resubmission.
- [Reference](./REFERENCE.md): look up supported inputs, exact options, models,
  environment variables, download-filename and archive contracts, storage, and commands.
- [Explanation](./EXPLANATION.md): understand the process-once architecture, Adversal
  MCP boundary, Qdrant retrieval, persistence, and security tradeoffs.

For implementation-level onboarding, continue to the
[technical guide](./TECHNICAL_GUIDE.md) or the deeper
[codebase documentation](./codebase/ARCHITECTURE.md).

## Open the offline documentation site

The repository also includes [interactive HTML docs](./site.html). Open that file
directly in a browser for a searchable sidebar, a zero-to-mastery learning path, and
every tracked Markdown page in one local site.

After editing documentation, rebuild the site from the repository root:

```bash
uv run python scripts/build_docs_site.py
```

Use `uv run python scripts/build_docs_site.py --check` in a quality check to catch a
stale generated site.
