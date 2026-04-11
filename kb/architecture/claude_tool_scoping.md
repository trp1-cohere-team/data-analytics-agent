# Claude Code — Tool Scoping Philosophy

Claude Code uses a large number of narrowly scoped tools instead of a few general-purpose tools.

## Core Idea

Each tool:
- performs one specific task
- has clearly defined inputs and outputs
- operates within a strict domain boundary

## Characteristics

- **High specialization**: Tools are optimized for specific operations
- **Low ambiguity**: Reduces incorrect tool usage
- **Composable**: Complex tasks are solved by chaining simple tools

## Why This Matters

General-purpose tools increase:
- ambiguity
- hallucination risk
- execution errors

Narrow tools improve:
- reliability
- interpretability
- debugging

## Application to Oracle Forge

Maps directly to MCP tools:

- separate tools for:
  - PostgreSQL queries
  - MongoDB queries
  - schema inspection
  - join-key normalization

Instead of:
“one tool that queries everything”

Use:
“many tools with strict responsibilities”

This improves:
- execution correctness
- traceability
- error isolation
