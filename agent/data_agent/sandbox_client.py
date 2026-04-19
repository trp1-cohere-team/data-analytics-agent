"""HTTP client for the OracleForge sandbox execution server.

FR-10: Sends Python code to sandbox_server.py for isolated execution.
BR-U4-03: Only activated when AGENT_USE_SANDBOX=1.
BR-U4-04: Health-checks the server before sending any payload.
SEC-05: Validates code payload length before sending.
SEC-15: All HTTP calls have explicit error handling.
SEC-03: Structured logging throughout.
"""

from __future__ import annotations

import logging

import requests

from agent.data_agent.config import (
    SANDBOX_MAX_PAYLOAD_CHARS,
    SANDBOX_PY_TIMEOUT_SECONDS,
    SANDBOX_TIMEOUT_SECONDS,
    SANDBOX_URL,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SandboxClient
# ---------------------------------------------------------------------------


class SandboxClient:
    """HTTP client for the sandbox execution server.

    Only instantiated when ``AGENT_USE_SANDBOX=1`` (BR-U4-03).
    All public methods return plain dicts — never raise to callers.
    """

    def __init__(self) -> None:
        self._base_url = SANDBOX_URL.rstrip("/")
        self._timeout = SANDBOX_TIMEOUT_SECONDS
        self._py_timeout = SANDBOX_PY_TIMEOUT_SECONDS
        self._max_payload = SANDBOX_MAX_PAYLOAD_CHARS
        logger.info("SandboxClient init: url=%s", self._base_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check if the sandbox server is reachable and healthy.

        Returns
        -------
        bool
            ``True`` if the server responded with status ``"ok"``.
        """
        try:
            resp = requests.get(
                f"{self._base_url}/health",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            healthy = data.get("status") == "ok"
            if not healthy:
                logger.warning("SandboxClient.health_check: unexpected response: %s", data)
            return healthy
        except requests.Timeout:
            logger.warning("SandboxClient.health_check: timed out")
            return False
        except requests.RequestException as exc:
            logger.warning("SandboxClient.health_check: request failed: %s", exc)
            return False
        except Exception as exc:
            logger.warning("SandboxClient.health_check: unexpected error: %s", exc)
            return False

    def execute(self, code: str) -> dict:
        """Execute Python code in the sandbox.

        Parameters
        ----------
        code:
            Python source code string to execute.

        Returns
        -------
        dict
            ``{"success": bool, "output": str, "error": str}``

        Notes
        -----
        - BR-U4-04: Health-check is performed before sending the payload.
        - SEC-05: Payload length is validated before sending.
        - SEC-15: All errors return a safe error dict — never raises.
        """
        # SEC-05: input validation BEFORE health-check (avoid unnecessary network call)
        if not isinstance(code, str):
            logger.warning("SandboxClient.execute: code must be a string")
            return {"success": False, "output": "", "error": "invalid_payload_type"}

        if len(code) > self._max_payload:
            logger.warning(
                "SandboxClient.execute: payload too large (%d chars, max %d)",
                len(code),
                self._max_payload,
            )
            return {
                "success": False,
                "output": "",
                "error": f"payload_too_large (max {self._max_payload} chars)",
            }

        # BR-U4-04: health-check after input validation
        if not self.health_check():
            logger.warning("SandboxClient.execute: server unhealthy — aborting")
            return {"success": False, "output": "", "error": "sandbox_unavailable"}

        try:
            resp = requests.post(
                f"{self._base_url}/execute",
                json={"code": code, "timeout": self._py_timeout},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "SandboxClient.execute: success=%s output_len=%d",
                data.get("success"),
                len(str(data.get("output", ""))),
            )
            return {
                "success": bool(data.get("success", False)),
                "output": str(data.get("output", "")),
                "error": str(data.get("error", "")),
            }
        except requests.Timeout:
            logger.warning("SandboxClient.execute: request timed out")
            return {"success": False, "output": "", "error": "sandbox_request_timeout"}
        except requests.RequestException as exc:
            logger.warning("SandboxClient.execute: request failed: %s", exc)
            return {"success": False, "output": "", "error": "sandbox_request_failed"}
        except Exception as exc:
            logger.warning("SandboxClient.execute: unexpected error: %s", exc)
            return {"success": False, "output": "", "error": "sandbox_unexpected_error"}
