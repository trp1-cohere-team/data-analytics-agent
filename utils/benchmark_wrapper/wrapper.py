
# 2. `utils/benchmark_wrapper/`

## `utils/benchmark_wrapper/wrapper.py`


from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class BenchmarkRequest:
    question: str
    available_databases: list[str] | None = None
    schema_info: dict[str, Any] | None = None


@dataclass
class BenchmarkResponse:
    answer: str
    query_trace: list[dict[str, Any]]
    confidence: float
    assumptions: list[str]
    data_sources_used: list[str]
    transformations_applied: list[str]


def wrap_agent_for_benchmark(
    agent_callable: Callable[..., dict[str, Any]],
    question: str,
    available_databases: list[str] | None = None,
    schema_info: dict[str, Any] | None = None,
) -> BenchmarkResponse:
    raw = agent_callable(
        question=question,
        available_databases=available_databases,
        schema_info=schema_info,
    )

    return BenchmarkResponse(
        answer=str(raw.get("answer", "")),
        query_trace=list(raw.get("query_trace", [])),
        confidence=float(raw.get("confidence", 0.0)),
        assumptions=list(raw.get("assumptions", [])),
        data_sources_used=list(raw.get("data_sources_used", [])),
        transformations_applied=list(raw.get("transformations_applied", [])),
    )


def to_serializable_dict(response: BenchmarkResponse) -> dict[str, Any]:
    return {
        "answer": response.answer,
        "query_trace": response.query_trace,
        "confidence": response.confidence,
        "assumptions": response.assumptions,
        "data_sources_used": response.data_sources_used,
        "transformations_applied": response.transformations_applied,
    }
