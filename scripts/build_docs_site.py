"""Build the self-contained offline documentation website.

The generated site deliberately has no runtime dependency. It embeds the
repository's tracked Markdown files as hash-routed pages, so opening
``docs/site.html`` directly from a file browser works without a web server.
"""

# The generated HTML template intentionally keeps related CSS and markup together.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

ROOT = Path(__file__).resolve().parents[1]
SITE_PATH = ROOT / "docs" / "site.html"
FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([^ ]*)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
UNORDERED_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$"
)
INLINE_RE = re.compile(r"(!?)\[([^\]]+)\]\(([^)]+)\)")
LINKED_IMAGE_RE = re.compile(r"\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)")
CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1")


@dataclass(frozen=True)
class Document:
    path: Path
    relative_path: str
    slug: str
    title: str
    category: str
    description: str
    source: str
    content_html: str = ""


def tracked_markdown() -> list[Path]:
    """Return Markdown files tracked by Git, with a safe local fallback."""

    try:
        result = subprocess.run(
            ["git", "ls-files", "*.md"],  # noqa: S607
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        paths = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    else:
        paths = [ROOT / line for line in result.stdout.splitlines() if line.strip()]

    return sorted({path for path in paths if path.is_file()}, key=lambda path: path.as_posix())


def slugify(value: str) -> str:
    value = re.sub(r"[`*_]", "", value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "page"


def page_slug(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative == "README.md":
        return "readme"
    return slugify(relative.removesuffix(".md").replace("/", "-"))


def first_heading(source: str, fallback: str) -> str:
    for line in source.splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return re.sub(r"[`*_]", "", match.group(2)).strip()
    return fallback


def category_for(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    exact_categories = {
        "README.md": "Start here",
        "docs/TUTORIAL.md": "Learn",
        "docs/HOW_TO.md": "Do",
        "docs/REFERENCE.md": "Understand",
        "docs/EXPLANATION.md": "Understand",
        "docs/TECHNICAL_GUIDE.md": "Operate",
        "docs/ARCHITECTURE.md": "Operate",
    }
    if relative.startswith("docs/codebase/"):
        return "Codebase"
    return exact_categories.get(relative, "Documentation")


def description_for(path: Path, title: str) -> str:
    descriptions = {
        "README.md": "Project overview, workflows, setup, configuration, and limitations.",
        "docs/TUTORIAL.md": "A guided first run from installation to a grounded answer and export.",
        "docs/HOW_TO.md": "Task-focused recipes for launching, operating, troubleshooting, and deploying.",
        "docs/REFERENCE.md": "Exact runtime settings, contracts, paths, models, and limits.",
        "docs/EXPLANATION.md": "The design choices behind the process-once, artifact-first architecture.",
        "docs/TECHNICAL_GUIDE.md": "Developer and operator guidance for the complete runtime lifecycle.",
        "docs/ARCHITECTURE.md": "Architecture reading order and links to the project diagrams.",
        "docs/codebase/ARCHITECTURE.md": "Implementation layers, responsibilities, patterns, and risks.",
        "docs/codebase/CONCERNS.md": "Known concerns, boundaries, and maintenance risks.",
        "docs/codebase/CONVENTIONS.md": "Coding, naming, testing, and documentation conventions.",
        "docs/codebase/INTEGRATIONS.md": "External services, SDKs, persistence, and integration boundaries.",
        "docs/codebase/STACK.md": "The runtime, dependency, deployment, and quality-tool stack.",
        "docs/codebase/STRUCTURE.md": "A map of source files, tests, docs, and runtime data directories.",
        "docs/codebase/TESTING.md": "Existing verification patterns and the current testing gap analysis.",
    }
    fallback = f"Read {title} in the project documentation set."
    return descriptions.get(path.relative_to(ROOT).as_posix(), fallback)


def parse_documents(paths: Iterable[Path]) -> list[Document]:
    documents: list[Document] = []
    used_slugs: set[str] = set()
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        title = first_heading(source, path.stem.replace("_", " ").title())
        slug = page_slug(path)
        if slug in used_slugs:
            slug = f"{slug}-{len(used_slugs)}"
        used_slugs.add(slug)
        documents.append(
            Document(
                path=path,
                relative_path=relative,
                slug=slug,
                title=title,
                category=category_for(path),
                description=description_for(path, title),
                source=source,
            )
        )
    return documents


def split_table_row(line: str) -> list[str]:
    value = line.strip()
    value = value.removeprefix("|").removesuffix("|")
    return [cell.strip() for cell in value.split("|")]


def relative_source_target(current: Path, target: str, slug_by_path: dict[str, str]) -> str:
    clean = target.strip().split()[0].strip("<>")
    if clean.startswith(("#", "http://", "https://", "mailto:", "tel:")):
        return clean

    target_path = clean.split("#", 1)[0]
    fragment = f"#{clean.split('#', 1)[1]}" if "#" in clean else ""
    if target_path.lower().endswith(".md"):
        resolved = (current.parent / target_path).resolve()
        try:
            relative = resolved.relative_to(ROOT).as_posix()
        except ValueError:
            relative = ""
        if relative in slug_by_path:
            route = f"#{slug_by_path[relative]}"
            return f"{route}/{fragment.removeprefix('#')}" if fragment else route

    # The site lives in docs/, while README links are written from the repo root.
    if current.relative_to(ROOT).as_posix() == "README.md" and target_path.startswith("./docs/"):
        return f"./{target_path.removeprefix('./docs/')}{fragment}"
    if current.relative_to(ROOT).as_posix() == "README.md" and target_path.startswith("docs/"):
        return f"./{target_path.removeprefix('docs/')}{fragment}"
    if current.relative_to(ROOT).as_posix() == "README.md" and target_path in {"./LICENSE", "LICENSE"}:
        return f"../LICENSE{fragment}"
    return f"{clean}{fragment}" if fragment and "#" not in clean else clean


def inline_markup(text: str, current: Path, slug_by_path: dict[str, str]) -> str:
    image_tokens: list[str] = []
    code_tokens: list[str] = []

    def stash_linked_image(match: re.Match[str]) -> str:
        image_target = relative_source_target(current, match.group(2), slug_by_path)
        link_target = relative_source_target(current, match.group(3), slug_by_path)
        image = (
            f'<img src="{html.escape(image_target, quote=True)}" '
            f'alt="{html.escape(match.group(1), quote=True)}" loading="lazy">'
        )
        external = link_target.startswith(("http://", "https://", "mailto:"))
        attrs = ' target="_blank" rel="noreferrer"' if external else ""
        image_tokens.append(f'<a href="{html.escape(link_target, quote=True)}"{attrs}>{image}</a>')
        return f"\x00IMAGE{len(image_tokens) - 1}\x00"

    text = LINKED_IMAGE_RE.sub(stash_linked_image, text)

    def stash_code(match: re.Match[str]) -> str:
        code_tokens.append(f"<code>{html.escape(match.group(2).strip())}</code>")
        return f"\x00CODE{len(code_tokens) - 1}\x00"

    text = CODE_SPAN_RE.sub(stash_code, text)
    pieces: list[str] = []
    cursor = 0
    for match in INLINE_RE.finditer(text):
        pieces.append(html.escape(text[cursor : match.start()]))
        label = inline_markup(match.group(2), current, slug_by_path)
        target = relative_source_target(current, match.group(3), slug_by_path)
        safe_target = html.escape(target, quote=True)
        if match.group(1):
            pieces.append(
                f'<img src="{safe_target}" alt="{html.escape(match.group(2), quote=True)}" '
                'loading="lazy">'
            )
        else:
            external = target.startswith(("http://", "https://", "mailto:"))
            attrs = ' target="_blank" rel="noreferrer"' if external else ""
            pieces.append(f'<a href="{safe_target}"{attrs}>{label}</a>')
        cursor = match.end()
    pieces.append(html.escape(text[cursor:]))
    rendered = "".join(pieces)
    for index, token in enumerate(code_tokens):
        rendered = rendered.replace(f"\x00CODE{index}\x00", token)
    for index, token in enumerate(image_tokens):
        rendered = rendered.replace(f"\x00IMAGE{index}\x00", token)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"__(.+?)__", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", rendered)
    return re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", rendered)


def render_markdown(  # noqa: C901, PLR0912, PLR0915
    source: str, current: Path, slug_by_path: dict[str, str]
) -> str:
    """Render the project's Markdown subset into safe, readable HTML."""

    lines = source.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    index = 0

    # Keep README metadata useful without letting YAML become a confusing heading.
    if lines and lines[0].strip() == "---":
        end = next((pos for pos in range(1, len(lines)) if lines[pos].strip() == "---"), None)
        if end is not None:
            metadata = "\n".join(lines[1:end])
            output.append(
                '<details class="frontmatter"><summary>Document metadata</summary>'
                f"<pre><code>{html.escape(metadata)}</code></pre></details>"
            )
            index = end + 1

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker, language = fence.groups()
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].lstrip().startswith(
                marker[0] * len(marker)
            ):
                body.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            class_name = (
                f' class="language-{html.escape(language, quote=True)}"' if language else ""
            )
            output.append(f"<pre><code{class_name}>{html.escape(chr(10).join(body))}</code></pre>")
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            raw_title = heading.group(2)
            title = inline_markup(raw_title, current, slug_by_path)
            anchor = slugify(re.sub(r"[`*_]", "", raw_title))
            output.append(f'<h{level} id="{anchor}">{title}</h{level}>')
            index += 1
            continue

        if re.match(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$", line):
            output.append("<hr>")
            index += 1
            continue

        if stripped.startswith(">"):
            quoted: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            kind = "note"
            if quoted and re.match(
                r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]$",
                quoted[0],
                re.IGNORECASE,
            ):
                kind = quoted.pop(0)[2:-1].lower()
            inner = render_markdown("\n".join(quoted), current, slug_by_path)
            output.append(f'<aside class="callout {kind}">{inner}</aside>')
            continue

        if (
            index + 1 < len(lines)
            and "|" in line
            and TABLE_SEPARATOR_RE.match(lines[index + 1])
        ):
            header = split_table_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                rows.append(split_table_row(lines[index]))
                index += 1
            head_html = "".join(
                f"<th>{inline_markup(cell, current, slug_by_path)}</th>" for cell in header
            )
            body_html = "".join(
                "<tr>" + "".join(
                    f"<td>{inline_markup(cell, current, slug_by_path)}</td>" for cell in row
                ) + "</tr>"
                for row in rows
            )
            output.append(
                f'<div class="table-wrap"><table><thead><tr>{head_html}</tr></thead>'
                f"<tbody>{body_html}</tbody></table></div>"
            )
            continue

        unordered = UNORDERED_RE.match(line)
        ordered = ORDERED_RE.match(line)
        if unordered or ordered:
            tag = "ul" if unordered else "ol"
            item_re = UNORDERED_RE if unordered else ORDERED_RE
            items: list[str] = []
            while index < len(lines):
                item = item_re.match(lines[index])
                if item:
                    items.append(inline_markup(item.group(1), current, slug_by_path))
                    index += 1
                    continue
                if items and lines[index][:1].isspace() and lines[index].strip():
                    items[-1] += " " + inline_markup(lines[index].strip(), current, slug_by_path)
                    index += 1
                    continue
                if not item:
                    break
            output.append(f"<{tag}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{tag}>")
            continue

        if line.lstrip().startswith("<"):
            raw_html: list[str] = []
            while index < len(lines) and lines[index].strip():
                raw_html.append(lines[index])
                index += 1
            output.append("\n".join(raw_html))
            continue

        paragraph: list[str] = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            next_stripped = next_line.strip()
            if (
                not next_stripped
                or FENCE_RE.match(next_line)
                or HEADING_RE.match(next_line)
                or next_stripped.startswith(">")
                or UNORDERED_RE.match(next_line)
                or ORDERED_RE.match(next_line)
                or next_line.lstrip().startswith("<")
            ):
                break
            paragraph.append(next_stripped)
            index += 1
        output.append(f"<p>{inline_markup(' '.join(paragraph), current, slug_by_path)}</p>")

    return "\n".join(output)


def home_content(documents: list[Document]) -> str:
    by_slug = {document.slug: document for document in documents}
    by_path = {document.relative_path: document for document in documents}

    def link(slug: str, label: str) -> str:
        document = by_slug[slug]
        return f'<a class="text-link" href="#{document.slug}">{html.escape(label)}</a>'

    def path_link(relative_path: str, label: str) -> str:
        document = by_path[relative_path]
        return link(document.slug, label)

    tutorial = next((document for document in documents if document.relative_path == "docs/TUTORIAL.md"), None)
    how_to = next((document for document in documents if document.relative_path == "docs/HOW_TO.md"), None)
    reference = next((document for document in documents if document.relative_path == "docs/REFERENCE.md"), None)
    technical = next((document for document in documents if document.relative_path == "docs/TECHNICAL_GUIDE.md"), None)
    codebase_architecture = next(
        (document for document in documents if document.relative_path == "docs/codebase/ARCHITECTURE.md"),
        None,
    )

    def card(number: str, eyebrow: str, title: str, body: str, document: Document | None) -> str:
        action = link(document.slug, "Open this guide") if document else ""
        return (
            '<article class="path-card">'
            f'<span class="step">{number}</span><p class="eyebrow">{html.escape(eyebrow)}</p>'
            f'<h3>{html.escape(title)}</h3><p>{html.escape(body)}</p>{action}'
            "</article>"
        )

    groups: dict[str, list[Document]] = {}
    for document in documents:
        groups.setdefault(document.category, []).append(document)
    included = ", ".join(document.relative_path for document in documents)
    return f"""
<section class="hero">
  <p class="eyebrow">Video Summarizer documentation</p>
  <h1>From first run to confident changes.</h1>
  <p class="lede">A practical, offline handbook for turning one video into structured notes,
  visual evidence, grounded answers, and reusable documents.</p>
  <div class="hero-actions">
    {link(tutorial.slug, "Start the tutorial") if tutorial else ""}
    {link(reference.slug, "Browse the reference") if reference else ""}
  </div>
</section>

<section class="section-block">
  <div class="section-heading"><p class="eyebrow">Zero to mastery</p><h2>A learning path that follows the product</h2></div>
  <div class="path-grid">
    {card("01", "Learn", "Run one complete workflow", "Install with uv, authenticate Adversal, process a video, inspect frames, and ask a grounded question.", tutorial)}
    {card("02", "Do", "Solve the task in front of you", "Use focused recipes for uploads, URLs, analysis profiles, exports, retrieval, deployment, and recovery.", how_to)}
    {card("03", "Understand", "Know what the output means", "Read the exact contracts, model settings, retrieval rules, and design reasons before making decisions.", reference)}
    {card("04", "Operate", "Change it without surprises", "Trace the runtime lifecycle, persistence boundaries, security model, integrations, and verification commands.", technical)}
    {card("05", "Codebase", "Onboard at source level", "Map the modules, stack, conventions, testing patterns, and known concerns before opening a pull request.", codebase_architecture)}
  </div>
</section>

<section class="section-block two-column">
  <div>
    <p class="eyebrow">Core idea</p><h2>Process once, reuse many ways</h2>
    <p>Adversal performs the expensive remote video-understanding pass and returns
    chaptered Markdown plus selected frames. The app keeps those artifacts as the
    evidence layer. Qdrant retrieves relevant chunks for questions, while the selected
    chat provider creates task-specific documents from bounded context.</p>
    <p>{path_link("README.md", "The README")}, {path_link("docs/EXPLANATION.md", "the explanation")}, and
    {path_link("docs/TECHNICAL_GUIDE.md", "the technical guide")} describe this boundary in more detail.</p>
  </div>
  <div class="fact-panel">
    <div><strong>9</strong><span>supported output workflows</span></div>
    <div><strong>3</strong><span>source artifact downloads</span></div>
    <div><strong>1</strong><span>reusable video workspace</span></div>
  </div>
</section>

<section class="section-block">
  <div class="section-heading"><p class="eyebrow">Included in this site</p><h2>Every tracked Markdown page</h2></div>
  <p class="muted">This file is generated from the repository at build time. It embeds the current
  Markdown, rewrites internal documentation links to local routes, and keeps external links visible.
  The source inventory is: {html.escape(included)}.</p>
  <div class="document-grid">
    {''.join(f'<a class="document-card" href="#{document.slug}"><span>{html.escape(document.category)}</span><strong>{html.escape(document.title)}</strong><small>{html.escape(document.description)}</small></a>' for document in documents)}
  </div>
</section>

<section class="section-block diagrams">
  <div><p class="eyebrow">Visual orientation</p><h2>Read the architecture as a picture</h2>
  <p>Open the diagram index for the system, processing sequence, job lifecycle, and private Space deployment views.</p></div>
  <a class="diagram-link" href="./diagrams/video-summarizer-architecture.html">Open architecture diagram ↗</a>
</section>
"""


def build_site(documents: list[Document]) -> str:
    slug_by_path = {document.relative_path: document.slug for document in documents}
    rendered = [
        replace(
            document,
            content_html=render_markdown(document.source, document.path, slug_by_path),
        )
        for document in documents
    ]
    pages = [
        {
            "slug": "home",
            "title": "Zero to mastery",
            "category": "Start here",
            "description": "A guided path through the complete project documentation.",
            "source": "Generated overview",
            "content": home_content(rendered),
        }
    ]
    pages.extend(
        {
            "slug": document.slug,
            "title": document.title,
            "category": document.category,
            "description": document.description,
            "source": document.relative_path,
            "content": document.content_html,
        }
        for document in rendered
    )
    payload = json.dumps(pages, ensure_ascii=False).replace("</script", "<\\/script")
    nav_groups = ["Start here", "Learn", "Do", "Understand", "Operate", "Codebase", "Documentation"]
    nav_json = json.dumps(nav_groups)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Offline zero-to-mastery documentation for Video Summarizer">
  <title>Video Summarizer docs</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #647180;
      --line: #dce3e8;
      --paper: #f7f9fa;
      --panel: #ffffff;
      --accent: #2166f3;
      --accent-soft: #eaf0ff;
      --teal: #0d7f78;
      --shadow: 0 18px 45px rgba(25, 45, 65, .08);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.65 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    a {{ color: var(--accent); }}
    .shell {{ min-height: 100vh; display: grid; grid-template-columns: 290px minmax(0, 1fr); }}
    .sidebar {{ position: sticky; top: 0; height: 100vh; overflow-y: auto; background: #111c29; color: #e9f0f6; padding: 28px 20px 22px; }}
    .brand {{ display: flex; align-items: center; gap: 10px; color: white; text-decoration: none; font-weight: 750; letter-spacing: -.02em; font-size: 17px; margin: 0 8px 25px; }}
    .brand-mark {{ width: 28px; height: 28px; border-radius: 9px; display: grid; place-items: center; background: linear-gradient(135deg, #6e9aff, #42d4bc); color: #0d1b2a; font-weight: 900; }}
    .sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }}
    .search {{ width: 100%; border: 1px solid #344557; border-radius: 10px; padding: 10px 12px; background: #1b2a3a; color: white; outline: none; }}
    .search::placeholder {{ color: #9aaaba; }}
    .search:focus {{ border-color: #7fa5ff; box-shadow: 0 0 0 3px rgba(127, 165, 255, .18); }}
    .nav {{ margin-top: 25px; }}
    .nav-group {{ margin: 0 0 19px; }}
    .nav-label {{ color: #91a2b4; text-transform: uppercase; letter-spacing: .12em; font-size: 10px; font-weight: 800; padding: 0 9px; margin-bottom: 6px; }}
    .nav a {{ display: block; border-radius: 8px; padding: 7px 9px; color: #d8e2ec; text-decoration: none; line-height: 1.35; }}
    .nav a:hover, .nav a.active {{ color: white; background: #253a51; }}
    .nav a small {{ display: block; color: #8fa1b4; font-size: 11px; margin-top: 2px; }}
    .sidebar-footer {{ margin: 28px 8px 0; color: #91a2b4; font-size: 12px; }}
    main {{ min-width: 0; }}
    .topbar {{ height: 62px; display: flex; justify-content: flex-end; align-items: center; gap: 12px; padding: 0 7vw; border-bottom: 1px solid var(--line); background: rgba(247, 249, 250, .9); position: sticky; top: 0; z-index: 5; backdrop-filter: blur(8px); }}
    .topbar span {{ color: var(--muted); font-size: 12px; }}
    .content {{ max-width: 1120px; padding: 50px 7vw 90px; margin: 0 auto; }}
    .hero {{ padding: 32px 0 62px; max-width: 830px; }}
    .eyebrow {{ color: var(--teal); font-size: 11px; font-weight: 850; letter-spacing: .13em; margin: 0 0 11px; text-transform: uppercase; }}
    h1, h2, h3 {{ letter-spacing: -.035em; line-height: 1.12; margin: 0 0 15px; }}
    h1 {{ font-size: clamp(2.5rem, 6vw, 4.8rem); max-width: 760px; }}
    h2 {{ font-size: clamp(1.65rem, 3vw, 2.35rem); }}
    h3 {{ font-size: 1.25rem; }}
    .lede {{ color: var(--muted); font-size: 19px; max-width: 680px; margin: 0 0 25px; }}
    .hero-actions {{ display: flex; flex-wrap: wrap; gap: 11px; }}
    .text-link, .diagram-link {{ display: inline-flex; align-items: center; width: fit-content; border-radius: 8px; padding: 9px 13px; background: var(--accent-soft); color: #174ec4; text-decoration: none; font-weight: 700; }}
    .text-link:hover, .diagram-link:hover {{ background: #dbe6ff; }}
    .section-block {{ border-top: 1px solid var(--line); padding: 45px 0; }}
    .section-heading {{ margin-bottom: 24px; }}
    .path-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }}
    .path-card, .document-card, .fact-panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); }}
    .path-card {{ padding: 21px; min-height: 265px; display: flex; flex-direction: column; align-items: flex-start; }}
    .path-card .step {{ color: var(--accent); font-size: 12px; font-weight: 850; letter-spacing: .12em; }}
    .path-card .eyebrow {{ margin-top: 18px; margin-bottom: 8px; }}
    .path-card p:not(.eyebrow) {{ color: var(--muted); margin: 0 0 18px; }}
    .path-card .text-link {{ margin-top: auto; padding: 0; background: transparent; }}
    .two-column {{ display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(230px, .6fr); gap: 38px; align-items: start; }}
    .two-column p {{ color: var(--muted); }}
    .fact-panel {{ padding: 7px 20px; }}
    .fact-panel div {{ padding: 17px 0; border-bottom: 1px solid var(--line); }}
    .fact-panel div:last-child {{ border-bottom: 0; }}
    .fact-panel strong {{ display: block; color: var(--accent); font-size: 31px; line-height: 1; }}
    .fact-panel span {{ color: var(--muted); font-size: 12px; }}
    .muted {{ color: var(--muted); }}
    .document-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(225px, 1fr)); gap: 12px; margin-top: 23px; }}
    .document-card {{ display: flex; flex-direction: column; gap: 6px; padding: 17px; color: var(--ink); text-decoration: none; }}
    .document-card:hover {{ border-color: #9db8ff; transform: translateY(-1px); }}
    .document-card span {{ color: var(--teal); font-size: 10px; font-weight: 850; letter-spacing: .1em; text-transform: uppercase; }}
    .document-card small {{ color: var(--muted); line-height: 1.45; }}
    .diagrams {{ display: flex; align-items: center; justify-content: space-between; gap: 20px; }}
    .page-meta {{ border-bottom: 1px solid var(--line); margin-bottom: 35px; padding-bottom: 22px; }}
    .page-meta h1 {{ font-size: clamp(2.2rem, 5vw, 3.8rem); margin-bottom: 10px; }}
    .page-meta p {{ color: var(--muted); margin: 0; }}
    .source-path {{ display: inline-block; color: var(--teal); font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; margin-top: 8px; }}
    .markdown-body {{ max-width: 850px; }}
    .markdown-body h1 {{ display: none; }}
    .markdown-body h2 {{ margin-top: 43px; padding-top: 5px; }}
    .markdown-body h3 {{ margin-top: 30px; }}
    .markdown-body p, .markdown-body li {{ color: #344352; }}
    .markdown-body p {{ max-width: 78ch; }}
    .markdown-body li {{ margin: 5px 0; }}
    .markdown-body ul, .markdown-body ol {{ padding-left: 25px; }}
    .markdown-body pre {{ overflow-x: auto; border: 1px solid #26384a; border-radius: 10px; background: #172535; color: #e7eff8; padding: 16px; font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .markdown-body code {{ border-radius: 4px; background: #edf1f5; padding: 2px 5px; font: .9em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .markdown-body pre code {{ background: transparent; padding: 0; }}
    .table-wrap {{ overflow-x: auto; margin: 20px 0; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid var(--line); font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; }}
    th {{ background: #f0f4f7; color: #28394a; font-size: 12px; }}
    blockquote, .callout {{ border-left: 4px solid #9db8ff; margin: 22px 0; padding: 7px 17px; background: #f1f5ff; }}
    .callout.note {{ border-color: #88a5c7; }} .callout.tip {{ border-color: #35aa8e; background: #eefaf7; }}
    .callout.warning, .callout.caution {{ border-color: #d98d32; background: #fff7eb; }}
    .frontmatter {{ margin: 0 0 20px; color: var(--muted); }}
    .frontmatter summary {{ cursor: pointer; font-size: 12px; font-weight: 700; }}
    .frontmatter pre {{ margin: 8px 0; }}
    .not-found {{ padding: 70px 0; }}
    @media (max-width: 820px) {{
      .shell {{ grid-template-columns: 1fr; }} .sidebar {{ position: static; height: auto; padding: 18px 16px; }}
      .nav {{ max-height: 290px; overflow-y: auto; }} .sidebar-footer {{ margin-top: 17px; }}
      .topbar {{ padding: 0 20px; }} .content {{ padding: 35px 20px 65px; }}
      .two-column, .diagrams {{ grid-template-columns: 1fr; display: grid; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <a class="brand" href="#home"><span class="brand-mark">V</span> Video Summarizer</a>
      <label><span class="sr-only">Filter documentation</span><input id="search" class="search" type="search" placeholder="Filter pages  (Ctrl K)" autocomplete="off"></label>
      <nav id="nav" class="nav" aria-label="Documentation navigation"></nav>
      <p class="sidebar-footer">Offline site generated from tracked Markdown.<br>Open <code>docs/site.html</code> directly.</p>
    </aside>
    <main>
      <div class="topbar"><span id="page-count"></span><span>Local, versioned, and source-linked</span></div>
      <div id="content" class="content" aria-live="polite"></div>
    </main>
  </div>
  <script id="docs-data" type="application/json">{payload}</script>
  <script>
    const pages = JSON.parse(document.getElementById("docs-data").textContent);
    const groups = {nav_json};
    const nav = document.getElementById("nav");
    const content = document.getElementById("content");
    const search = document.getElementById("search");
    const pageCount = document.getElementById("page-count");

    function buildNav(filter = "") {{
      const query = filter.trim().toLowerCase();
      nav.innerHTML = "";
      groups.forEach(group => {{
        const entries = pages.filter(page => page.category === group &&
          (!query || `${{page.title}} ${{page.description}}`.toLowerCase().includes(query)));
        if (!entries.length) return;
        const section = document.createElement("div");
        section.className = "nav-group";
        section.innerHTML = `<div class="nav-label">${{group}}</div>`;
        entries.forEach(page => {{
          const link = document.createElement("a");
          link.href = `#${{page.slug}}`;
          link.dataset.slug = page.slug;
          link.innerHTML = `${{page.title}}<small>${{page.description}}</small>`;
          section.appendChild(link);
        }});
        nav.appendChild(section);
      }});
    }}

    function showPage() {{
      const route = window.location.hash.slice(1) || "home";
      const [slug, anchor] = route.split("/", 2);
      const page = pages.find(candidate => candidate.slug === slug) || pages[0];
      if (page.slug !== slug) window.history.replaceState(null, "", `#${{page.slug}}`);
      const isHome = page.slug === "home";
      content.innerHTML = isHome ? page.content :
        `<header class="page-meta"><p class="eyebrow">${{page.category}}</p><h1>${{page.title}}</h1><p>${{page.description}}</p><span class="source-path">${{page.source}}</span></header><article class="markdown-body">${{page.content}}</article>`;
      document.title = `${{page.title}} · Video Summarizer docs`;
      document.querySelectorAll(".nav a").forEach(link => link.classList.toggle("active", link.dataset.slug === page.slug));
      pageCount.textContent = `${{pages.length - 1}} source docs`;
      window.scrollTo({{top: 0, behavior: "instant"}});
      if (anchor) document.getElementById(anchor)?.scrollIntoView();
    }}

    search.addEventListener("input", event => buildNav(event.target.value));
    document.addEventListener("keydown", event => {{
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {{ event.preventDefault(); search.focus(); }}
    }});
    window.addEventListener("hashchange", showPage);
    buildNav();
    showPage();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the generated site differs from disk.")
    args = parser.parse_args()
    documents = parse_documents(tracked_markdown())
    generated = build_site(documents)
    if args.check:
        existing = SITE_PATH.read_text(encoding="utf-8") if SITE_PATH.exists() else ""
        if existing != generated:
            message = (
                f"{SITE_PATH.relative_to(ROOT)} is out of date; "
                "run this script to rebuild it"
            )
            raise SystemExit(message)
        print(f"{SITE_PATH.relative_to(ROOT)} is up to date ({len(documents)} source docs)")  # noqa: T201
        return
    SITE_PATH.write_text(generated, encoding="utf-8", newline="\n")
    print(f"Wrote {SITE_PATH.relative_to(ROOT)} with {len(documents)} source docs")  # noqa: T201


if __name__ == "__main__":
    main()
