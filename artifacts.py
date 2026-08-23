"""Read, package, and export the artifacts produced by Adversal."""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pipeline
from pipeline import Job

if TYPE_CHECKING:
    from pathlib import Path

CHAPTER_SPLIT_RE = re.compile(r"\n\s*\*\s*\*\s*\*\s*\n")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class LocalImage:
    alt: str
    src: str
    path: Path
    relative_path: Path


@dataclass(frozen=True)
class Section:
    heading: str
    markdown: str


def split_sections(markdown_text: str) -> list[Section]:
    sections = []
    for raw_section in CHAPTER_SPLIT_RE.split(markdown_text):
        text = raw_section.strip()
        if not text:
            continue
        heading_match = HEADING_RE.search(text)
        heading = heading_match.group(2).strip() if heading_match else "Untitled"
        sections.append(Section(heading=heading, markdown=text))
    return sections


def find_local_images(markdown_text: str, base_dir: Path) -> list[LocalImage]:
    """Return unique, referenced local images without allowing path traversal."""
    resolved_base = base_dir.resolve()
    images = []
    seen: set[Path] = set()
    for match in pipeline.IMAGE_RE.finditer(markdown_text):
        alt, src = match.group(1), match.group(2)
        path = pipeline._resolve_local_image(resolved_base, src)  # noqa: SLF001
        if path is None or path in seen:
            continue
        seen.add(path)
        images.append(
            LocalImage(
                alt=alt,
                src=src,
                path=path,
                relative_path=path.relative_to(resolved_base),
            )
        )
    return images


def _zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, content in files:
            archive.writestr(archive_name, content)
    return output.getvalue()


def build_native_bundle(job: Job) -> bytes:
    notes = pipeline.load_completed_notes(job)
    files = [(job.file_name, notes.encode())]
    files.extend(
        (image.relative_path.as_posix(), image.path.read_bytes())
        for image in find_local_images(notes, job.output_path)
    )
    return _zip_bytes(files)


def _yaml_value(value: object) -> str:
    """JSON scalars and arrays are valid YAML and require no extra dependency."""
    return json.dumps(value, ensure_ascii=False)


def _frontmatter(fields: list[tuple[str, object]]) -> str:
    lines = ["---"]
    lines.extend(f"{key}: {_yaml_value(value)}" for key, value in fields)
    lines.append("---")
    return "\n".join(lines)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "section"


def _rewrite_image_paths(markdown_text: str, images: list[LocalImage]) -> str:
    by_src = {image.src: image for image in images}

    def replace(match: re.Match[str]) -> str:
        alt, src = match.group(1), match.group(2)
        image = by_src.get(src)
        if image is None:
            return match.group(0)
        return f"![{alt}](../assets/{image.relative_path.as_posix()})"

    return pipeline.IMAGE_RE.sub(replace, markdown_text)


def build_okf_bundle(job: Job) -> bytes:
    notes = pipeline.load_completed_notes(job)
    sections = split_sections(notes)
    images = find_local_images(notes, job.output_path)
    generated_at = datetime.fromtimestamp(
        job.completed_at or job.submitted_at, tz=UTC
    ).isoformat().replace("+00:00", "Z")
    resource = job.source_url or f"urn:adversal:request:{job.request_id}"
    chapter_files = [
        f"chapters/{index:03d}-{_slugify(section.heading)}.md"
        for index, section in enumerate(sections, start=1)
    ]

    index_lines = [
        _frontmatter([("okf_version", "0.2")]),
        "",
        f"# {job.source_name}",
        "",
        "* [Video overview](video.md) - Source metadata and chapter index.",
    ]
    index_lines.extend(
        f"* [{section.heading}]({path}) - Adversal-generated video knowledge."
        for section, path in zip(sections, chapter_files, strict=True)
    )

    video_lines = [
        _frontmatter(
            [
                ("type", "Video"),
                ("title", job.source_name),
                ("description", "Adversal-generated structured video analysis."),
                ("resource", resource),
                ("tags", ["video", "adversal"]),
                ("status", "draft"),
                ("generated", {"by": "adversal/video-understanding", "at": generated_at}),
            ]
        ),
        "",
        "# Chapters",
        "",
    ]
    video_lines.extend(
        f"* [{section.heading}]({path})"
        for section, path in zip(sections, chapter_files, strict=True)
    )

    files = [
        ("index.md", "\n".join(index_lines).encode()),
        ("video.md", "\n".join(video_lines).encode()),
    ]
    for section, path in zip(sections, chapter_files, strict=True):
        body = _rewrite_image_paths(section.markdown, images)
        concept = "\n\n".join(
            [
                _frontmatter(
                    [
                        ("type", "Video Chapter"),
                        ("title", section.heading),
                        ("description", f"A chapter from {job.source_name}."),
                        ("tags", ["video", "chapter", "adversal"]),
                        ("status", "draft"),
                        (
                            "generated",
                            {"by": "adversal/video-understanding", "at": generated_at},
                        ),
                        (
                            "sources",
                            [
                                {
                                    "id": "source-video",
                                    "resource": resource,
                                    "title": job.source_name,
                                }
                            ],
                        ),
                    ]
                ),
                body,
            ]
        )
        files.append((path, concept.encode()))
    files.extend(
        (f"assets/{image.relative_path.as_posix()}", image.path.read_bytes())
        for image in images
    )
    return _zip_bytes(files)
