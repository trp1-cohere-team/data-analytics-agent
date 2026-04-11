"""Key-rotating OpenAI client wrapper.

Wraps openai.AsyncOpenAI to transparently rotate through multiple API keys
when one key is exhausted (HTTP 402) or rate-limited (HTTP 429 / RateLimitError).

Usage::

    from utils.key_rotator import KeyRotatingOpenAI

    client = KeyRotatingOpenAI(
        keys=["sk-or-...", "sk-or-..."],
        base_url="https://openrouter.ai/api/v1",
    )
    # Drop-in replacement for openai.AsyncOpenAI:
    response = await client.chat.completions.create(model=..., messages=...)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import openai

_logger = logging.getLogger("agent.key_rotator")


class _RotatingCompletions:
    """Proxy for client.chat.completions with key-rotation logic."""

    def __init__(self, rotator: "KeyRotatingOpenAI") -> None:
        self._rotator = rotator

    async def create(self, **kwargs: Any) -> Any:
        return await self._rotator._create_with_rotation(**kwargs)


class _RotatingChat:
    """Proxy for client.chat with .completions attribute."""

    def __init__(self, rotator: "KeyRotatingOpenAI") -> None:
        self.completions = _RotatingCompletions(rotator)


class KeyRotatingOpenAI:
    """Drop-in replacement for openai.AsyncOpenAI that rotates keys on exhaustion.

    Key rotation triggers on:
    - HTTP 402 (APIStatusError with status_code 402) — credit exhausted
    - openai.RateLimitError — quota exceeded

    All other exceptions propagate immediately.
    """

    def __init__(self, keys: list[str], base_url: str) -> None:
        if not keys:
            raise ValueError("KeyRotatingOpenAI requires at least one API key")
        self._keys = keys
        self._base_url = base_url
        self._current_idx = 0
        self._clients: list[openai.AsyncOpenAI] = [
            openai.AsyncOpenAI(api_key=k, base_url=base_url) for k in keys
        ]
        self.chat = _RotatingChat(self)

    def _current_client(self) -> openai.AsyncOpenAI:
        return self._clients[self._current_idx]

    def _rotate(self) -> bool:
        """Advance to the next key. Returns False if all keys are exhausted."""
        next_idx = self._current_idx + 1
        if next_idx >= len(self._clients):
            return False
        _logger.warning(
            "key_rotated",
            extra={
                "from_key_index": self._current_idx,
                "to_key_index": next_idx,
                "total_keys": len(self._clients),
            },
        )
        self._current_idx = next_idx
        return True

    async def _create_with_rotation(self, **kwargs: Any) -> Any:
        while True:
            try:
                response = await self._current_client().chat.completions.create(**kwargs)
                return response
            except openai.APIStatusError as exc:
                if exc.status_code == 402:  # payment required — credit exhausted
                    if self._rotate():
                        await asyncio.sleep(0.5)
                        continue
                    _logger.error("all_keys_exhausted — no more API keys to rotate to")
                raise
            except openai.RateLimitError:
                if self._rotate():
                    await asyncio.sleep(1.0)
                    continue
                raise
