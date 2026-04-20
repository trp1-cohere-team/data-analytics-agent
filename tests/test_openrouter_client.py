"""Tests for chat-completions provider routing and fallback."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from agent.data_agent import openrouter_client


class TestOpenRouterClient(unittest.TestCase):
    """Ensure provider selection and OpenRouter key-fallback behavior."""

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
            with patch.object(openrouter_client, "OPENAI_API_KEY", ""):
                with patch.object(openrouter_client, "LLM_PROVIDER", "openrouter"):
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
            with patch.object(openrouter_client, "OPENAI_API_KEY", ""):
                with patch.object(openrouter_client, "LLM_PROVIDER", "auto"):
                    with self.assertRaises(requests.RequestException):
                        openrouter_client.post_chat_completions(
                            messages=[{"role": "user", "content": "hello"}],
                            logger=Mock(),
                        )

    def test_post_chat_completions_prefers_openai_when_auto_and_key_present(self) -> None:
        response = Mock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": "ok-openai"}}]}

        with patch.object(openrouter_client, "LLM_PROVIDER", "auto"):
            with patch.object(openrouter_client, "OPENAI_API_KEY", "openai-test-key"):
                with patch.object(openrouter_client, "OPENROUTER_API_KEYS", ("or-key-1",)):
                    with patch.object(openrouter_client.requests, "post", return_value=response) as post_mock:
                        result = openrouter_client.post_chat_completions(
                            messages=[{"role": "user", "content": "hello"}],
                            logger=Mock(),
                        )

        self.assertEqual(result["choices"][0]["message"]["content"], "ok-openai")
        self.assertEqual(post_mock.call_count, 1)
        called_url = post_mock.call_args.args[0]
        self.assertIn("/chat/completions", called_url)
        headers = post_mock.call_args.kwargs["headers"]
        self.assertIn("Bearer openai-test-key", headers["Authorization"])

    def test_post_chat_completions_falls_back_to_openrouter_when_openai_429(self) -> None:
        openai_response = Mock(status_code=429)
        openai_error = requests.HTTPError("429 too many requests")
        openai_error.response = openai_response

        openrouter_response = Mock(status_code=200)
        openrouter_response.raise_for_status.return_value = None
        openrouter_response.json.return_value = {"choices": [{"message": {"content": "ok-openrouter"}}]}

        with patch.object(openrouter_client, "LLM_PROVIDER", "openai"):
            with patch.object(openrouter_client, "OPENAI_API_KEY", "openai-test-key"):
                with patch.object(openrouter_client, "OPENROUTER_API_KEYS", ("or-key-1",)):
                    with patch.object(
                        openrouter_client,
                        "_post_openai_chat_completions",
                        side_effect=openai_error,
                    ) as openai_mock:
                        with patch.object(
                            openrouter_client,
                            "_post_openrouter_chat_completions",
                            return_value=openrouter_response.json(),
                        ) as openrouter_mock:
                            result = openrouter_client.post_chat_completions(
                                messages=[{"role": "user", "content": "hello"}],
                                logger=Mock(),
                            )

        self.assertEqual(result["choices"][0]["message"]["content"], "ok-openrouter")
        self.assertEqual(openai_mock.call_count, 1)
        self.assertEqual(openrouter_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
