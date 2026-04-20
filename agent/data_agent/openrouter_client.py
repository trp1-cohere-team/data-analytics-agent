"""Shared chat-completions client with OpenAI/OpenRouter support."""

from __future__ import annotations

import logging

import requests

from agent.data_agent.config import (
    AGENT_MAX_TOKENS,
    AGENT_TEMPERATURE,
    AGENT_TIMEOUT_SECONDS,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENROUTER_API_KEYS,
    OPENROUTER_APP_NAME,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)

_FALLBACK_STATUSES = {401, 402, 403, 429}


def _mask_key(api_key: str) -> str:
    if len(api_key) <= 10:
        return "***"
    return f"{api_key[:12]}...{api_key[-4:]}"


def post_chat_completions(
    messages: list[dict[str, str]],
    logger: logging.Logger,
) -> dict:
    """Call chat completions using configured provider (OpenAI/OpenRouter)."""
    provider = _resolve_provider()
    if provider == "openai":
        try:
            return _post_openai_chat_completions(messages)
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in _FALLBACK_STATUSES and OPENROUTER_API_KEYS:
                logger.warning(
                    "openrouter_client: OpenAI returned HTTP %s; falling back to OpenRouter",
                    status,
                )
                return _post_openrouter_chat_completions(messages, logger)
            raise
    if provider == "openrouter":
        return _post_openrouter_chat_completions(messages, logger)
    raise requests.RequestException(
        "No LLM API key configured. Set OPENAI_API_KEY/openai_api_key or OPENROUTER_API_KEY."
    )


def _resolve_provider() -> str:
    provider = (LLM_PROVIDER or "auto").strip().lower()
    if provider in {"openai", "openrouter"}:
        return provider
    if OPENAI_API_KEY:
        return "openai"
    if OPENROUTER_API_KEYS:
        return "openrouter"
    return "none"


def _post_openai_chat_completions(messages: list[dict[str, str]]) -> dict:
    if not OPENAI_API_KEY:
        raise requests.RequestException("No OpenAI API key configured")
    resp = requests.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": messages,
            "max_tokens": AGENT_MAX_TOKENS,
            "temperature": AGENT_TEMPERATURE,
        },
        timeout=AGENT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _post_openrouter_chat_completions(
    messages: list[dict[str, str]],
    logger: logging.Logger,
) -> dict:
    if not OPENROUTER_API_KEYS:
        raise requests.RequestException("No OpenRouter API key configured")

    last_error: requests.RequestException | None = None

    for index, api_key in enumerate(OPENROUTER_API_KEYS):
        try:
            resp = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": OPENROUTER_APP_NAME,
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": messages,
                    "max_tokens": AGENT_MAX_TOKENS,
                    "temperature": AGENT_TEMPERATURE,
                },
                timeout=AGENT_TIMEOUT_SECONDS,
            )
            if resp.status_code in _FALLBACK_STATUSES and index + 1 < len(OPENROUTER_API_KEYS):
                logger.warning(
                    "openrouter_client: key %s returned HTTP %s; trying next configured key",
                    _mask_key(api_key),
                    resp.status_code,
                )
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            raise
        except requests.RequestException as exc:
            last_error = exc
            break

    if last_error is not None:
        raise last_error
    raise requests.RequestException("OpenRouter request failed without a response")
