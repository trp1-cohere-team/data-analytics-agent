# Knowledge Base Guide

This directory stores curated knowledge used by the agent at runtime.

## Subdirectories
- `architecture/`: System architecture notes, tool-scoping guidance, and architecture changelog.
- `domain/`: Domain hints, schema-specific notes, and join-key guidance.
- `evaluation/`: DAB format and scoring references used during benchmarking.
- `corrections/`: Self-correction playbooks, correction patterns, and correction logs.

## How It Is Used
- Retrieved during context-layer assembly to provide institutional and domain grounding before tool calls.
