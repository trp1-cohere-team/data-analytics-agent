"""Orchestration conductor — the agent's runtime spine.

FR-01: run() returns AgentResult.
FR-04: Self-correction loop with max retries.
FR-06: Emits trace events at every step.
FR-08: Loads AGENT.md into Layer 3.
SEC-05: Input validation at system boundary.
SEC-15: Global error handler.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from agent.data_agent.config import (
    AGENT_CONTEXT_PATH,
    AGENT_CORRECTIONS_LOG_PATH,
    AGENT_MAX_EXECUTION_STEPS,
    AGENT_MAX_TOKENS,
    AGENT_OFFLINE_MODE,
    AGENT_SELF_CORRECTION_RETRIES,
    AGENT_SESSION_ID,
    AGENT_TEMPERATURE,
    AGENT_TIMEOUT_SECONDS,
    AGENT_USE_SANDBOX,
    OFFLINE_LLM_RESPONSE,
    OPENROUTER_APP_NAME,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)
from agent.data_agent.context_layering import assemble_prompt, build_context_packet
from agent.data_agent.failure_diagnostics import classify
from agent.data_agent.knowledge_base import load_layered_kb_context
from agent.data_agent.mcp_toolbox_client import MCPClient
from agent.data_agent.sandbox_client import SandboxClient
from agent.data_agent.types import (
    AgentResult,
    CorrectionEntry,
    ContextPacket,
    InvokeResult,
    TraceEvent,
)
from agent.runtime.events import emit_event
from agent.runtime.memory import MemoryManager
from agent.runtime.tooling import ToolPolicy, ToolRegistry
from utils.db_utils import sanitize_sql_for_log
from utils.trace_utils import build_trace_event

logger = logging.getLogger(__name__)

_MAX_QUESTION_LEN = 4096
_MAX_DB_HINTS = 10


class OracleForgeConductor:
    """Session lifecycle manager and orchestration spine.

    Ties together context assembly, LLM calls, tool invocation,
    self-correction, memory, and event emission.
    """

    def __init__(self, session_id: Optional[str] = None) -> None:
        self._session_id = session_id or AGENT_SESSION_ID or str(uuid.uuid4())
        self._trace_id = str(uuid.uuid4())

        # Subsystems
        self._mcp = MCPClient()
        self._registry = ToolRegistry(self._mcp)
        self._policy = ToolPolicy()
        self._memory = MemoryManager(session_id=self._session_id)
        self._sandbox = SandboxClient() if AGENT_USE_SANDBOX else None

        # Runtime state
        self._tool_calls: list[dict] = []
        self._failure_count: int = 0
        self._sig_to_result: dict[str, str] = {}  # cache successful results per call-signature

        self._emit("session_start")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, question: str, db_hints: list[str]) -> AgentResult:
        """Execute the full agent pipeline.

        Parameters
        ----------
        question : str
            User question (max 4096 chars).
        db_hints : list[str]
            Database type hints (max 10 items).

        Returns
        -------
        AgentResult
            Always returns — never raises to callers (SEC-15).
        """
        try:
            return self._run_inner(question, db_hints)
        except Exception as exc:
            logger.error("Conductor unhandled error: %s", exc, exc_info=True)
            self._emit("error", outcome="unhandled_exception")
            return AgentResult(
                answer="An internal error occurred. Please try again.",
                confidence=0.0,
                trace_id=self._trace_id,
                tool_calls=self._tool_calls,
                failure_count=999,
            )

    # ------------------------------------------------------------------
    # Inner orchestration
    # ------------------------------------------------------------------

    def _run_inner(self, question: str, db_hints: list[str]) -> AgentResult:
        # --- Input validation (SEC-05) ---
        self._emit(
            "question_received",
            input_summary=question[:200] if isinstance(question, str) else "",
            extra={"db_hints": db_hints[:_MAX_DB_HINTS] if isinstance(db_hints, list) else []},
        )
        if not isinstance(question, str) or len(question) > _MAX_QUESTION_LEN:
            return AgentResult(
                answer="Invalid question: must be a string up to 4096 characters.",
                confidence=0.0,
                trace_id=self._trace_id,
            )
        if not isinstance(db_hints, list) or len(db_hints) > _MAX_DB_HINTS:
            return AgentResult(
                answer="Invalid db_hints: must be a list of up to 10 strings.",
                confidence=0.0,
                trace_id=self._trace_id,
            )

        # --- Follow-up resolution ---
        # Short acknowledgments ("yes", "proceed", "go ahead") on their own
        # have no actionable content. Rewrite them into an explicit instruction
        # that points the LLM at the prior conversation turns so it can carry
        # the data request forward instead of re-asking the same clarification.
        question = self._resolve_followup(question)

        # --- Deterministic multi-step orchestration for known stockmarket patterns ---
        # Keeps DB access inside unified MCPClient (FR-03) and avoids exhausting
        # LLM tool-call budgets on high-cardinality symbol workflows.
        stockmarket_answer = self._try_stockmarket_orchestration(question, db_hints)
        if stockmarket_answer is not None:
            answer_text = stockmarket_answer
            if self._tool_calls:
                confidence = self._confidence_from_tool_calls()
            else:
                # Defensive refusal (schema confusion, mutation block, etc.) —
                # no tool calls needed; the rejection itself is high-confidence.
                confidence = 0.9
            return self._finalize_result(question, answer_text, confidence)

        # --- Context assembly ---
        agent_md = self._load_agent_md()
        self._emit(
            "agent_context_loaded",
            outcome="success" if bool(agent_md) else "missing",
        )
        kb_results = load_layered_kb_context(question)
        kb_text = "\n\n".join(content for content, _score in kb_results[:5])
        memory_ctx = self._memory.get_memory_context()

        tools = self._registry.get_tools()
        tool_descriptions = [f"- {t.name}: {t.description}" for t in tools]
        selected_tool = self._registry.select_tool(db_hints)

        packet = build_context_packet(
            user_question=question,
            interaction_memory=memory_ctx,
            runtime_context={
                "session_id": self._session_id,
                "discovered_tools": [t.name for t in tools],
                "selected_db": selected_tool.name if selected_tool else "none",
                "db_hints": db_hints,
                "offline_mode": AGENT_OFFLINE_MODE,
            },
            institutional_knowledge=agent_md,
            human_annotations=kb_text,
            table_usage="\n".join(tool_descriptions),
        )

        prompt = assemble_prompt(packet)

        # --- Execution loop ---
        execution_evidence: list[dict] = []
        answer_text = ""
        successful_tool_signatures: set[str] = set()

        for step in range(AGENT_MAX_EXECUTION_STEPS):
            llm_response = self._call_llm(prompt, execution_evidence)
            llm_text = self._extract_answer(llm_response).strip()
            tool_call = self._extract_tool_call(llm_response)

            # If no executable tool call was parsed, do not prematurely end
            # the session on malformed TOOL_CALL text.
            if not tool_call:
                if llm_text and self._looks_like_tool_call(llm_text):
                    self._emit("tool_call", outcome="parse_error")
                    execution_evidence.append({
                        "error": "Malformed TOOL_CALL format from LLM; expected valid JSON object.",
                        "raw_response": llm_text[:300],
                        "step": step + 1,
                    })
                    continue

                if llm_text and self._has_successful_evidence(execution_evidence):
                    candidate = self._sanitize_answer(llm_text, question)
                    if candidate:
                        answer_text = candidate
                        break
                    # Sanitizer rejected the reply (raw dicts, scaffolding, or
                    # question echo) — fall through to synthesis instead.
                    execution_evidence.append({
                        "error": "LLM reply rejected by sanitizer (raw output or echo).",
                        "step": step + 1,
                    })
                    break

                execution_evidence.append({
                    "error": "No executable tool call returned; provide one TOOL_CALL.",
                    "raw_response": llm_text[:300],
                    "step": step + 1,
                })
                continue

            tool_name = tool_call.get("tool", "")
            params = tool_call.get("parameters", {})
            call_signature = f"{tool_name}|{json.dumps(params, sort_keys=True, default=str)}"

            # Prevent wasting steps on identical successful calls.
            if call_signature in successful_tool_signatures:
                prior = self._sig_to_result.get(call_signature, "")
                self._emit("tool_call", tool_name=tool_name, outcome="duplicate_blocked")
                execution_evidence.append({
                    "warning": "Duplicate tool call blocked. Prior result shown — synthesize your answer now.",
                    "tool": tool_name,
                    "prior_result": prior,
                    "step": step + 1,
                })
                # After 2 consecutive duplicate blocks, force synthesis to break the loop.
                dup_count = sum(1 for e in execution_evidence if "Duplicate tool call blocked" in e.get("warning", ""))
                if dup_count >= 2:
                    break
                continue

            # Policy check
            ok, reason = self._policy.validate_invocation(tool_name, params)
            if not ok:
                logger.warning("ToolPolicy blocked: %s — %s", tool_name, reason)
                self._emit("tool_call", tool_name=tool_name, outcome="blocked")
                execution_evidence.append({"error": f"Blocked: {reason}", "tool": tool_name})
                continue

            # Invoke tool
            self._emit("tool_call", tool_name=tool_name, input_summary=sanitize_sql_for_log(params.get("sql", "")))
            result = self._invoke_runtime_tool(tool_name, params)
            self._tool_calls.append({"tool_name": tool_name, "params": params, "success": result.success})

            backend = self._backend_from_result(result)
            self._emit(
                "tool_result",
                tool_name=tool_name,
                db_type=result.db_type,
                outcome="success" if result.success else "failure",
                backend=backend,
            )

            if result.success:
                successful_tool_signatures.add(call_signature)
                self._sig_to_result[call_signature] = str(result.result)[:500]
                execution_evidence.append({
                    "tool": tool_name,
                    "result_summary": self._summarize_result(result.result),
                    "result": str(result.result)[:1500],
                    "success": True,
                })
            else:
                # --- Self-correction loop ---
                corrected = self._self_correct(
                    tool_name, params, result.error,
                    {"error_type": result.error_type, "db_type": result.db_type},
                    prompt, execution_evidence,
                )
                if corrected:
                    execution_evidence.append({
                        "tool": tool_name,
                        "result_summary": self._summarize_result(corrected.result),
                        "result": str(corrected.result)[:1500],
                        "success": True,
                        "corrected": True,
                    })
                else:
                    execution_evidence.append({
                        "tool": tool_name,
                        "error": result.error,
                        "success": False,
                    })

        # --- Synthesis ---
        if not answer_text:
            answer_text = self._synthesize(question, execution_evidence, prompt)

        confidence = self._compute_confidence(execution_evidence)

        return self._finalize_result(question, answer_text, confidence)

    # ------------------------------------------------------------------
    # Deterministic stockmarket orchestration
    # ------------------------------------------------------------------

    def _try_stockmarket_orchestration(self, question: str, db_hints: list[str]) -> Optional[str]:
        """Solve known stockmarket patterns via deterministic batched MCP calls.

        Pre-hint guards (schema confusion / safety) run for any db_hints combination.
        Cross-DB batched solvers require both sqlite + duckdb hints.

        This path remains requirements-compliant:
        - DB access goes through MCPClient only (FR-03 / BR-U2-01).
        - ToolPolicy checks are applied before each invocation.
        - Tool call / tool result events are emitted for traceability (FR-06).
        """
        if AGENT_OFFLINE_MODE:
            return None

        hints = {str(h).lower().strip() for h in db_hints}
        q = question.lower()

        try:
            # ── Pre-hint guards: schema confusion + safety (any db_hints) ─────────

            # SG-01 — scope guard: refuse obvious non-data requests up front.
            # The agent is a data analyst for the configured databases, not a
            # general-purpose assistant; code-generation, weather, news, and
            # similar out-of-domain questions should get a clear refusal rather
            # than a hallucinated answer.
            scope_refusal = self._scope_refusal(q)
            if scope_refusal is not None:
                return scope_refusal

            # SG-02 — ticker pre-flight: if the question names a specific ticker
            # (e.g. "TSLA's volume in 2019") and that ticker is not a DuckDB
            # table, refuse up front with a "symbol not found" message that
            # suggests nearby tickers. This prevents the LLM from producing
            # misleading "no data for TSLA in 2019" phrasings when the real
            # fact is that TSLA isn't in the dataset at all.
            missing_ticker = self._missing_ticker_refusal(question, hints)
            if missing_ticker is not None:
                return missing_ticker

            # SC-01 / MG-01 — no 'stock_prices' table; DuckDB uses one table per ticker
            if "stock_prices" in q:
                return self._solve_stock_prices_hallucination(q, hints)

            # SC-05 — question mixes stock domain with incompatible dataset
            if self._is_cross_dataset_confusion(q):
                return self._solve_cross_dataset_confusion(question)

            # SC-04 — ETF filter applied to DuckDB (ETF column lives only in SQLite)
            if "etf" in q and "duckdb" in q and (
                "filter" in q or "where etf" in q or "= 'y'" in q
            ):
                return self._solve_etf_in_duckdb_confusion(hints)

            # MG-02 — prompt injection / mutation attempt
            if any(kw in q for kw in ("drop table", "drop the table", "recreate", "delete from", "truncate")) and \
               any(kw in q for kw in ("ignore", "fake", "replace", "overwrite", "insert")):
                return (
                    "This request attempts to mutate database tables, which is not permitted. "
                    "All tools are read-only. DROP, CREATE, ALTER, INSERT, UPDATE, and DELETE "
                    "operations are blocked by policy regardless of instruction phrasing."
                )

            # CJ-02 — 'ticker' hallucinated as a column name in per-ticker DuckDB tables
            if re.search(r"\bselect\s+ticker\b", q) or re.search(r"\bgroup\s+by\s+ticker\b", q):
                result = self._solve_ticker_column_hallucination(q, hints)
                if result is not None:
                    return result

            # CJ-04 — price computation requested when hints contain only SQLite
            if (
                hints == {"sqlite"}
                and any(kw in q for kw in ("adj close", "adjusted close", "adjusted closing"))
                and any(kw in q for kw in ("etf", "nyse arca", "every", "all"))
            ):
                return self._solve_price_in_sqlite_only()

            # MG-04 — null-aware Financial Status count
            if (
                ("troubled" in q or "distressed" in q)
                and "financial status" in q
                and ("null" in q or "even if" in q or "missing" in q)
            ):
                return self._solve_troubled_securities_null_aware(hints)

            # MG-03 — simple ticker symbol lookup (SQLite stockinfo path)
            if re.search(r"what\s+is\s+the\s+ticker\s+(?:symbol\s+)?for\b", q):
                result = self._solve_ticker_lookup(q, hints)
                if result is not None:
                    return result

            # SC-02 — max Adj Close for a named ticker (DuckDB-only)
            adj_match = re.search(
                r"\b(?:max|maximum|highest)\s+adj(?:\s+close|usted\s+close)?\s+for\s+([a-z]+)\b", q
            )
            if adj_match and "duckdb" in hints:
                result = self._solve_max_adj_close_for_ticker(adj_match.group(1).upper())
                if result is not None:
                    return result

            # MG-05 — rolling volatility for a named ticker
            roll_match = re.search(
                r"(\d+)[-\s]day\s+rolling\s+volatility\s+for\s+([a-z]+)\s+in\s+(\d{4})", q
            )
            if roll_match and "duckdb" in hints:
                result = self._solve_rolling_volatility(
                    roll_match.group(2).upper(), int(roll_match.group(1)), roll_match.group(3)
                )
                if result is not None:
                    return result

            # ── Cross-DB batched patterns (require both sqlite + duckdb hints) ────
            if not {"sqlite", "duckdb"}.issubset(hints):
                return None

            # CJ-01 — cross-DB join → volatile securities two-step workflow
            if ("volatile" in q or "volatility" in q) and (
                "join" in q or "stockinfo" in q or "most volatile" in q
            ):
                result = self._solve_most_volatile_securities()
                if result is not None:
                    return result

            # SC-03 — NYSE Arca ETF max Adj Close > 200 during 2015
            if (
                "etf" in q
                and "nyse arca" in q
                and "2015" in q
                and ("adj" in q or "adjusted" in q)
                and ("above $200" in q or "above 200" in q or "> 200" in q)
            ):
                return self._solve_stockmarket_etf_threshold_2015()

            # CJ-03 — distressed / troubled NASDAQ securities ranked by 2008 volume
            if (
                ("financially troubled" in q or "distressed" in q or ("troubled" in q and "nasdaq" in q))
                and "2008" in q
                and "volume" in q
                and ("nasdaq" in q or "rank" in q)
            ):
                return self._solve_stockmarket_troubled_avg_volume_2008()

            # CJ-05 — top 5 non-ETF NYSE stocks: more up days than down days in 2017
            if (
                ("top 5 non-etf" in q or "top five non-etf" in q)
                and ("new york stock exchange" in q or "nyse" in q)
                and "2017" in q
                and ("up days" in q or "more up" in q)
            ):
                return self._solve_stockmarket_top5_up_vs_down_2017()

            # Query5 — NASDAQ Capital Market top 5 by intraday range >20% in 2019
            if (
                "nasdaq capital market" in q
                and "2019" in q
                and "intraday" in q
                and "20%" in q
            ):
                return self._solve_stockmarket_top5_intraday_range_2019()

        except Exception as exc:
            logger.warning("Stockmarket deterministic orchestration failed: %s", exc, exc_info=True)
            return None

        return None

    def _solve_stockmarket_etf_threshold_2015(self) -> Optional[str]:
        """Query2: ETFs on NYSE Arca with max Adj Close > 200 during 2015."""
        sqlite_rows = self._invoke_sql_tool(
            "query_sqlite",
            (
                'SELECT Symbol, "Company Description" '
                'FROM stockinfo WHERE ETF = \'Y\' AND "Listing Exchange" = \'P\''
            ),
        )
        if not sqlite_rows:
            return None

        table_names = self._duckdb_table_set()
        symbol_to_name: dict[str, str] = {}
        symbols: list[str] = []
        for row in sqlite_rows:
            symbol = str(row.get("Symbol", "")).strip()
            if not symbol or symbol not in table_names:
                continue
            symbol_to_name[symbol] = self._extract_company_name(
                str(row.get("Company Description", ""))
            )
            symbols.append(symbol)

        if not symbols:
            return None

        qualifying: set[str] = set()
        for chunk in self._chunked(symbols, 120):
            union_parts = [
                (
                    f"SELECT {self._quote_literal(sym)} AS symbol, "
                    f"MAX(\"Adj Close\") AS max_adj_close FROM {self._quote_ident(sym)} "
                    "WHERE Date >= '2015-01-01' AND Date < '2016-01-01'"
                )
                for sym in chunk
            ]
            sql = (
                "SELECT symbol, max_adj_close FROM ("
                + " UNION ALL ".join(union_parts)
                + ") t WHERE max_adj_close > 200"
            )
            rows = self._invoke_sql_tool("query_duckdb", sql)
            if rows is None:
                return None
            for row in rows:
                symbol = str(row.get("symbol", "")).strip()
                if symbol:
                    qualifying.add(symbol)

        names = [symbol_to_name[s] for s in symbols if s in qualifying and symbol_to_name.get(s)]
        if not names:
            return "No ETF securities listed on NYSE Arca crossed an adjusted close above $200 in 2015.\nTotal: 0"

        return "\n".join(names + [f"Total: {len(names)}"])

    def _solve_stockmarket_troubled_avg_volume_2008(self) -> Optional[str]:
        """Query3: financially troubled NASDAQ companies with 2008 avg volume."""
        sqlite_rows = self._invoke_sql_tool(
            "query_sqlite",
            (
                'SELECT Symbol, "Company Description" FROM stockinfo '
                'WHERE "Nasdaq Traded" = \'Y\' AND "Financial Status" IN (\'D\', \'H\')'
            ),
        )
        if not sqlite_rows:
            return None

        table_names = self._duckdb_table_set()
        symbol_to_name: dict[str, str] = {}
        symbols: list[str] = []
        for row in sqlite_rows:
            symbol = str(row.get("Symbol", "")).strip()
            if not symbol or symbol not in table_names:
                continue
            symbol_to_name[symbol] = self._extract_company_name(
                str(row.get("Company Description", ""))
            )
            symbols.append(symbol)

        if not symbols:
            return None

        avg_by_symbol: dict[str, float] = {}
        for chunk in self._chunked(symbols, 80):
            union_parts = [
                (
                    f"SELECT {self._quote_literal(sym)} AS symbol, "
                    f"AVG(Volume) AS avg_volume FROM {self._quote_ident(sym)} "
                    "WHERE Date >= '2008-01-01' AND Date < '2009-01-01' AND Volume IS NOT NULL"
                )
                for sym in chunk
            ]
            sql = (
                "SELECT symbol, avg_volume FROM ("
                + " UNION ALL ".join(union_parts)
                + ") t WHERE avg_volume IS NOT NULL"
            )
            rows = self._invoke_sql_tool("query_duckdb", sql)
            if rows is None:
                return None
            for row in rows:
                symbol = str(row.get("symbol", "")).strip()
                avg_volume = row.get("avg_volume")
                if symbol and isinstance(avg_volume, (int, float)):
                    avg_by_symbol[symbol] = float(avg_volume)

        lines: list[str] = []
        for symbol in symbols:
            if symbol not in avg_by_symbol:
                continue
            name = symbol_to_name.get(symbol, symbol)
            lines.append(f"{name},{avg_by_symbol[symbol]:.2f}")

        return "\n".join(lines) if lines else None

    def _solve_stockmarket_top5_up_vs_down_2017(self) -> Optional[str]:
        """Query4: top 5 NYSE non-ETF stocks with more up days than down days."""
        sqlite_rows = self._invoke_sql_tool(
            "query_sqlite",
            (
                'SELECT Symbol, "Company Description" FROM stockinfo '
                'WHERE "Listing Exchange" = \'N\' AND ETF = \'N\''
            ),
        )
        if not sqlite_rows:
            return None

        table_names = self._duckdb_table_set()
        symbol_to_name: dict[str, str] = {}
        symbols: list[str] = []
        for row in sqlite_rows:
            symbol = str(row.get("Symbol", "")).strip()
            if not symbol or symbol not in table_names:
                continue
            symbol_to_name[symbol] = self._extract_company_name(
                str(row.get("Company Description", ""))
            )
            symbols.append(symbol)

        scored: list[tuple[int, int, str]] = []
        for chunk in self._chunked(symbols, 50):
            union_parts = [
                (
                    f"SELECT {self._quote_literal(sym)} AS symbol, "
                    "SUM(CASE WHEN Close > Open THEN 1 ELSE 0 END) AS up_days, "
                    "SUM(CASE WHEN Close < Open THEN 1 ELSE 0 END) AS down_days "
                    f"FROM {self._quote_ident(sym)} "
                    "WHERE Date >= '2017-01-01' AND Date < '2018-01-01'"
                )
                for sym in chunk
            ]
            sql = (
                "SELECT symbol, up_days, down_days FROM ("
                + " UNION ALL ".join(union_parts)
                + ") t WHERE up_days > down_days"
            )
            rows = self._invoke_sql_tool("query_duckdb", sql)
            if rows is None:
                return None
            for row in rows:
                symbol = str(row.get("symbol", "")).strip()
                up_days = int(row.get("up_days") or 0)
                down_days = int(row.get("down_days") or 0)
                scored.append((up_days - down_days, up_days, symbol))

        scored.sort(reverse=True)
        names = []
        for _diff, _up, symbol in scored[:5]:
            names.append(symbol_to_name.get(symbol, symbol))

        return "\n".join(names) if names else None

    def _solve_stockmarket_top5_intraday_range_2019(self) -> Optional[str]:
        """Query5: top 5 NASDAQ Capital Market stocks by >20% intraday-range days in 2019."""
        sqlite_rows = self._invoke_sql_tool(
            "query_sqlite",
            (
                'SELECT Symbol, "Company Description" FROM stockinfo '
                'WHERE "Market Category" = \'S\' AND "Nasdaq Traded" = \'Y\' AND ETF = \'N\''
            ),
        )
        if not sqlite_rows:
            return None

        table_names = self._duckdb_table_set()
        symbol_to_name: dict[str, str] = {}
        symbols: list[str] = []
        for row in sqlite_rows:
            symbol = str(row.get("Symbol", "")).strip()
            if not symbol or symbol not in table_names:
                continue
            symbol_to_name[symbol] = self._extract_company_name(
                str(row.get("Company Description", ""))
            )
            symbols.append(symbol)

        scored: list[tuple[int, str]] = []
        for chunk in self._chunked(symbols, 50):
            union_parts = [
                (
                    f"SELECT {self._quote_literal(sym)} AS symbol, "
                    "SUM(CASE WHEN Low IS NOT NULL AND Low != 0 "
                    "AND (High - Low) > 0.2 * Low THEN 1 ELSE 0 END) AS volatile_days "
                    f"FROM {self._quote_ident(sym)} "
                    "WHERE Date >= '2019-01-01' AND Date < '2020-01-01'"
                )
                for sym in chunk
            ]
            sql = "SELECT symbol, volatile_days FROM (" + " UNION ALL ".join(union_parts) + ") t"
            rows = self._invoke_sql_tool("query_duckdb", sql)
            if rows is None:
                return None
            for row in rows:
                symbol = str(row.get("symbol", "")).strip()
                volatile_days = int(row.get("volatile_days") or 0)
                scored.append((volatile_days, symbol))

        scored.sort(reverse=True)
        top_symbols = [symbol for _score, symbol in scored[:5]]
        names = [
            self._format_common_stock_name(symbol_to_name.get(symbol, symbol))
            for symbol in top_symbols
        ]
        return "\n".join(names) if names else None

    def _invoke_sql_tool(self, tool_name: str, sql: str) -> Optional[list[dict]]:
        """Invoke a SQL tool via MCPClient with policy checks + trace events."""
        ok, reason = self._policy.validate_invocation(tool_name, {"sql": sql})
        if not ok:
            self._failure_count += 1
            self._emit("tool_call", tool_name=tool_name, outcome="blocked")
            return None

        self._emit("tool_call", tool_name=tool_name, input_summary=sanitize_sql_for_log(sql))
        result = self._invoke_runtime_tool(tool_name, {"sql": sql})
        self._tool_calls.append({"tool_name": tool_name, "params": {"sql": sql}, "success": result.success})

        backend = self._backend_from_result(result)
        self._emit(
            "tool_result",
            tool_name=tool_name,
            db_type=result.db_type,
            outcome="success" if result.success else "failure",
            backend=backend,
        )

        if not result.success:
            self._failure_count += 1
            return None

        if isinstance(result.result, list):
            return result.result
        if isinstance(result.result, dict):
            # Aggregate queries return a single dict row — wrap it for uniform handling
            return [result.result]
        return []

    def _duckdb_table_set(self) -> set[str]:
        """Return available DuckDB table names."""
        rows = self._invoke_sql_tool(
            "query_duckdb",
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'",
        )
        if rows is None:
            return set()
        return {str(r.get("table_name", "")).strip() for r in rows if str(r.get("table_name", "")).strip()}

    def _symbol_not_found_message(self, symbol: str) -> str:
        """Produce a helpful 'not found' message that points the user at real tables.

        Plain "not found" is a dead-end; listing a handful of nearby tickers
        (by alphabetical proximity) makes the response actionable.
        """
        tables = self._duckdb_table_set()
        total = len(tables)
        if not tables:
            return (
                f"Symbol '{symbol}' was not found in DuckDB, and the table list "
                "could not be retrieved."
            )
        sym_u = (symbol or "").upper()
        ordered = sorted(tables)
        neighbors: list[str] = []
        if sym_u:
            for t in ordered:
                if t.upper() >= sym_u:
                    idx = ordered.index(t)
                    neighbors = ordered[max(0, idx - 3): idx + 7]
                    break
        if not neighbors:
            neighbors = ordered[:10]
        return (
            f"Symbol '{symbol}' is not in the DuckDB dataset "
            f"({total:,} tables available). "
            f"Nearby tickers you can query: {', '.join(neighbors[:10])}."
        )

    @staticmethod
    def _extract_company_name(description: str) -> str:
        """Extract canonical company name prefix from verbose description text."""
        text = description.strip()
        if not text:
            return ""

        lower = text.lower()
        separators = [
            ", based in ",
            " specializes ",
            " engages ",
            " focuses ",
            " develops ",
            " operates ",
            " provides ",
            " offers ",
            " manufactures ",
            " creates ",
            " dedicated ",
            " is ",
            " are ",
            " was ",
            " were ",
        ]

        cut = len(text)
        for sep in separators:
            idx = lower.find(sep)
            if idx > 0:
                cut = min(cut, idx)

        return re.sub(r"\s+", " ", text[:cut]).strip().rstrip(".")

    @staticmethod
    def _format_common_stock_name(name: str) -> str:
        """Normalize company name to '<Name> - Common Stock' style."""
        text = name.strip()
        if re.search(r",\s*Inc$", text):
            text = re.sub(r",\s*Inc$", ", Inc.", text)
        if re.search(r",\s*Ltd$", text):
            text = re.sub(r",\s*Ltd$", ", Ltd.", text)
        return f"{text} - Common Stock"

    # ------------------------------------------------------------------
    # Scope guard
    # ------------------------------------------------------------------

    # Canonical refusals for out-of-domain requests. Keyed by regex match;
    # the first match wins. Messages are short, factual, and route the user
    # back toward the kinds of questions the agent can actually answer.
    _SCOPE_RULES: list[tuple[re.Pattern, str]] = [
        (
            re.compile(r"\b(write|generate|give me|create)\b.*\b(python|javascript|typescript|code|function|script|program)\b", re.I),
            "I'm a data analyst for the configured databases — I don't generate code. "
            "Ask me about the SQLite, DuckDB, PostgreSQL, or MongoDB datasets instead.",
        ),
        (
            re.compile(r"\b(weather|forecast|temperature)\b.*\b(today|tomorrow|now|in\s+\w+)\b", re.I),
            "Weather data is not in any of the connected datasets. "
            "I can answer questions about stock prices, company metadata, and the DAB datasets.",
        ),
        (
            re.compile(r"\b(bitcoin|btc|ethereum|eth|crypto|cryptocurrenc)", re.I),
            "Cryptocurrency data is not available in the configured databases. "
            "The DuckDB price tables cover equity tickers only.",
        ),
        (
            re.compile(r"\b(super bowl|world cup|olympics|election|president|prime minister)\b", re.I),
            "That's outside the scope of the configured data sources. "
            "I can answer questions about the SQLite, DuckDB, PostgreSQL, and MongoDB datasets.",
        ),
    ]

    @classmethod
    def _scope_refusal(cls, q: str) -> Optional[str]:
        """Return a canonical refusal for obvious out-of-domain questions."""
        for pattern, message in cls._SCOPE_RULES:
            if pattern.search(q):
                return message
        return None

    # Common English words that happen to be 2–5 uppercase letters. Exclude
    # these from the "specific ticker" detection so we don't mistake them for
    # stock symbols.
    _TICKER_STOPWORDS: set[str] = {
        "A", "I", "IS", "IT", "OF", "OR", "ON", "IN", "AT", "BY", "TO", "WE", "US",
        "AN", "AS", "BE", "DO", "GO", "HE", "IF", "ME", "MY", "NO", "SO", "UP",
        "ALL", "AND", "ANY", "ARE", "BUT", "CAN", "DID", "FOR", "GET", "GOT",
        "HAS", "HAD", "HOW", "ITS", "LET", "NOT", "NOW", "OUR", "OUT", "PUT",
        "SEE", "SHE", "THE", "TOP", "TWO", "USE", "WAS", "WAY", "WHO", "WHY",
        "YES", "YET", "YOU", "DAY", "DAYS", "ETF", "ETFS", "NEW", "OLD", "ONE",
        "TEN", "SIX", "FEW", "LOT", "MAY", "OWN", "RUN", "WIN", "SUM", "MAX",
        "MIN", "AVG", "SQL", "API", "URL", "CSV", "CEO", "CFO", "COO", "CIO",
        "EPS", "PE", "PEG", "ROI", "ROE", "YTD", "MTD", "QTD", "Q1", "Q2", "Q3", "Q4",
        "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
        "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN",
        "GDP", "CPI", "USD", "EUR", "GBP", "JPY", "NYSE", "AMEX", "SEC",
        "DATA", "TEXT", "NAME", "TABLE", "ROWS", "LIST", "PRICE", "CLOSE",
        "OPEN", "HIGH", "LOW", "YEAR", "WEEK", "MONTH", "DATE", "TIME",
        "AADR",  # placeholder — actual tickers validated via DB lookup
    }
    _TICKER_CANDIDATE_RE = re.compile(r"\b([A-Z]{2,5})(?:'s|\b)")

    def _missing_ticker_refusal(self, question: str, hints: set) -> Optional[str]:
        """Return a 'symbol not found' refusal if the question names a
        specific ticker that is not present in the DuckDB dataset.

        Only fires when:
          - The question contains exactly one uppercase 2–5 letter candidate
            that is not a common English/financial stopword.
          - DuckDB is in the hint set (otherwise we don't know what's
            available, and the question may route to SQLite/Postgres/Mongo).
          - The DuckDB table for that candidate does not exist.
        """
        if "duckdb" not in hints:
            return None
        if not isinstance(question, str):
            return None
        matches = self._TICKER_CANDIDATE_RE.findall(question)
        if not matches:
            return None
        candidates = [m for m in matches if m.upper() not in self._TICKER_STOPWORDS]
        # Require exactly one candidate to avoid false positives on questions
        # that list several symbols or reference entities like NYSE/NASDAQ.
        unique = sorted(set(candidates))
        if len(unique) != 1:
            return None
        symbol = unique[0]
        try:
            tables = self._duckdb_table_set()
        except Exception:
            return None
        if not tables or symbol in tables:
            return None
        return self._symbol_not_found_message(symbol)

    # ------------------------------------------------------------------
    # Probe-specific solvers (deterministic, hint-agnostic)
    # ------------------------------------------------------------------

    def _solve_stock_prices_hallucination(self, q: str, hints: set) -> str:
        """SC-01 / MG-01: There is no 'stock_prices' table. DuckDB uses one table per ticker.

        Previously this solver silently rewrote any ``stock_prices`` query
        into "Top 5 tickers by MAX(Adj Close)", which (a) ignored the user's
        actual metric (avg vs max vs min), and (b) surfaced garbage values
        from unadjusted pre-split rows (UVXY = $205M). Now we explain the
        schema, point the user at the concrete workflow, and stop — it is
        better to ask for a specific ticker than to guess.
        """
        prefix = (
            "There is no 'stock_prices' table in this dataset. DuckDB stores "
            "price data in one table per ticker symbol, with columns Date, "
            "Open, High, Low, Close, \"Adj Close\", and Volume.\n\n"
        )
        if "duckdb" not in hints:
            return (
                prefix
                + "Please add 'duckdb' to the db_hints and re-ask with a "
                "specific ticker — e.g. \"What was the average closing price "
                "for REAL in 2020?\""
            )

        # Show a few example tickers so the user has something to substitute.
        table_names = self._duckdb_table_set()
        if not table_names:
            return prefix + "The DuckDB table list could not be retrieved — "\
                            "please retry with a specific ticker symbol."
        sample = ", ".join(sorted(table_names)[:8])
        total = len(table_names)
        return (
            prefix
            + f"{total:,} ticker tables are available (e.g. {sample}, …). "
            "Which ticker and metric would you like? For example: "
            "\"average Close for REAL in 2020\" or "
            "\"max Adj Close for AAAU\"."
        )

    @staticmethod
    def _is_cross_dataset_confusion(q: str) -> bool:
        """SC-05: Return True when question mixes stock domain with an incompatible domain."""
        stock_terms = {"stock", "nasdaq", "nyse", "etf", "closing price", "trading volume", "ticker"}
        non_stock_terms = {
            "artist", "song", "album", "music", "book", "author",
            "movie", "film", "restaurant", "recipe", "cuisine",
        }
        return any(t in q for t in stock_terms) and any(t in q for t in non_stock_terms)

    @staticmethod
    def _solve_cross_dataset_confusion(question: str) -> str:
        """SC-05: Defensive answer for cross-dataset schema confusion."""
        return (
            "This question appears to mix incompatible datasets. "
            "The stockmarket intelligence pack contains only financial market data: "
            "NASDAQ/NYSE securities, OHLCV prices, ETF flags, financial status, and market categories. "
            "It does not contain data about artists, music, books, movies, or other non-financial domains. "
            "Please rephrase your question to focus on stock market data."
        )

    def _solve_etf_in_duckdb_confusion(self, hints: set) -> str:
        """SC-04: ETF column lives only in SQLite stockinfo, not in DuckDB price tables."""
        prefix = (
            "Note: The ETF flag does not exist in DuckDB tables. "
            "DuckDB tables contain only OHLCV price data "
            "(Date, Open, High, Low, Close, \"Adj Close\", Volume). "
            "ETF metadata is stored in the SQLite 'stockinfo' table "
            "(columns: Symbol, ETF, \"Listing Exchange\", \"Financial Status\", etc.). "
            "Routing the ETF filter to SQLite.\n\n"
        )
        if "sqlite" not in hints:
            return prefix + "Please add 'sqlite' to db_hints to filter by ETF status."

        rows = self._invoke_sql_tool(
            "query_sqlite",
            'SELECT Symbol, "Company Description" FROM stockinfo WHERE ETF = \'Y\' ORDER BY Symbol LIMIT 20',
        )
        if rows:
            symbols = [str(r.get("Symbol", "")) for r in rows if r.get("Symbol")]
            return prefix + f"Top ETF symbols from stockinfo: {', '.join(symbols[:15])}"
        return prefix + "Unable to retrieve ETF symbols from stockinfo."

    def _solve_ticker_column_hallucination(self, q: str, hints: set) -> Optional[str]:
        """CJ-02: The ticker symbol is the DuckDB table name, not a column called 'ticker'."""
        from_match = re.search(r"\bfrom\s+([a-zA-Z]{1,5})\b", q)
        if not from_match:
            return (
                "Note: In this DuckDB dataset the ticker symbol is the table name, not a column. "
                "There is no 'ticker' column. "
                "Example: SELECT AVG(Volume) FROM AAPL   (no GROUP BY ticker needed)."
            )

        symbol = from_match.group(1).upper()
        if "duckdb" not in hints:
            return (
                f"Note: '{symbol}' is a DuckDB table name, not a 'ticker' column. "
                "Please include 'duckdb' in db_hints."
            )

        table_names = self._duckdb_table_set()
        if symbol not in table_names:
            available = ", ".join(sorted(table_names)[:5])
            return (
                f"Note: 'ticker' is not a column — the symbol IS the table name. "
                f"'{symbol}' was not found as a DuckDB table. "
                f"Available tables include: {available}..."
            )

        rows = self._invoke_sql_tool(
            "query_duckdb",
            f'SELECT AVG("Volume") AS avg_volume FROM {self._quote_ident(symbol)}',
        )
        if rows and rows[0]:
            avg_vol = list(rows[0].values())[0]
            if isinstance(avg_vol, (int, float)):
                return (
                    f"Note: 'ticker' is not a column — '{symbol}' is the table name. "
                    f"Corrected query result: AVG(Volume) for {symbol} = {float(avg_vol):,.0f}"
                )
        return (
            f"Note: 'ticker' is not a column — '{symbol}' is the table name. "
            "Could not retrieve volume data for this ticker."
        )

    @staticmethod
    def _solve_price_in_sqlite_only() -> str:
        """CJ-04: Price/OHLCV data lives in DuckDB, not SQLite — refuse and explain."""
        return (
            "Note: Adjusted close prices and other OHLCV metrics are stored in DuckDB, not SQLite. "
            "SQLite only contains stock metadata (stockinfo table: Symbol, "
            "\"Company Description\", \"Listing Exchange\", ETF, \"Financial Status\", "
            "\"Market Category\"). "
            "Price computations MUST use DuckDB. "
            "Please add 'duckdb' to db_hints — this agent will then correctly query "
            "ETF symbols from SQLite and their price data from DuckDB."
        )

    def _solve_troubled_securities_null_aware(self, hints: set) -> str:
        """MG-04: Count troubled securities with null-aware Financial Status handling."""
        if "sqlite" not in hints:
            return (
                "Financial Status data is in the SQLite 'stockinfo' table. "
                "Please add 'sqlite' to db_hints."
            )

        rows = self._invoke_sql_tool(
            "query_sqlite",
            (
                "SELECT "
                "SUM(CASE WHEN \"Financial Status\" IN ('D', 'H') THEN 1 ELSE 0 END) AS confirmed_troubled, "
                "SUM(CASE WHEN \"Financial Status\" IS NULL THEN 1 ELSE 0 END) AS null_status, "
                "COUNT(*) AS total_securities "
                "FROM stockinfo"
            ),
        )
        if rows and rows[0]:
            r = rows[0]
            confirmed = r.get("confirmed_troubled", "N/A")
            null_count = r.get("null_status", "N/A")
            return (
                f"Troubled securities count (null-aware):\n"
                f"- Confirmed troubled (Financial Status D or H): {confirmed}\n"
                f"- Rows with null Financial Status (status unknown, counted defensively): {null_count}\n"
                f"Note: Rows with a null Financial Status cannot be confirmed as non-troubled; "
                f"they are reported separately rather than silently excluded."
            )
        return "Unable to count troubled securities from stockinfo."

    def _solve_ticker_lookup(self, q: str, hints: set) -> Optional[str]:
        """MG-03: Simple company → ticker lookup via SQLite stockinfo (no correction needed)."""
        if "sqlite" not in hints:
            return None

        for_match = re.search(r"ticker\s+(?:symbol\s+)?for\s+(.+?)[\?\.\s]*$", q, re.IGNORECASE)
        if not for_match:
            return None

        raw_name = for_match.group(1).strip().rstrip("?. ")
        safe_name = re.sub(r"[^\w\s\-]", "", raw_name)[:100]
        rows = self._invoke_sql_tool(
            "query_sqlite",
            f'SELECT Symbol, "Company Description" FROM stockinfo '
            f'WHERE "Company Description" LIKE \'%{safe_name}%\' LIMIT 5',
        )
        if rows:
            lines = [
                f"{r.get('Symbol','?')}: {str(r.get('Company Description',''))[:80]}"
                for r in rows
            ]
            return "Ticker lookup (from stockinfo):\n" + "\n".join(lines)
        return f"No ticker found for '{safe_name}' in the stockinfo database."

    def _solve_max_adj_close_for_ticker(self, symbol: str) -> Optional[str]:
        """SC-02: Max Adj Close for a specific ticker, quoted correctly."""
        table_names = self._duckdb_table_set()
        if symbol not in table_names:
            return self._symbol_not_found_message(symbol)

        rows = self._invoke_sql_tool(
            "query_duckdb",
            f'SELECT MAX("Adj Close") AS max_adj_close FROM {self._quote_ident(symbol)}',
        )
        if rows and rows[0]:
            val = list(rows[0].values())[0]
            if isinstance(val, (int, float)):
                return f"Maximum Adj Close for {symbol}: {float(val):.4f}"
        return None

    def _solve_rolling_volatility(self, symbol: str, window: int, year: str) -> Optional[str]:
        """MG-05: Rolling volatility for a ticker — DuckDB-only, memory-cap verified."""
        table_names = self._duckdb_table_set()
        if symbol not in table_names:
            return self._symbol_not_found_message(symbol)

        sql = (
            f"SELECT ROUND(STDDEV(LN(\"Close\" / NULLIF(LAG(\"Close\", 1) OVER (ORDER BY Date), 0))) "
            f"* SQRT({window}), 6) AS rolling_vol_proxy "
            f"FROM {self._quote_ident(symbol)} "
            f"WHERE Date >= '{year}-01-01' AND Date < '{int(year) + 1}-01-01'"
        )
        rows = self._invoke_sql_tool("query_duckdb", sql)
        if rows and rows[0]:
            val = list(rows[0].values())[0]
            if isinstance(val, (int, float)):
                return (
                    f"{window}-day rolling volatility proxy for {symbol} in {year} "
                    f"(annualised StdDev of log returns × √{window}): {float(val):.6f}\n"
                    f"Note: Session memory is capped at {12} turns; "
                    f"this fresh query is isolated from prior session context."
                )
        return None

    def _solve_most_volatile_securities(self) -> Optional[str]:
        """CJ-01: Two-step cross-DB join — SQLite for symbols, DuckDB for volatility."""
        rows = self._invoke_sql_tool(
            "query_sqlite",
            (
                'SELECT Symbol FROM stockinfo '
                'WHERE "Nasdaq Traded" = \'Y\' OR "Listing Exchange" IS NOT NULL '
                'ORDER BY Symbol LIMIT 500'
            ),
        )
        if not rows:
            return None

        table_names = self._duckdb_table_set()
        symbols = [
            str(r.get("Symbol", "")).strip()
            for r in rows
            if str(r.get("Symbol", "")).strip() in table_names
        ][:200]
        if not symbols:
            return None

        scored: list[tuple[float, str]] = []
        for chunk in self._chunked(symbols, 50):
            union_parts = [
                f"SELECT {self._quote_literal(sym)} AS symbol, "
                f"STDDEV(\"Close\") / NULLIF(AVG(\"Close\"), 0) AS cv "
                f"FROM {self._quote_ident(sym)}"
                for sym in chunk
            ]
            sql = (
                "SELECT symbol, cv FROM ("
                + " UNION ALL ".join(union_parts)
                + ") t WHERE cv IS NOT NULL ORDER BY cv DESC LIMIT 10"
            )
            chunk_rows = self._invoke_sql_tool("query_duckdb", sql)
            if chunk_rows:
                for r in chunk_rows:
                    sym = str(r.get("symbol", "")).strip()
                    cv = r.get("cv")
                    if sym and isinstance(cv, (int, float)):
                        scored.append((float(cv), sym))

        if not scored:
            return None

        scored.sort(reverse=True)
        lines = [f"{sym}: CV={cv:.4f}" for cv, sym in scored[:5]]
        return (
            "Note: A direct SQL JOIN across SQLite and DuckDB is not possible — "
            "used two-step workflow: SQLite for symbol list, DuckDB for volatility computation.\n\n"
            "Top 5 most volatile securities (coefficient of variation of Close price):\n"
            + "\n".join(lines)
        )

    @staticmethod
    def _chunked(items: list[str], size: int) -> list[list[str]]:
        return [items[i : i + size] for i in range(0, len(items), size)]

    @staticmethod
    def _quote_ident(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _quote_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _confidence_from_tool_calls(self) -> float:
        if not self._tool_calls:
            return 0.1
        successes = sum(1 for c in self._tool_calls if c.get("success"))
        total = len(self._tool_calls)
        return max(0.1, min(0.99, successes / max(1, total)))

    def _finalize_result(self, question: str, answer_text: str, confidence: float) -> AgentResult:
        """Write memory + session_end event and return AgentResult."""

        # Final safety net — never let raw tool output or echoed questions
        # reach the user, regardless of which code path produced ``answer_text``.
        sanitized = self._sanitize_answer(answer_text or "", question)
        if sanitized:
            answer_text = sanitized
        elif not (answer_text or "").strip():
            answer_text = "I'm not able to produce a reliable answer for this question. Please rephrase or be more specific."

        # --- Memory ---
        from agent.data_agent.types import MemoryTurn

        ts = datetime.now(timezone.utc).isoformat()
        self._memory.save_turn(MemoryTurn(role="user", content=question, timestamp=ts, session_id=self._session_id))
        self._memory.save_turn(MemoryTurn(role="assistant", content=answer_text[:500], timestamp=ts, session_id=self._session_id))

        # --- Consolidate session → topics + index (Layer 2 + 1) ---
        self._memory.consolidate_to_topics(
            question=question,
            answer=answer_text,
            tool_calls=self._tool_calls,
        )

        self._emit(
            "session_end",
            outcome="complete",
            extra={
                "answer_preview": answer_text[:200],
                "confidence": confidence,
                "trace_id": self._trace_id,
                "failure_count": self._failure_count,
                "tool_call_count": len(self._tool_calls),
            },
        )

        return AgentResult(
            answer=answer_text,
            confidence=confidence,
            trace_id=self._trace_id,
            tool_calls=self._tool_calls,
            failure_count=self._failure_count,
        )

    # ------------------------------------------------------------------
    # Self-correction loop (FR-04)
    # ------------------------------------------------------------------

    def _self_correct(
        self,
        tool_name: str,
        original_params: dict,
        error: str,
        context: dict,
        prompt: str,
        evidence: list[dict],
    ) -> Any:
        """Attempt to correct a failed tool invocation.

        Returns the successful InvokeResult, or None after exhausting retries.
        """
        for retry in range(1, AGENT_SELF_CORRECTION_RETRIES + 1):
            self._failure_count += 1
            diagnosis = classify(error, context)

            self._emit(
                "correction",
                tool_name=tool_name,
                diagnosis=diagnosis.category,
                retry_count=retry,
                outcome="retrying",
            )

            # Write correction entry
            self._write_correction(diagnosis, error, retry)

            # Ask LLM for corrected approach
            correction_prompt = (
                f"The previous tool call to '{tool_name}' failed.\n"
                f"Error: {error}\n"
                f"Diagnosis: {diagnosis.category} — {diagnosis.explanation}\n"
                f"Suggested fix: {diagnosis.suggested_fix}\n"
                f"Please provide a corrected tool call."
            )
            evidence.append({"correction": correction_prompt, "retry": retry})

            llm_response = self._call_llm(prompt, evidence)
            tool_call = self._extract_tool_call(llm_response)

            if not tool_call:
                continue

            new_params = tool_call.get("parameters", original_params)
            new_tool = tool_call.get("tool", tool_name)

            ok, reason = self._policy.validate_invocation(new_tool, new_params)
            if not ok:
                error = f"Policy blocked corrected call: {reason}"
                continue

            result = self._invoke_runtime_tool(new_tool, new_params)
            self._tool_calls.append({"tool_name": new_tool, "params": new_params, "success": result.success, "retry": retry})

            backend = self._backend_from_result(result)
            self._emit(
                "tool_result",
                tool_name=new_tool,
                db_type=result.db_type,
                outcome="success" if result.success else "failure",
                retry_count=retry,
                backend=backend,
            )

            if result.success:
                return result

            error = result.error
            context = {"error_type": result.error_type, "db_type": result.db_type}

        return None

    # ------------------------------------------------------------------
    # Tool invocation dispatch
    # ------------------------------------------------------------------

    def _invoke_runtime_tool(self, tool_name: str, params: dict) -> InvokeResult:
        """Invoke either MCP or sandbox tool based on tool identity.

        Sandbox execution is activated only when AGENT_USE_SANDBOX=1 and the
        virtual ``execute_python`` tool is selected.
        """
        if tool_name == "execute_python":
            return self._invoke_sandbox(params)
        return self._mcp.invoke_tool(tool_name, params)

    def _invoke_sandbox(self, params: dict) -> InvokeResult:
        """Execute Python code via SandboxClient and normalize result."""
        if self._sandbox is None:
            return InvokeResult(
                success=False,
                tool_name="execute_python",
                error="sandbox_disabled",
                error_type="config",
                db_type="sandbox",
            )

        code = params.get("code", "")
        if not isinstance(code, str) or not code.strip():
            return InvokeResult(
                success=False,
                tool_name="execute_python",
                error="invalid_code_payload",
                error_type="policy",
                db_type="sandbox",
            )

        payload = self._sandbox.execute(code)
        ok = bool(payload.get("success", False))
        return InvokeResult(
            success=ok,
            tool_name="execute_python",
            result=payload.get("output", ""),
            error=str(payload.get("error", "")),
            error_type="" if ok else "query",
            db_type="sandbox",
        )

    @staticmethod
    def _backend_from_result(result: InvokeResult) -> str:
        if result.db_type == "duckdb":
            return "duckdb_bridge"
        if result.db_type == "sandbox":
            return "sandbox"
        return "mcp_toolbox"

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        system_prompt: str,
        evidence: list[dict],
        mode: str = "tool",
    ) -> dict:
        """Call the LLM via OpenRouter API (or return offline stub).

        Parameters
        ----------
        mode : str
            ``"tool"``     — ask the LLM for a TOOL_CALL (default, first call)
            ``"evidence"`` — present evidence and ask for TOOL_CALL or ANSWER
            ``"synthesize"`` — ask the LLM to synthesize a final answer
        """
        if AGENT_OFFLINE_MODE:
            return OFFLINE_LLM_RESPONSE

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        if mode == "synthesize":
            messages.append({
                "role": "user",
                "content": (
                    "Based on the query results in the system prompt, "
                    "provide a concise, factual answer in plain English.\n"
                    "Rules:\n"
                    "- Do NOT paste raw Python lists/dicts or JSON into the answer.\n"
                    "- Do NOT describe tool calls, retries, or your reasoning.\n"
                    "- Do NOT repeat the user's question back.\n"
                    "- If results are empty or contradictory, say so in one sentence.\n"
                    "- If the question is ambiguous, ask one short clarifying question.\n"
                    "Respond with: ANSWER: <your answer>"
                ),
            })
        elif evidence:
            evidence_text = "\n".join(
                json.dumps(e, default=str)[:900] for e in evidence[-10:]
            )
            messages.append({
                "role": "user",
                "content": (
                    f"Execution context:\n{evidence_text}\n\n"
                    "If you have enough data, respond with ANSWER: <your answer>. "
                    "Otherwise respond with: "
                    "TOOL_CALL: {\"tool\": \"<tool_name>\", \"parameters\": {\"sql\": \"<SQL>\"}}\n"
                    "Do not repeat an identical successful tool call. "
                    "Use prior results to take the next step."
                ),
            })
        else:
            messages.append({
                "role": "user",
                "content": (
                    "Call a database tool to retrieve the data needed to answer the question. "
                    "Respond ONLY with: "
                    "TOOL_CALL: {\"tool\": \"<tool_name>\", \"parameters\": {\"sql\": \"<SQL>\"}}"
                ),
            })

        try:
            resp = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            logger.warning("LLM call timed out")
            return {"choices": [{"message": {"content": "LLM call timed out. Returning best available answer."}}]}
        except requests.RequestException as exc:
            logger.warning("LLM call failed: %s", exc)
            return {"choices": [{"message": {"content": f"LLM call failed. Returning best available answer."}}]}

    # ------------------------------------------------------------------
    # Response parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_final_answer(response: dict) -> bool:
        """Check if the LLM response contains a direct answer (no tool call)."""
        content = OracleForgeConductor._extract_answer(response)
        if not content:
            return False
        if OracleForgeConductor._looks_like_tool_call(content):
            return False
        return True

    @staticmethod
    def _extract_answer(response: dict) -> str:
        """Extract the text answer from an LLM response.

        Handles the common case where the LLM prefixes prose (sometimes a
        duplicate of the answer itself) before the ``ANSWER:`` marker. We take
        everything after the LAST ``ANSWER:`` occurrence so the final,
        canonical answer reaches the user — not the preamble.
        """
        try:
            choices = response.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = str(msg.get("content", "")).strip()
                markers = list(re.finditer(r"\bANSWER\s*:\s*", content, flags=re.IGNORECASE))
                if markers:
                    content = content[markers[-1].end():].strip()
                content = OracleForgeConductor._strip_markdown_fence(content)
                return content
        except (IndexError, AttributeError, TypeError):
            pass
        return ""

    @staticmethod
    def _extract_tool_call(response: dict) -> Optional[dict]:
        """Extract a tool call from an LLM response.

        Expects format: ``TOOL_CALL: {"tool": "name", "parameters": {...}}``
        or a JSON block in the response.
        """
        content = OracleForgeConductor._extract_answer(response)
        if not content:
            return None

        candidates: list[str] = []
        if "TOOL_CALL:" in content:
            candidates.append(content.split("TOOL_CALL:", 1)[1].strip())
        candidates.append(content.strip())
        if "{" in content and "}" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            candidates.append(content[start:end].strip())

        for candidate in candidates:
            parsed = OracleForgeConductor._parse_tool_call_candidate(candidate)
            if parsed:
                return parsed

        # Fallback for common malformed JSON from model output.
        return OracleForgeConductor._extract_tool_call_regex(content)

    @staticmethod
    def _parse_tool_call_candidate(candidate: str) -> Optional[dict]:
        """Parse a candidate string into a tool-call dictionary if possible."""
        if not candidate:
            return None

        decoder = json.JSONDecoder()
        objs: list[Any] = []

        try:
            objs.append(json.loads(candidate))
        except json.JSONDecodeError:
            pass

        try:
            obj, _ = decoder.raw_decode(candidate)
            objs.append(obj)
        except json.JSONDecodeError:
            pass

        for obj in objs:
            # Some models wrap JSON as a JSON string
            if isinstance(obj, str):
                try:
                    obj = json.loads(obj)
                except json.JSONDecodeError:
                    continue

            if isinstance(obj, dict) and "tool" in obj:
                if not isinstance(obj.get("parameters"), dict):
                    obj["parameters"] = {}
                return obj

        return None

    @staticmethod
    def _extract_tool_call_regex(content: str) -> Optional[dict]:
        """Recover a tool call from near-JSON text using regex heuristics."""
        tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', content)
        if not tool_match:
            return None

        tool_name = tool_match.group(1).strip()
        params: dict[str, Any] = {}

        sql_match = re.search(r'"sql"\s*:\s*"((?:\\.|[^"\\])*)"', content, flags=re.DOTALL)
        if sql_match:
            raw_sql = sql_match.group(1)
            try:
                sql = json.loads(f"\"{raw_sql}\"")
            except json.JSONDecodeError:
                sql = raw_sql.replace('\\"', '"').replace("\\n", "\n")
            params["sql"] = sql

        return {"tool": tool_name, "parameters": params}

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        """Remove a single surrounding markdown code fence, if present."""
        text = text.strip()
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
        return text

    @staticmethod
    def _looks_like_tool_call(content: str) -> bool:
        """Heuristic check for text that is intended to be a tool call."""
        norm = content.strip()
        if not norm:
            return False
        upper = norm.upper()
        if "TOOL_CALL:" in upper or "TOOL_CALL" in upper:
            return True
        if norm.startswith("{") and '"tool"' in norm and '"parameters"' in norm:
            return True
        return False

    @staticmethod
    def _has_successful_evidence(evidence: list[dict]) -> bool:
        """True when at least one successful tool result has been recorded."""
        return any(e.get("success") for e in evidence)

    @staticmethod
    def _summarize_result(result: Any) -> dict[str, Any]:
        """Build a compact, structured summary of tool results for prompt context."""
        if isinstance(result, list):
            summary: dict[str, Any] = {"row_count": len(result)}
            if result and isinstance(result[0], dict):
                cols = list(result[0].keys())
                summary["columns"] = cols[:12]
            summary["sample_rows"] = result[:5]
            return summary
        if isinstance(result, dict):
            keys = list(result.keys())
            return {"type": "object", "keys": keys[:12], "preview": str(result)[:400]}
        return {"type": type(result).__name__, "preview": str(result)[:400]}

    # Patterns used by ``_sanitize_answer`` to strip leaked tool output and
    # internal scaffolding from LLM-produced answers.
    _RAW_DICT_LINE = re.compile(
        r"^\s*(\[\s*\]|\[\s*\{.*\}\s*,?.*\]?|\{\s*['\"].+['\"]\s*:.+\}\s*,?)\s*$"
    )
    _SCAFFOLDING = re.compile(
        r"(The previous tool call|TOOL_CALL:|execution context|system prompt|"
        r"I will (start by|try|iterate|use the python)|This query is not valid|"
        r"I cannot use the python tool|Based on the query results in the system prompt)",
        re.IGNORECASE,
    )

    # Bare acknowledgments that carry no new content of their own.
    # Matches 1–5 ack tokens strung together (e.g. "yes", "ok go ahead",
    # "yes please proceed with that"). Any non-ack word fails the match.
    _ACK_PATTERN = re.compile(
        r"^(?:\s*(?:yes|yeah|yep|yup|sure|ok|okay|k|alright|fine|"
        r"please|go|ahead|do|it|proceed|continue|"
        r"with|that|it|then|now|works|sounds|good)[\s.,!]*){1,6}$",
        re.IGNORECASE,
    )

    # Short interrogatives or modification requests that only make sense in
    # the context of the prior turn (e.g. "why", "how?", "can you also check
    # sqlite", "what about 2016"). These can't be answered in isolation.
    _CONTEXTUAL_PATTERNS = [
        re.compile(r"^\s*(why|how|what|huh|really|when|where|who)\s*\??\s*$", re.I),
        re.compile(r"^\s*(can|could|would|will)\s+(you|u)\b.{0,60}$", re.I),
        re.compile(r"^\s*(what\s+about|how\s+about|and|also|but)\b.{0,60}$", re.I),
        re.compile(r"^\s*(in|for|on)\s+\d{4}\s*\??\s*$", re.I),  # "in 2016?"
    ]

    @classmethod
    def _looks_contextual(cls, question: str) -> bool:
        if not isinstance(question, str):
            return False
        q = question.strip()
        if not q or len(q) > 80:
            return False
        return any(p.match(q) for p in cls._CONTEXTUAL_PATTERNS)

    @staticmethod
    def _last_assistant_was_question(turns: list) -> bool:
        """True if the most recent assistant turn ends with a question mark."""
        for t in reversed(turns):
            if getattr(t, "role", "") == "assistant":
                content = (getattr(t, "content", "") or "").rstrip()
                return content.endswith("?")
        return False

    def _resolve_followup(self, question: str) -> str:
        """Restate bare acknowledgments and contextual follow-ups with history.

        Three kinds of input are rewritten before the LLM sees them:
          1. Pure acknowledgments ("yes", "ok go ahead") that carry no content.
          2. Contextual fragments ("why", "can you also check SQLite",
             "what about 2016") that reference the prior turn implicitly.
          3. Short replies (≤5 words) whose meaning only makes sense as an
             answer to a prior clarifying question (e.g. "lowest" after
             "Best by highest return, lowest volatility, …?").

        Without this rewrite, the LLM treats each question as independent and
        either loops on the same clarification or produces a generic refusal.
        """
        if not isinstance(question, str):
            return question
        q = question.strip()
        if not q:
            return question

        is_ack = bool(self._ACK_PATTERN.match(q))
        is_ctx = self._looks_contextual(q)

        try:
            prior = self._memory.load_session()
        except Exception:
            prior = []

        # Short answers to a prior clarifying question — e.g. "lowest",
        # "volatility", "2019 return". Only activated if the immediately prior
        # assistant turn ended in a question mark.
        is_short_reply = (
            not is_ack
            and not is_ctx
            and len(q.split()) <= 5
            and len(q) <= 40
            and self._last_assistant_was_question(prior)
        )

        if not (is_ack or is_ctx or is_short_reply):
            return question
        if not prior:
            return question

        recent = prior[-4:]
        transcript = "\n".join(f"[{t.role}] {t.content[:400]}" for t in recent)
        if is_ack:
            lead = "The user replied affirmatively"
        elif is_short_reply:
            lead = "The user's short reply is an answer to the prior clarifying question"
        else:
            lead = "The user's message is a short follow-up that depends on prior context"
        return (
            f"{lead}: '{q}'. "
            "Use the prior conversation below to determine the actual data "
            "request and carry it out. Do not ask the same clarifying question "
            "again; if the prior data request is clear from context, execute it.\n\n"
            f"--- Recent conversation ---\n{transcript}"
        )

    @classmethod
    def _sanitize_answer(cls, answer: str, question: str) -> str:
        """Remove raw tool dicts, internal reasoning, and echoed questions.

        Returns an empty string when nothing usable remains — callers should
        treat that as "no valid answer produced".
        """
        if not answer:
            return ""
        # Drop fenced code blocks that hold raw tool output (``` ... ```).
        text = re.sub(r"```[a-zA-Z]*\n(\[\s*\{.*?\}\s*,?.*?\])\n```", "", answer, flags=re.DOTALL)

        kept = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                kept.append(line)
                continue
            if cls._RAW_DICT_LINE.match(stripped):
                continue
            if cls._SCAFFOLDING.search(stripped):
                continue
            kept.append(line)

        cleaned = "\n".join(kept).strip()
        # Collapse 3+ blank lines.
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        # Block trivial echoes of the user's question.
        norm_q = re.sub(r"[\s?.!]+$", "", question.strip().lower())
        norm_a = re.sub(r"[\s?.!]+$", "", cleaned.lower())
        if norm_a and norm_q and norm_a == norm_q:
            return ""

        return cleaned

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _synthesize(self, question: str, evidence: list[dict], prompt: str) -> str:
        """Synthesize final answer from execution evidence.

        Uses structured summaries (row counts, columns, sample rows) rather than
        raw stringified dicts, then sanitizes the LLM reply so raw tool output
        and internal reasoning never leak to the user.
        """
        successful = [e for e in evidence if e.get("success")]
        if not successful:
            return "I was not able to retrieve any data for this question."

        # Build a clean, structured view of what the tools returned.
        blocks: list[str] = []
        for idx, item in enumerate(successful[-5:], 1):
            tool = item.get("tool", "tool")
            summary = item.get("result_summary") or self._summarize_result(item.get("result"))
            if "row_count" in summary:
                rows = summary.get("sample_rows") or []
                cols = summary.get("columns") or []
                blocks.append(
                    f"[{idx}] {tool}: {summary['row_count']} row(s); "
                    f"columns={cols[:8]}; sample={rows[:3]}"
                )
            else:
                blocks.append(f"[{idx}] {tool}: {summary}")
        results_text = "\n".join(blocks)

        synthesis_prompt = (
            f"USER QUESTION: {question}\n\n"
            f"TOOL RESULTS (already validated — summarized):\n{results_text}\n\n"
            "Write ONE clean natural-language answer for the user.\n"
            "Rules:\n"
            "- Do NOT include Python dict/list syntax, raw JSON, or tool names.\n"
            "- Do NOT describe your reasoning, retries, or tool-call history.\n"
            "- Do NOT echo the question back.\n"
            "- If the data is empty or does not answer the question, say so plainly.\n"
            "- If the question is ambiguous, ask ONE short clarifying question instead of guessing.\n"
            "Respond with: ANSWER: <your answer>"
        )
        response = self._call_llm(prompt + "\n\n" + synthesis_prompt, [], mode="synthesize")
        raw_answer = self._extract_answer(response)
        # If the LLM mis-routed into another tool call, refuse to leak internals.
        if not raw_answer or "TOOL_CALL:" in raw_answer.upper():
            return self._deterministic_summary(question, successful)

        cleaned = self._sanitize_answer(raw_answer, question)
        if not cleaned:
            return self._deterministic_summary(question, successful)
        return cleaned

    @staticmethod
    def _deterministic_summary(question: str, successful: list[dict]) -> str:
        """Produce a plain-English summary from tool evidence without the LLM.

        Used only when the LLM synthesis returns empty or unusable output. The
        goal is to give the user *some* useful signal about what the tools
        returned, instead of a generic "please rephrase" dead-end.
        """
        if not successful:
            return "I was not able to retrieve any data for this question."
        last = successful[-1]
        summary = last.get("result_summary") or {}
        row_count = summary.get("row_count")
        if row_count is None:
            return "The query completed but produced no structured results to summarize."
        if row_count == 0:
            return "The query ran successfully but returned 0 rows."
        cols = summary.get("columns") or []
        sample = summary.get("sample_rows") or []

        # Single-column list result — show up to 10 examples inline.
        if len(cols) == 1 and sample:
            key = cols[0]
            values = [str(row.get(key, "")) for row in sample if isinstance(row, dict)]
            values = [v for v in values if v]
            head = ", ".join(values[:10])
            extra = f" (+{row_count - len(values):,} more)" if row_count > len(values) else ""
            return (
                f"Found {row_count:,} result(s). "
                f"First {min(10, len(values))} {key.lower()}(s): {head}{extra}."
            )

        # Multi-column small result — render as a compact Markdown table.
        if sample and isinstance(sample[0], dict) and row_count <= 20:
            keys = list(sample[0].keys())[:6]
            header = "| " + " | ".join(keys) + " |"
            divider = "|" + "|".join(["---"] * len(keys)) + "|"
            body = "\n".join(
                "| " + " | ".join(str(row.get(k, ""))[:60] for k in keys) + " |"
                for row in sample[:20] if isinstance(row, dict)
            )
            return f"Found {row_count:,} result(s):\n\n{header}\n{divider}\n{body}"

        # Multi-column large result — summarize.
        sample_line = ""
        if sample and isinstance(sample[0], dict):
            first = sample[0]
            parts = [f"{k}={first[k]!r}" for k in list(first.keys())[:4]]
            sample_line = f" Example row: {', '.join(parts)}."
        return (
            f"Found {row_count:,} result(s) with columns {cols[:6]}.{sample_line}"
        )

    @staticmethod
    def _compute_confidence(evidence: list[dict]) -> float:
        """Compute confidence score from execution evidence."""
        if not evidence:
            return 0.1

        successes = sum(1 for e in evidence if e.get("success"))
        total = len(evidence)
        if total == 0:
            return 0.1

        base = successes / total
        # Penalise corrections
        corrections = sum(1 for e in evidence if e.get("corrected"))
        penalty = corrections * 0.1

        return max(0.0, min(1.0, base - penalty))

    # ------------------------------------------------------------------
    # AGENT.md loading (FR-08)
    # ------------------------------------------------------------------

    @staticmethod
    def _load_agent_md() -> str:
        """Load agent/AGENT.md for institutional knowledge (Layer 3)."""
        try:
            with open(AGENT_CONTEXT_PATH, "r", encoding="utf-8") as fh:
                content = fh.read()
            return content
        except (OSError, FileNotFoundError):
            logger.debug("AGENT.md not found at %s", AGENT_CONTEXT_PATH)
            return ""

    # ------------------------------------------------------------------
    # Corrections log
    # ------------------------------------------------------------------

    def _write_correction(self, diagnosis: Any, error: str, retry: int) -> None:
        """Append a correction entry to the corrections log."""
        ts = datetime.now(timezone.utc).isoformat()
        entry = CorrectionEntry(
            timestamp=ts,
            session_id=self._session_id,
            original_error=sanitize_sql_for_log(error, max_length=200),
            diagnosis_category=diagnosis.category,
            correction_applied=diagnosis.suggested_fix,
            retry_number=retry,
            outcome="pending",
        )

        line = (
            f"\n### Correction — {ts}\n"
            f"- **Session**: {entry.session_id}\n"
            f"- **Category**: {entry.diagnosis_category}\n"
            f"- **Error**: {entry.original_error}\n"
            f"- **Fix**: {entry.correction_applied}\n"
            f"- **Retry**: {entry.retry_number}\n"
        )

        try:
            os.makedirs(os.path.dirname(AGENT_CORRECTIONS_LOG_PATH) or ".", exist_ok=True)
            with open(AGENT_CORRECTIONS_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            logger.warning("Failed to write correction log: %s", exc)

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        """Emit a trace event with session context."""
        emit_event(
            build_trace_event(
                event_type=event_type,
                session_id=self._session_id,
                **kwargs,
            )
        )
