from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError


@dataclass(slots=True)
class SandboxExecutionResult:
    success: bool
    endpoint: str
    request_body: dict[str, Any]
    response: dict[str, Any] | None
    error: str | None = None


class SandboxClient:
    """HTTP client for externalized code-execution sandbox."""

    def __init__(self, base_url: str, timeout_seconds: int = 12) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def execute(self, payload: dict[str, Any]) -> SandboxExecutionResult:
        endpoint = "/execute"
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=url,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=data,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                parsed: dict[str, Any] = {}
                if raw.strip():
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        parsed = loaded
                validation_status = str(parsed.get("validation_status", "")).lower()
                if validation_status and validation_status != "passed":
                    return SandboxExecutionResult(
                        success=False,
                        endpoint=endpoint,
                        request_body=payload,
                        response=parsed,
                        error=str(parsed.get("error_if_any", "sandbox validation failed")),
                    )
                if parsed.get("error_if_any"):
                    return SandboxExecutionResult(
                        success=False,
                        endpoint=endpoint,
                        request_body=payload,
                        response=parsed,
                        error=str(parsed.get("error_if_any")),
                    )
                return SandboxExecutionResult(
                    success=True,
                    endpoint=endpoint,
                    request_body=payload,
                    response=parsed,
                )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return SandboxExecutionResult(
                success=False,
                endpoint=endpoint,
                request_body=payload,
                response=None,
                error=str(exc),
            )
