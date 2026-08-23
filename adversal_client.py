"""Thin stateless wrapper around the adversal-cli MCP stdio server.

Every public function spawns a fresh adversal-cli subprocess, makes one
MCP tool call, and tears down. This is safe because Adversal's local job
registry persists on disk across subprocess restarts (per its own docs),
so there is no need to keep a long-lived subprocess alive across Streamlit
reruns.
"""

import asyncio
import shutil
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

VideoType = Literal["generic", "lesson", "interview", "meeting"]
ImageDensity = Literal["minimal", "selective", "generous"]


class AdversalAuthRequiredError(Exception):
    """Raised when a tool call responds with AUTHENTICATION REQUIRED."""


class AdversalError(Exception):
    """Raised on any other tool-level error."""


def _server_params() -> StdioServerParameters:
    exe = shutil.which("adversal-cli")
    if exe is None:
        msg = "adversal-cli not found on PATH — run `uv sync`."
        raise AdversalError(msg)
    return StdioServerParameters(command=exe)


async def _call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | str:
    params = _server_params()
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(tool_name, arguments=arguments)
        text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
        is_error = result.isError
        structured = result.structuredContent

    # Raised outside the stdio_client/ClientSession `async with` block on purpose: anyio
    # wraps exceptions raised *inside* that block's task group in an ExceptionGroup, which
    # a plain `except AdversalError` at the call site would silently fail to catch.
    if "AUTHENTICATION REQUIRED" in text.upper():
        raise AdversalAuthRequiredError(text)
    if is_error:
        raise AdversalError(text or "unknown adversal-cli error")
    return structured if structured is not None else text


def process_video(
    *,
    video_path: str | None = None,
    video_url: str | None = None,
    output_path: str,
    file_name: str = "notes.md",
    type: VideoType = "generic",  # noqa: A002 - matches adversal-cli's own parameter name
    images: ImageDensity = "minimal",
    start_time: str | None = None,
    end_time: str | None = None,
    timestamps: list[str] | None = None,
) -> dict[str, Any] | str:
    if (video_path is None) == (video_url is None):
        msg = "exactly one of video_path/video_url is required"
        raise ValueError(msg)
    args = {
        "video_path": video_path,
        "video_url": video_url,
        "output_path": output_path,
        "file_name": file_name,
        "type": type,
        "images": images,
        "start_time": start_time,
        "end_time": end_time,
        "timestamps": timestamps,
    }
    args = {k: v for k, v in args.items() if v is not None}
    return asyncio.run(_call_tool("process_video", args))


def check_video_status(request_id: str) -> dict[str, Any] | str:
    return asyncio.run(_call_tool("check_video_status", {"request_id": request_id}))


def check_remaining_quota() -> dict[str, Any] | str:
    return asyncio.run(_call_tool("check_remaining_quota", {}))


def authenticate() -> None:
    """Block while the user completes browser OAuth sign-in.

    Local single-user dev only: the browser opens on whatever machine runs
    this process.
    """
    asyncio.run(_call_tool("authenticate", {}))
