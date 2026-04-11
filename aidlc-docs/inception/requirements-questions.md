# Requirements Clarification Questions
# The Oracle Forge — Data Analytics Agent

The challenge documents provide comprehensive requirements. The following questions clarify
implementation choices that will shape the architecture and code generation plan.

Please answer each question by filling in the letter choice after the [Answer]: tag.
Let me know when you are done.

---

## Question 1
What is the primary LLM backbone for the agent?

A) Claude API (Anthropic) — claude-sonnet-4-6 or claude-opus-4-6
B) Gemini CLI / Gemini API (Google) — as used in tenai-infra conductor
C) Both — Claude for intelligence, Gemini CLI as the conductor/orchestrator layer
D) Other (please describe after [Answer]: tag below)

[Answer]: D : we have openrouter which we can use multiple LLM but we will use Openai chatgpt4.0 as primary LLM

---

## Question 2
What is the primary programming language for the agent codebase?

A) Python — standard for data/ML work, best DAB ecosystem support
B) TypeScript/Node.js — mirrors Claude Code architecture studied in the challenge
C) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 3
Which database types should the agent support at minimum for the interim submission (April 15)?

A) PostgreSQL + SQLite (2 types — minimum "solid" requirement)
B) PostgreSQL + SQLite + MongoDB (3 types)
C) All four: PostgreSQL + SQLite + MongoDB + DuckDB (full DAB coverage)
D) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question 4
How should the agent be deployed for the shared server / live demo?

A) FastAPI HTTP server (Python) — REST interface, easy to integrate with MCP
B) CLI-based agent with a simple web UI wrapper (Streamlit or Gradio)
C) MCP server that Claude Code or Gemini CLI connects to directly
D) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 5
For the evaluation harness, what scoring approach should be used?

A) Exact match + partial credit (as defined in DAB paper: pass@1 with fuzzy numeric tolerance)
B) LLM-as-judge scoring (a second LLM call evaluates the answer quality)
C) Both — exact match primary, LLM-as-judge for ambiguous cases
D) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question 6
For the three mandatory context layers, which storage backend should be used for interaction memory (Layer 3)?

A) SQLite file (simple, portable, no external dependency)
B) JSON files (MEMORY.md pattern from Claude Code architecture)
C) Redis (fast in-memory, good for session state)
D) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question 7
What is the team's current infrastructure status?

A) tenai-infra server is running and accessible via Tailscale
B) No shared server yet — agent will run locally for now
C) Using a cloud VM (AWS/GCP/Azure) but not tenai-infra
D) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question 8
Which DAB datasets should be prioritised first for the agent's knowledge base (KB v2)?

A) Yelp dataset (recommended starting point per manual — multi-source, nested JSON)
B) Finance/retail datasets (most business-relevant)
C) Whatever datasets have the most queries in DAB (maximum benchmark coverage)
D) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question: Security Extensions
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)
B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)
X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question: Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)
B) Partial — enforce PBT rules only for pure functions and serialization round-trips
C) No — skip all PBT rules (suitable for simple CRUD or thin integration layers)
X) Other (please describe after [Answer]: tag below)

[Answer]: A
