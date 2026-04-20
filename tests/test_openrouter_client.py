"""Tests for ordered OpenRouter API-key fallback."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from agent.data_agent import openrouter_client


class TestOpenRouterClient(unittest.TestCase):
    """Ensure OpenRouter chat requests fail over to the next configured key."""

    def test_post_chat_completions_falls_back_on_quota_status(self) -> None:
        first = Mock(status_code=429)
        first.raise_for_status.return_value = None

        second = Mock(status_code=200)
        second.raise_for_status.return_value = None
        second.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch.object(
            openrouter_client,
            "OPENROUTER_API_KEYS",
            ("first-key-123456", "second-key-654321"),
        ):
            with patch.object(openrouter_client.requests, "post", side_effect=[first, second]) as post_mock:
                result = openrouter_client.post_chat_completions(
                    messages=[{"role": "user", "content": "hello"}],
                    logger=Mock(),
                )

        self.assertEqual(result["choices"][0]["message"]["content"], "ok")
        self.assertEqual(post_mock.call_count, 2)
        first_headers = post_mock.call_args_list[0].kwargs["headers"]
        second_headers = post_mock.call_args_list[1].kwargs["headers"]
        self.assertIn("Bearer first-key-123456", first_headers["Authorization"])
        self.assertIn("Bearer second-key-654321", second_headers["Authorization"])

    def test_post_chat_completions_raises_when_no_keys_exist(self) -> None:
        with patch.object(openrouter_client, "OPENROUTER_API_KEYS", ()):
            with self.assertRaises(requests.RequestException):
                openrouter_client.post_chat_completions(
                    messages=[{"role": "user", "content": "hello"}],
                    logger=Mock(),
                )


if __name__ == "__main__":
    unittest.main()
