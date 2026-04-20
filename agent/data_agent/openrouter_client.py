"""Shared OpenRouter chat-completions client with ordered API-key fallback."""

from __future__ import annotations

import logging

import requests

from agent.data_agent.config import (
    AGENT_MAX_TOKENS,
    AGENT_TEMPERATURE,
    AGENT_TIMEOUT_SECONDS,
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
    """Call OpenRouter chat completions using the first healthy configured key."""
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
