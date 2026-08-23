"""Rerun-safe, metadata-only application logging."""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

LOGGER_NAME: Final = "video_summarizer"
DEFAULT_LOG_DIR: Final = Path("logs")
LOG_FILE_NAME: Final = "video-summarizer.log"
MAX_LOG_BYTES: Final = 5 * 1024 * 1024
BACKUP_COUNT: Final = 3
DEFAULT_LOG_LEVEL: Final = "INFO"
LOG_LEVEL_ENV: Final = "VIDEO_SUMMARIZER_LOG_LEVEL"
SECRET_ENV_NAMES: Final = ("OPENAI_API_KEY", "AGNES_API_KEY", "GOOGLE_API_KEY")
VALID_LEVELS: Final = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_CONFIGURE_LOCK = threading.Lock()
_TOKEN_PATTERNS = (
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{16,}\b"),
)


def _redact(message: str) -> str:
    redacted = message
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    for pattern in _TOKEN_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted.replace("\r", "\\r").replace("\n", "\\n")[:4096]


class _SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.getMessage())
        record.args = ()
        return True


def _managed(handler: logging.Handler) -> bool:
    return bool(getattr(handler, "_video_summarizer_handler", False))


def _mark_managed(handler: logging.Handler) -> logging.Handler:
    handler.__dict__["_video_summarizer_handler"] = True
    return handler


def _level(level_name: str | None) -> tuple[str, int, bool]:
    requested = (level_name or os.environ.get(LOG_LEVEL_ENV, DEFAULT_LOG_LEVEL)).upper()
    if requested in VALID_LEVELS:
        return requested, VALID_LEVELS[requested], False
    return DEFAULT_LOG_LEVEL, VALID_LEVELS[DEFAULT_LOG_LEVEL], True


def configure_logging(
    *, log_dir: Path = DEFAULT_LOG_DIR, level_name: str | None = None
) -> logging.Logger:
    """Configure the process-wide app logger once across Streamlit reruns."""
    resolved_name, resolved_level, invalid_level = _level(level_name)
    logger = logging.getLogger(LOGGER_NAME)
    with _CONFIGURE_LOCK:
        logger.setLevel(resolved_level)
        logger.propagate = False
        existing = [handler for handler in logger.handlers if _managed(handler)]
        if existing:
            for handler in existing:
                handler.setLevel(resolved_level)
            return logger

        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        redaction_filter = _SecretRedactingFilter()

        console = _mark_managed(logging.StreamHandler(sys.stdout))
        console.setLevel(resolved_level)
        console.setFormatter(formatter)
        console.addFilter(redaction_filter)
        logger.addHandler(console)

        file_enabled = False
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = _mark_managed(
                RotatingFileHandler(
                    log_dir / LOG_FILE_NAME,
                    maxBytes=MAX_LOG_BYTES,
                    backupCount=BACKUP_COUNT,
                    encoding="utf-8",
                )
            )
        except OSError as exc:
            logger.warning("logging.file_unavailable error_type=%s", type(exc).__name__)
        else:
            file_handler.setLevel(resolved_level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(redaction_filter)
            logger.addHandler(file_handler)
            file_enabled = True
        logger.info(
            "logging.configured level=%s file=logs/%s file_enabled=%s",
            resolved_name,
            LOG_FILE_NAME,
            file_enabled,
        )
        if invalid_level:
            logger.warning(
                "logging.invalid_level fallback=%s env=%s", DEFAULT_LOG_LEVEL, LOG_LEVEL_ENV
            )
    return logger


def get_logger(component: str) -> logging.Logger:
    """Return a child logger that inherits the central handlers."""
    return logging.getLogger(f"{LOGGER_NAME}.{component}")


def log_failure(
    logger: logging.Logger,
    event: str,
    exc: BaseException,
    **metadata: object,
) -> None:
    """Log failure metadata without serializing the exception or user content."""
    fields = " ".join(f"{key}={value}" for key, value in metadata.items())
    suffix = f" {fields}" if fields else ""
    logger.error("%s.failed error_type=%s%s", event, type(exc).__name__, suffix)
    if logger.isEnabledFor(logging.DEBUG) and exc.__traceback__ is not None:
        frames = "".join(traceback.format_tb(exc.__traceback__)).rstrip()
        logger.debug("%s.traceback\n%s", event, frames)
