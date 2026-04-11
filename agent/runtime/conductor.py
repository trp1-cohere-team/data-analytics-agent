from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agent.data_agent.context_layering import LayeredContext, build_layered_context
from agent.data_agent.dab_heuristics import (
    build_specialized_plan,
    synthesize_specialized_answer,
)
from agent.data_agent.execution_planner import (
    build_heuristic_plan,
    build_model_plan,
)
from agent.data_agent.knowledge_base import KnowledgeLayers
from agent.data_agent.knowledge_base import append_correction_entry
from agent.data_agent.mcp_toolbox_client import MCPToolboxClient
from agent.data_agent.openrouter_client import OpenRouterClient
from agent.data_agent.sandbox_client import SandboxClient
from agent.data_agent.result_synthesizer import (
    summarize_without_model,
    synthesize_with_model,
)
from agent.data_agent.router import suggest_database_routes
from agent.data_agent.types import AgentRequest, AgentResponse, QueryTraceEvent

from .events import EventStore
from .memory import MemoryManager
from .routing import filter_schema_info, select_databases_for_routes
from .tooling import ToolPolicy, ToolRegistry
from .worker import QueryWorker


class OracleForgeConductor:
    """Coordinates planning, tool execution, synthesis, and persistence."""

    def __init__(
        self,
        *,
        client: OpenRouterClient,
        mcp_client: MCPToolboxClient,
        memory_manager: MemoryManager,
        event_store: EventStore,
        tool_policy: ToolPolicy,
        config: Any,
    ) -> None:
        self.client = client
        self.mcp_client = mcp_client
        self.memory_manager = memory_manager
        self.event_store = event_store
        self.tool_policy = tool_policy
        self.config = config
        sandbox_client: SandboxClient | None = None
        if bool(getattr(config, "use_sandbox", False)):
            sandbox_client = SandboxClient(
                base_url=str(getattr(config, "sandbox_url", "http://localhost:8080")),
                timeout_seconds=int(getattr(config, "sandbox_timeout_seconds", 12)),
            )
        self.worker = QueryWorker(
            mcp_client=mcp_client,
            tool_policy=tool_policy,
            client=client,
            sandbox_client=sandbox_client,
            use_sandbox=bool(getattr(config, "use_sandbox", False)),
            self_correction_retries=max(
                0, int(getattr(config, "self_correction_retries", 1))
            ),
            duckdb_path=str(getattr(config, "duckdb_path", "./data/duckdb/main.duckdb")),
        )
        self._cached_tool_names: list[str] | None = None

    def run(self, request: AgentRequest, kb_layers: KnowledgeLayers) -> AgentResponse:
        session_id = self.memory_manager.ensure_session(
            getattr(self.config, "session_id", None)
        )
        topic_key = self.memory_manager.derive_topic_key(
            request.question,
            request.available_databases,
        )
        memory_context = self.memory_manager.build_context(session_id, topic_key)

        trace: list[QueryTraceEvent] = []
        self._emit_trace(
            trace,
            session_id=session_id,
            stage="input_received",
            detail="Captured question and context payload.",
        )

        routes = suggest_database_routes(request.question, request.available_databases)
        self._emit_trace(
            trace,
            session_id=session_id,
            stage="route_planning",
            detail=f"Proposed routes: {routes}",
            tool="router",
            payload={"routes": routes},
        )
        planned_databases = select_databases_for_routes(
            routes=routes,
            available_databases=request.available_databases,
        )
        planned_schema_info = filter_schema_info(
            schema_info=request.schema_info,
            selected_databases=planned_databases,
        )
        self._emit_trace(
            trace,
            session_id=session_id,
            stage="route_selection",
            detail=(
                "Selected databases for planning/execution: "
                f"{[str(db.get('name', 'unknown_db')) for db in planned_databases]}"
            ),
            tool="router",
            payload={
                "selected_databases": [
                    str(db.get("name", "unknown_db")) for db in planned_databases
                ]
            },
        )

        available_tools = self._discover_tools(trace, session_id)
        self._emit_trace(
            trace,
            session_id=session_id,
            stage="context_layer_schema_loaded",
            detail="Loaded table usage context layer.",
            tool="context_layering",
            payload={"sources": ["request.available_databases", "request.schema_info"]},
        )
        layered_context = build_layered_context(
            question=request.question,
            available_databases=request.available_databases,
            schema_info=request.schema_info,
            memory_context_text=memory_context.render(),
            kb_layers=kb_layers,
            routes=routes,
            selected_databases=planned_databases,
            available_tools=available_tools,
            session_id=session_id,
            mcp_enabled=bool(getattr(self.config, "use_mcp", False)),
            offline_mode=bool(getattr(self.config, "offline_mode", True)),
        )

        if layered_context.human_annotations:
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="context_layer_human_annotations_loaded",
                detail="Loaded human annotations layer.",
                tool="knowledge_base",
                payload={"sources": layered_context.source_map.get("human_annotations", [])},
            )

        if layered_context.codex_enrichment:
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="context_layer_codex_enrichment_loaded",
                detail="Loaded codex enrichment layer.",
                tool="knowledge_base",
                payload={"sources": layered_context.source_map.get("codex_enrichment", [])},
            )

        if layered_context.institutional_knowledge:
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="context_layer_institutional_loaded",
                detail="Loaded institutional knowledge layer.",
                tool="knowledge_base",
                payload={
                    "sources": layered_context.source_map.get("institutional_knowledge", [])
                },
            )

        if layered_context.source_map.get("agent_context"):
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="agent_context_loaded",
                detail="Loaded AGENT.md operating context at session start.",
                tool="agent_context",
                payload={"sources": layered_context.source_map.get("agent_context", [])},
            )

        if layered_context.interaction_memory:
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="context_layer_interaction_loaded",
                detail="Loaded interaction memory layer with session and corrections memory.",
                tool="memory_manager",
                payload={
                    "sources": (
                        layered_context.source_map.get("corrections", [])
                        + ["runtime_memory:index/topic/session"]
                    )
                },
            )

        if layered_context.runtime_context:
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="context_layer_runtime_loaded",
                detail="Loaded runtime context layer with tool, routing, and session signals.",
                tool="context_layering",
                payload={"sources": layered_context.source_map.get("runtime_context", [])},
            )

        registry = ToolRegistry(available_tools)

        plan = self._build_plan(
            request=request,
            planned_databases=planned_databases,
            planned_schema_info=planned_schema_info,
            registry=registry,
            layered_context=layered_context,
            trace=trace,
            session_id=session_id,
        )

        execution_records = self._execute_plan(
            request=request,
            plan=plan,
            registry=registry,
            trace=trace,
            session_id=session_id,
        )

        answer, confidence = self._synthesize_answer(
            request=request,
            execution_records=execution_records,
            layered_context=layered_context,
            trace=trace,
            session_id=session_id,
        )

        response = AgentResponse(
            answer=answer,
            query_trace=[asdict(event) for event in trace],
            confidence=confidence,
        )

        self.memory_manager.record_turn(
            session_id=session_id,
            topic_key=topic_key,
            question=request.question,
            answer=answer,
            confidence=confidence,
            execution_records=execution_records,
            trace=response.query_trace,
        )

        self._emit_trace(
            trace,
            session_id=session_id,
            stage="memory_updated",
            detail="Persisted index/topic/session memory for this turn.",
            tool="memory_manager",
        )

        response.query_trace = [asdict(event) for event in trace]
        return response

    def _discover_tools(
        self,
        trace: list[QueryTraceEvent],
        session_id: str,
    ) -> list[str]:
        if self._cached_tool_names is not None:
            return self._cached_tool_names

        if not getattr(self.config, "use_mcp", False):
            self._cached_tool_names = []
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="mcp_disabled",
                detail="AGENT_USE_MCP disabled; skipping toolbox discovery.",
                tool="mcp_toolbox",
                success=False,
            )
            return []

        try:
            tools = self.mcp_client.list_tools()
            self._cached_tool_names = tools
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="mcp_tools_discovered",
                detail=f"Discovered {len(tools)} tools from toolbox.",
                tool="mcp_toolbox",
                payload={"tools": tools},
            )
            return tools
        except Exception as exc:  # noqa: BLE001
            self._cached_tool_names = []
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="mcp_discovery_error",
                detail=f"Tool discovery failed: {exc}",
                tool="mcp_toolbox",
                success=False,
            )
            return []

    def _build_plan(
        self,
        *,
        request: AgentRequest,
        planned_databases: list[dict[str, Any]],
        planned_schema_info: dict[str, Any],
        registry: ToolRegistry,
        layered_context: LayeredContext,
        trace: list[QueryTraceEvent],
        session_id: str,
    ) -> list[dict[str, Any]]:
        specialized = build_specialized_plan(
            question=request.question,
            available_databases=planned_databases,
        )
        if specialized:
            bounded = specialized[: int(getattr(self.config, "max_execution_steps", 6))]
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="execution_plan",
                detail=f"Using specialized DAB plan with {len(bounded)} steps.",
                tool="planner",
            )
            return bounded

        model_plan = build_model_plan(
            client=self.client,
            question=request.question,
            available_databases=planned_databases,
            schema_info=planned_schema_info,
            available_tools=registry.names,
            context_layers=layered_context.to_prompt_payload(),
            extra_context=layered_context.render(),
        )
        if model_plan:
            selected = self._normalize_plan_tools(model_plan, registry)
            bounded = selected[: int(getattr(self.config, "max_execution_steps", 6))]
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="execution_plan",
                detail=f"Using model-generated plan with {len(bounded)} steps.",
                tool="planner",
            )
            return bounded

        heuristic = build_heuristic_plan(
            question=request.question,
            available_databases=planned_databases,
            schema_info=planned_schema_info,
            available_tools=registry.names,
        )
        selected = self._normalize_plan_tools(heuristic, registry)
        bounded = selected[: int(getattr(self.config, "max_execution_steps", 6))]
        self._emit_trace(
            trace,
            session_id=session_id,
            stage="execution_plan",
            detail=f"Using heuristic plan with {len(bounded)} steps.",
            tool="planner",
        )
        return bounded

    def _normalize_plan_tools(
        self,
        plan: list[dict[str, Any]],
        registry: ToolRegistry,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for step in plan:
            copy_step = dict(step)
            resolved_tool = registry.resolve_for_step(copy_step) or str(
                copy_step.get("tool", "")
            )
            copy_step["tool"] = resolved_tool
            normalized.append(copy_step)
        return normalized

    def _execute_plan(
        self,
        *,
        request: AgentRequest,
        plan: list[dict[str, Any]],
        registry: ToolRegistry,
        trace: list[QueryTraceEvent],
        session_id: str,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        steps_to_execute = list(plan)
        if not getattr(self.config, "use_mcp", False) or not registry.names:
            steps_to_execute = [
                step
                for step in plan
                if self.worker.can_execute_without_mcp(step=step, registry=registry)
            ]
            if not steps_to_execute:
                detail = "No executable MCP tool set available."
                self._emit_trace(
                    trace,
                    session_id=session_id,
                    stage="mcp_execution_skipped",
                    detail=detail,
                    tool="mcp_toolbox",
                    success=False,
                )
                self._record_correction(
                    query=request.question,
                    step={"tool": "none", "db_type": "unknown", "input": {}},
                    what_failed=detail,
                    category="database-type",
                    fix_applied="Configure MCP toolbox and database tools before execution.",
                    post_fix_outcome="failed",
                )
                return records

            self._emit_trace(
                trace,
                session_id=session_id,
                stage="mcp_execution_partial",
                detail=(
                    "MCP unavailable; executing local-compatible steps only "
                    f"({len(steps_to_execute)}/{len(plan)})."
                ),
                tool="mcp_toolbox",
            )

        for step in steps_to_execute:
            record = self.worker.execute_step(
                question=request.question,
                step=step,
                registry=registry,
                emit_trace=lambda **kwargs: self._emit_trace(
                    trace, session_id=session_id, **kwargs
                ),
                record_correction=self._record_correction,
            )
            records.append(record)

        return records

    def _synthesize_answer(
        self,
        *,
        request: AgentRequest,
        execution_records: list[dict[str, Any]],
        layered_context: LayeredContext,
        trace: list[QueryTraceEvent],
        session_id: str,
    ) -> tuple[str, float]:
        specialized = synthesize_specialized_answer(
            question=request.question,
            execution_records=execution_records,
        )
        if specialized:
            answer = str(specialized.get("answer", "No answer generated."))
            confidence = self._clamp_confidence(specialized.get("confidence", 0.95))
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="answer_synthesized",
                detail="Synthesized final answer with specialized DAB logic.",
                tool="dab_heuristics",
            )
            return answer, confidence

        synthesized = synthesize_with_model(
            client=self.client,
            question=request.question,
            execution_records=execution_records,
            context_layers=layered_context.to_prompt_payload(),
            additional_context=layered_context.render(),
        )

        if synthesized:
            answer = str(synthesized.get("answer", "No answer generated."))
            confidence = self._clamp_confidence(synthesized.get("confidence", 0.35))
            self._emit_trace(
                trace,
                session_id=session_id,
                stage="answer_synthesized",
                detail="Synthesized final answer with model.",
                tool="openrouter",
            )
            return answer, confidence

        answer = summarize_without_model(execution_records, request.question)
        confidence = 0.22 if execution_records else 0.1
        self._emit_trace(
            trace,
            session_id=session_id,
            stage="answer_synthesized",
            detail="Synthesized final answer with local fallback summarizer.",
            tool="result_synthesizer",
        )
        return answer, confidence

    def _record_correction(
        self,
        *,
        query: str,
        step: dict[str, Any],
        what_failed: str,
        category: str,
        fix_applied: str,
        post_fix_outcome: str,
    ) -> None:
        try:
            append_correction_entry(
                query=query,
                failed_step=step,
                what_failed=what_failed,
                root_cause_category=category,
                fix_applied=fix_applied,
                post_fix_outcome=post_fix_outcome,
                path=str(
                    getattr(
                        self.config,
                        "corrections_log_path",
                        "kb/corrections/corrections_log.md",
                    )
                ),
            )
        except Exception:
            # Never fail the user request because correction logging failed.
            return

    def _emit_trace(
        self,
        trace: list[QueryTraceEvent],
        *,
        session_id: str,
        stage: str,
        detail: str,
        tool: str | None = None,
        success: bool = True,
        payload: dict[str, Any] | None = None,
    ) -> None:
        trace.append(
            QueryTraceEvent(
                stage=stage,
                detail=detail,
                success=success,
                tool=tool,
            )
        )
        status = "ok" if success else "error"
        self.event_store.append_event(
            session_id=session_id,
            stage=stage,
            status=status,
            detail=detail,
            tool=tool,
            payload=payload,
        )

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = 0.25
        return max(0.0, min(1.0, num))
