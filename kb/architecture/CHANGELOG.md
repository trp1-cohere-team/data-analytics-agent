# KB / architecture — CHANGELOG

Documents in this directory describe the physical and logical architecture of
The Oracle Forge system: database schemas, MCP tool definitions, deployment
topology, and inter-component data flows.

---

## v1.0.0 — Initial injection (Week 8, Day 1)

**Documents added:**
- `schema_overview.md` — column-level schema for all 4 databases
- `mcp_toolbox.md` — MCP Toolbox endpoint definitions and tool signatures
- `deployment_topology.md` — Docker Compose stack, port map, DuckDB local path

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| "What tables are in PostgreSQL?" | orders, customers, products (+ others) | ✅ |
| "Which tool do I use for MongoDB?" | `mongo_aggregate` | ✅ |
| "Where is DuckDB hosted?" | Local file at `/home/data-analytics-agent/data/duckdb/main.duckdb` | ✅ |
| "What port does MCP Toolbox listen on?" | 5000 | ✅ |

**Injected by:** [TEAM MEMBER 1]
**Mob approval:** [DATE] — approved by team

---

## v1.1.0 — Schema refresh after data load (Week 8, Day 2)

**Documents updated:**
- `schema_overview.md` — added foreign key relationships discovered post-load

**Injection tests:**

| Query | Expected answer | Verified |
|-------|-----------------|---------|
| "How is orders linked to customers?" | Via `customer_id` foreign key | ✅ |
