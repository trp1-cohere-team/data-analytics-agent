# Corrections Injection Tests

## Test C1
- Prompt: "What should happen after a query syntax error?"
- Expected answer: "Classify as `query`, log correction, retry with corrected tool call up to retry cap."

## Test C2
- Prompt: "How should Mongo nested-field mistakes be recorded?"
- Expected answer: "As a concrete correction entry with wrong field path and fixed field path."

## Test C3
- Prompt: "What is required in a useful correction entry?"
- Expected answer: "Error, category, applied fix, retry number, and outcome context."
