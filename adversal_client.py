"""Persistent, typed wrapper around the adversal-cli MCP stdio server."""

from __future__ import annotations

import asyncio
import atexit
import json
import re
import shutil
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from queue import Queue
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

import observability

VideoType = Literal["generic", "lesson", "interview", "meeting"]
ImageDensity = Literal["minimal", "selective", "generous"]
VideoStatus = Literal["COMPLETED", "FAILED", "RUNNING", "UNKNOWN"]

logger = observability.get_logger("adversal")

REQUEST_ID_RE = re.compile(r'request[_ ]?id["\':\s]+([\w-]+)', re.IGNORECASE)
STATUS_RE = re.compile(r"^\s*(COMPLETED|FAILED|RUNNING|UNKNOWN)\b", re.IGNORECASE)


class AdversalError(Exception):
    """Raised when an Adversal tool or its MCP connection fails."""


class AdversalAuthRequiredError(AdversalError):
    """Raised when a tool call responds with AUTHENTICATION REQUIRED."""


@dataclass(frozen=True)
class StatusResult:
    """Parsed result from Adversal's check_video_status tool."""

    status: VideoStatus
    message: str
    error: str | None = None


@dataclass(frozen=True)
class _ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    future: Future[CallToolResult]


def _server_params() -> StdioServerParameters:
    exe = shutil.which("adversal-cli")
    if exe is None:
        msg = "adversal-cli not found on PATH — run `uv sync`."
        raise AdversalError(msg)
    return StdioServerParameters(command=exe)


class _MCPConnection:
    """One MCP subprocess and session, reused for the life of this app process."""

    def __init__(self) -> None:
        self._requests: Queue[_ToolCall | None] = Queue()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="adversal-mcp", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise self._startup_error

    def _run(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        try:
            async with (
                stdio_client(_server_params()) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                self._ready.set()
                while request := await asyncio.to_thread(self._requests.get):
                    try:
                        result = await session.call_tool(
                            request.tool_name,
                            arguments=request.arguments,
                        )
                    except Exception as exc:  # noqa: BLE001
                        request.future.set_exception(exc)
                    else:
                        request.future.set_result(result)
        except BaseException as exc:  # noqa: BLE001
            self._startup_error = exc
            self._ready.set()

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
        if self._closed or not self._thread.is_alive():
            msg = "Adversal MCP connection is closed."
            raise RuntimeError(msg)
        future: Future[CallToolResult] = Future()
        self._requests.put(_ToolCall(tool_name, arguments, future))
        return future.result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._requests.put(None)
        self._thread.join()


_connection: _MCPConnection | None = None
_connection_lock = threading.RLock()


def _close_connection() -> None:
    global _connection
    with _connection_lock:
        connection, _connection = _connection, None
        if connection is not None:
            connection.close()


atexit.register(_close_connection)


def _response_text(result: CallToolResult) -> str:
    text = "\n".join(
        content.text for content in result.content if isinstance(content, TextContent)
    ).strip()
    if text:
        return text

    structured = result.structuredContent
    if isinstance(structured, dict) and isinstance(structured.get("result"), str):
        return structured["result"].strip()
    if structured is not None:
        return json.dumps(structured)
    return ""


def _call_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    global _connection  # noqa: PLW0603
    started = time.perf_counter()
    logger.info("tool.started tool=%s", tool_name)
    connection: _MCPConnection | None = None
    try:
        with _connection_lock:
            if _connection is None:
                _connection = _MCPConnection()
            connection = _connection
            result = connection.call_tool(tool_name, arguments)
    except AdversalError:
        raise
    except Exception as exc:
        with _connection_lock:
            if connection is not None and _connection is connection:
                _connection = None
                try:
                    connection.close()
                except Exception as close_exc:  # noqa: BLE001
                    observability.log_failure(logger, "connection.close", close_exc)
        observability.log_failure(
            logger,
            "tool",
            exc,
            tool=tool_name,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        msg = "Adversal MCP connection failed. Retry the operation."
        raise AdversalError(msg) from exc

    text = _response_text(result)
    if "AUTHENTICATION REQUIRED" in text.upper():
        logger.warning(
            "tool.authentication_required tool=%s duration_ms=%s",
            tool_name,
            round((time.perf_counter() - started) * 1000),
        )
        raise AdversalAuthRequiredError(text)
    if result.isError:
        logger.error(
            "tool.remote_error tool=%s error_type=AdversalError duration_ms=%s",
            tool_name,
            round((time.perf_counter() - started) * 1000),
        )
        raise AdversalError(text or "Unknown adversal-cli error.")
    logger.info(
        "tool.completed tool=%s duration_ms=%s",
        tool_name,
        round((time.perf_counter() - started) * 1000),
    )
    return text


def _require_response(text: str, success_pattern: re.Pattern[str]) -> re.Match[str]:
    match = success_pattern.search(text)
    if match is None:
        raise AdversalError(text or "Adversal returned an empty response.")
    return match


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
) -> str:
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
    text = _call_tool("process_video", {key: value for key, value in args.items() if value})
    return _require_response(text, REQUEST_ID_RE).group(1)


def check_video_status(request_id: str) -> StatusResult:
    text = _call_tool("check_video_status", {"request_id": request_id})
    status = _require_response(text, STATUS_RE).group(1).upper()
    if status not in {"COMPLETED", "FAILED", "RUNNING", "UNKNOWN"}:
        raise AdversalError(text)
    typed_status: VideoStatus = status
    error = text if typed_status in {"FAILED", "UNKNOWN"} else None
    return StatusResult(status=typed_status, message=text, error=error)


def check_remaining_quota() -> str:
    text = _call_tool("check_remaining_quota", {})
    if not text.lstrip().upper().startswith("QUOTA STATUS"):
        raise AdversalError(text or "Adversal returned an empty quota response.")
    return text


def authenticate() -> None:
    """Block until browser OAuth succeeds or raise with Adversal's failure message."""
    text = _call_tool("authenticate", {})
    if not text.lstrip().upper().startswith("AUTHENTICATED"):
        raise AdversalError(text or "Adversal returned an empty authentication response.")
