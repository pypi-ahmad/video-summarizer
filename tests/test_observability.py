# ruff: noqa: ANN001, ANN201, INP001, S101, SLF001

import logging
from pathlib import Path

import pytest

import llm
import observability

EXPECTED_HANDLER_COUNT = 2
EXPECTED_CONSOLE_HANDLER_COUNT = 1


def _reset_logging() -> None:
    logger = logging.getLogger(observability.LOGGER_NAME)
    for handler in list(logger.handlers):
        if observability._managed(handler):
            logger.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def reset_logging():
    _reset_logging()
    yield
    _reset_logging()


def _read_log(log_dir: Path) -> str:
    for handler in logging.getLogger(observability.LOGGER_NAME).handlers:
        handler.flush()
    return (log_dir / observability.LOG_FILE_NAME).read_text(encoding="utf-8")


def _raise_private_error(message: str) -> None:
    raise RuntimeError(message)


def test_logging_setup_is_idempotent_across_reruns(tmp_path: Path) -> None:
    first = observability.configure_logging(log_dir=tmp_path)
    second = observability.configure_logging(log_dir=tmp_path)

    assert first is second
    assert (
        len([handler for handler in first.handlers if observability._managed(handler)])
        == EXPECTED_HANDLER_COUNT
    )

    first.info("test.single_line")
    assert _read_log(tmp_path).count("test.single_line") == 1


def test_log_level_uses_environment_and_invalid_value_falls_back(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(observability.LOG_LEVEL_ENV, "DEBUG")
    logger = observability.configure_logging(log_dir=tmp_path)
    assert logger.level == logging.DEBUG

    _reset_logging()
    monkeypatch.setenv(observability.LOG_LEVEL_ENV, "not-a-level")
    logger = observability.configure_logging(log_dir=tmp_path)
    assert logger.level == logging.INFO
    assert "logging.invalid_level" in _read_log(tmp_path)


def test_logging_redacts_secrets_and_omits_llm_content(tmp_path: Path, monkeypatch) -> None:
    secret = "sk-super-secret-value-123456789"  # noqa: S105 - synthetic redaction fixture
    prompt = "private transcript sentence that must never be logged"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    observability.configure_logging(log_dir=tmp_path)

    def fake_chat(model: str, system: str, user: str) -> str:
        assert model
        assert system
        assert user
        return "safe result"

    monkeypatch.setitem(llm._DISPATCH, "openai", fake_chat)

    llm.chat("system", prompt)
    observability.get_logger("test").warning("test.secret value=%s\ninjected", secret)
    try:
        _raise_private_error(prompt)
    except RuntimeError as exc:
        observability.log_failure(observability.get_logger("test"), "test.operation", exc)

    content = _read_log(tmp_path)
    assert secret not in content
    assert prompt not in content
    assert "[REDACTED]" in content
    assert "\\ninjected" in content
    assert "error_type=RuntimeError" in content
    assert "input_chars=" in content


def test_file_handler_rotates_at_configured_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(observability, "MAX_LOG_BYTES", 256)
    monkeypatch.setattr(observability, "BACKUP_COUNT", 1)
    logger = observability.configure_logging(log_dir=tmp_path)

    for index in range(20):
        logger.info("rotation.event index=%s padding=%s", index, "x" * 80)
    _read_log(tmp_path)

    assert (tmp_path / f"{observability.LOG_FILE_NAME}.1").is_file()


def test_unwritable_log_directory_keeps_console_logging_available(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("file", encoding="utf-8")

    logger = observability.configure_logging(log_dir=blocked)

    assert (
        len([handler for handler in logger.handlers if observability._managed(handler)])
        == EXPECTED_CONSOLE_HANDLER_COUNT
    )
