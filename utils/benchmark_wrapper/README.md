# Benchmark Wrapper

Wraps the team agent in a benchmark-friendly request/response shape.

## Purpose

Provides a stable adapter between:
- your internal agent interface
- benchmark input/output expectations

## Example

```python
from utils.benchmark_wrapper import wrap_agent_for_benchmark

response = wrap_agent_for_benchmark(
    agent_callable=my_agent,
    question="How many active customers do we have?",
    available_databases=["postgresql", "mongodb"],
    schema_info={"tables": ["customers", "tickets"]},
)
