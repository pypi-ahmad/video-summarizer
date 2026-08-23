"""Multi-provider LLM wrapper for the post-processing steps Adversal itself doesn't do.

Reads API keys/base URLs directly from the environment (never logged). On
this machine they're already set as system env vars; python-dotenv also
loads a local .env if present, but never overrides an already-set env var,
so other users can copy .env.example to .env on their own machine without
affecting this one.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from openai import OpenAI

import observability

load_dotenv(override=False)

EMBED_MODEL = "text-embedding-3-small"
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"

Provider = Literal["openai", "agnes", "gemini"]


@dataclass(frozen=True)
class LLMOption:
    label: str
    provider: Provider
    model: str


LLM_OPTIONS: dict[str, LLMOption] = {
    "openai-gpt-5.6-luna": LLMOption("OpenAI - GPT-5.6 Luna", "openai", "gpt-5.6-luna"),
    "agnes-2.5-flash": LLMOption("Agnes AI - Agnes 2.5 Flash", "agnes", "agnes-2.5-flash"),
    "gemini-3.5-flash-lite": LLMOption(
        "Google - Gemini 3.5 Flash Lite", "gemini", "gemini-3.5-flash-lite"
    ),
    "gemini-3.7-flash": LLMOption("Google - Gemini 3.7 Flash", "gemini", "gemini-3.7-flash"),
}
DEFAULT_LLM_OPTION = "openai-gpt-5.6-luna"

logger = observability.get_logger("llm")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        msg = f"{name} is not set. Copy .env.example to .env and fill it in."
        raise RuntimeError(msg)
    return value


def _openai_client() -> OpenAI:
    api_key = _require_env("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _agnes_client() -> OpenAI:
    return OpenAI(api_key=_require_env("AGNES_API_KEY"), base_url=AGNES_BASE_URL)


def _chat_openai(model: str, system: str, user: str) -> str:
    response = _openai_client().chat.completions.create(
        model=model,
        reasoning_effort="medium",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


def _chat_agnes(model: str, system: str, user: str) -> str:
    response = _agnes_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


def _chat_gemini(model: str, system: str, user: str) -> str:
    client = genai.Client(api_key=_require_env("GOOGLE_API_KEY"))
    response = client.models.generate_content(
        model=model,
        contents=user,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            thinking_config=genai_types.ThinkingConfig(
                thinking_level=genai_types.ThinkingLevel.MEDIUM
            ),
        ),
    )
    return response.text or ""


_DISPATCH = {"openai": _chat_openai, "agnes": _chat_agnes, "gemini": _chat_gemini}


def chat(system: str, user: str, option_key: str = DEFAULT_LLM_OPTION) -> str:
    option = LLM_OPTIONS[option_key]
    started = time.perf_counter()
    logger.info(
        "chat.started provider=%s model=%s input_chars=%s",
        option.provider,
        option.model,
        len(system) + len(user),
    )
    try:
        result = _DISPATCH[option.provider](option.model, system, user)
    except Exception as exc:
        observability.log_failure(
            logger,
            "chat",
            exc,
            provider=option.provider,
            model=option.model,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    logger.info(
        "chat.completed provider=%s model=%s output_chars=%s duration_ms=%s",
        option.provider,
        option.model,
        len(result),
        round((time.perf_counter() - started) * 1000),
    )
    return result


def embed(texts: list[str]) -> list[list[float]]:
    """Embeddings always use OpenAI - Agnes/Gemini weren't requested for this."""
    started = time.perf_counter()
    logger.info(
        "embed.started model=%s items=%s input_chars=%s",
        EMBED_MODEL,
        len(texts),
        sum(map(len, texts)),
    )
    try:
        response = _openai_client().embeddings.create(model=EMBED_MODEL, input=texts)
        embeddings = [item.embedding for item in response.data]
    except Exception as exc:
        observability.log_failure(
            logger,
            "embed",
            exc,
            model=EMBED_MODEL,
            items=len(texts),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise
    dimensions = len(embeddings[0]) if embeddings else 0
    logger.info(
        "embed.completed model=%s items=%s dimensions=%s duration_ms=%s",
        EMBED_MODEL,
        len(embeddings),
        dimensions,
        round((time.perf_counter() - started) * 1000),
    )
    return embeddings
