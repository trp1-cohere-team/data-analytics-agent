# OpenAI Data Agent — Six-Layer Context Architecture

The OpenAI data agent uses a multi-layer context system to handle large-scale, real-world data environments.

## Six Context Layers

1. **Schema Layer**
   - Tables, columns, relationships
   - Structural understanding of data

2. **Metadata Layer**
   - Table descriptions, usage patterns
   - Signals about reliability and relevance

3. **Domain Knowledge Layer**
   - Business definitions (e.g., revenue, churn)
   - Industry-specific meanings

4. **Query History Layer**
   - Previously executed queries
   - Successful patterns

5. **User Interaction Layer**
   - User preferences
   - corrections and clarifications

6. **Execution Feedback Layer**
   - errors
   - validation results
   - retry patterns

## Key Insight

The bottleneck is not query generation — it is **context quality**.

## Application to Oracle Forge

Minimum required implementation:

- Schema layer → DB introspection
- Domain layer → KB (domain/)
- Interaction layer → corrections log
- Execution feedback → validation + retry loop

The system must:
- combine multiple context layers
- retrieve selectively
- update context based on outcomes

This enables reliable performance in complex, multi-database environments.
