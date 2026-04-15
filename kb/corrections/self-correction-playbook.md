# Self-Correction Playbook

Execution loop behavior:

- On failed tool call, classify into one of 4 categories.
- Write append-only correction entry to `corrections_log.md`.
- Ask LLM for corrected tool call.
- Retry up to `AGENT_SELF_CORRECTION_RETRIES`.
- Emit correction and tool_result events for each retry.

Operator guidance:
- Keep correction entries specific and reproducible.
- Include what failed, why, and exact corrective action.
- Avoid generic wording when a schema/path-specific fix is known.
