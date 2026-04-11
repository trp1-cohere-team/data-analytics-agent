"""Unit tests for CodeSandbox (U6).

Tests run without any external services — subprocess only.
"""
from __future__ import annotations

import pytest
from agent.execution.sandbox import CodeSandbox


@pytest.fixture
def sandbox() -> CodeSandbox:
    return CodeSandbox(timeout=5.0)


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

def test_simple_computation(sandbox):
    result = sandbox.execute(code="result = 1 + 2", variables={})
    assert result.is_success
    assert result.result == 3
    assert result.error is None


def test_variables_injected(sandbox):
    result = sandbox.execute(
        code="result = [x for x in data if x > 5]",
        variables={"data": [3, 7, 2, 9]},
    )
    assert result.is_success
    assert result.result == [7, 9]


def test_named_variables_dict(sandbox):
    result = sandbox.execute(
        code="result = {'sum': a + b, 'product': a * b}",
        variables={"a": 4, "b": 6},
    )
    assert result.is_success
    assert result.result == {"sum": 10, "product": 24}


def test_stdout_captured(sandbox):
    result = sandbox.execute(
        code="print('hello world')\nresult = 42",
        variables={},
    )
    assert result.is_success
    assert result.result == 42
    assert "hello world" in result.stdout


def test_whitelisted_imports_json(sandbox):
    result = sandbox.execute(
        code='import json\nresult = json.loads(\'{"key": "value"}\')',
        variables={},
    )
    assert result.is_success
    assert result.result == {"key": "value"}


def test_whitelisted_imports_re(sandbox):
    result = sandbox.execute(
        code='import re\nresult = re.findall(r"\\d+", text)',
        variables={"text": "abc 123 def 456"},
    )
    assert result.is_success
    assert result.result == ["123", "456"]


def test_whitelisted_imports_math(sandbox):
    result = sandbox.execute(
        code="import math\nresult = math.floor(3.7)",
        variables={},
    )
    assert result.is_success
    assert result.result == 3


def test_whitelisted_imports_collections(sandbox):
    result = sandbox.execute(
        code="import collections\nc = collections.Counter(items)\nresult = dict(c)",
        variables={"items": ["a", "b", "a", "c", "a"]},
    )
    assert result.is_success
    assert result.result["a"] == 3


def test_result_none_when_not_assigned(sandbox):
    """No assignment to result is valid — returns None, not an error."""
    result = sandbox.execute(code="x = 5", variables={})
    assert result.is_success
    assert result.result is None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_syntax_error_in_code(sandbox):
    result = sandbox.execute(code="result = (1 +", variables={})
    assert not result.is_success
    assert result.error is not None
    assert "SyntaxError" in result.error or "RuntimeError" in result.error


def test_runtime_exception(sandbox):
    result = sandbox.execute(code="result = 1 / 0", variables={})
    assert not result.is_success
    assert "ZeroDivisionError" in result.error


def test_code_too_long_rejected(sandbox):
    long_code = "x = 1\n" * 1000  # well over 4096 chars
    result = sandbox.execute(code=long_code, variables={})
    assert not result.is_success
    assert "ValidationError" in result.error
    assert "4096" in result.error


def test_non_serialisable_variable_rejected(sandbox):
    result = sandbox.execute(code="result = 1", variables={"bad": object()})
    assert not result.is_success
    assert "ValidationError" in result.error


def test_timeout_enforced():
    slow_sandbox = CodeSandbox(timeout=1.0)
    # Infinite loop — no imports needed, triggers subprocess timeout
    result = slow_sandbox.execute(code="while True: pass", variables={})
    assert not result.is_success
    assert "TimeoutExpired" in result.error


def test_non_whitelisted_import_fails(sandbox):
    """requests is not in the whitelist — should fail at import."""
    result = sandbox.execute(code="import requests\nresult = 1", variables={})
    assert not result.is_success


# ---------------------------------------------------------------------------
# Session ID logging (smoke test — just ensures no exception)
# ---------------------------------------------------------------------------

def test_session_id_accepted(sandbox):
    result = sandbox.execute(code="result = 'ok'", variables={}, session_id="sess-001")
    assert result.is_success
    assert result.result == "ok"
