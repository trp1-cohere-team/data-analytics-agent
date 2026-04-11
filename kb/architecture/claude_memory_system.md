# Claude Code — Three-Layer Memory System

Claude Code uses a structured three-layer memory architecture designed to balance recall, scalability, and efficiency.

## Layer 1 — Memory Index (MEMORY.md)
Acts as the entry point to all stored knowledge. It does not contain full information but instead references specific topic files. This prevents context overload and enables targeted retrieval.

## Layer 2 — Topic Files
Each topic file contains focused knowledge about a specific domain or system component (e.g., database schemas, tool usage patterns). These files are loaded selectively based on the task.

## Layer 3 — Session Transcripts
Records of past interactions, decisions, and outcomes. These provide historical context and enable the system to learn from prior executions.

## Key Principles

- **Selective loading**: Only relevant topic files are injected into context.
- **Separation of concerns**: Index (navigation), topics (knowledge), transcripts (experience).
- **Scalability**: Prevents context window overflow by avoiding full memory loading.

## Application to Oracle Forge

This maps directly to:
- KB index → navigation layer
- KB documents → domain and architecture knowledge
- corrections log → session memory

This structure enables efficient retrieval and continuous learning without overwhelming the model.
