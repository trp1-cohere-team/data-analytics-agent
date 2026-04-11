# DAB Database Schema (Minimal Operational Spec)

## Purpose
Structured storage for:
- agent trajectories
- failure detection (DAB)
- corrections log
- query patterns

---

## 1. Tables

### 1.1 agent_runs
Stores each full agent execution

Fields:
- run_id (PK)
- query (text)
- timestamp
- final_output
- success (bool)

---

### 1.2 agent_steps
Stores step-by-step trajectory

Fields:
- step_id (PK)
- run_id (FK)
- step_index (int)
- thought (text)
- action (text)
- tool_name (nullable)
- tool_input (jsonb)
- tool_output (jsonb)
- observation (text)

---

### 1.3 failures (DAB core)
Stores detected failures

Fields:
- failure_id (PK)
- run_id (FK)
- step_index (int)
- error_type (enum: knowledge | reasoning | perception | execution)
- failure_description (text)
- detected_by (agent | validator | probe)

---

### 1.4 corrections_log (KB v3 feed)
Structured correction memory

Fields:
- correction_id (PK)
- query (text)
- failure_point (text)
- error_type (enum)
- root_cause (text)
- correct_approach (text)
- fix_strategy (text)
- confidence (float)

---

### 1.5 query_patterns
Reusable working patterns

Fields:
- pattern_id (PK)
- pattern_name
- description
- sql_template (text)
- success_rate (float)
- last_validated_at

---

### 1.6 schema_registry
Tracks schema knowledge

Fields:
- table_name
- column_name
- data_type
- known_issues (text)
- join_key_quality (good | inconsistent | broken)

---

---

## 2. Indexing Strategy

- agent_steps(run_id, step_index)
- failures(run_id)
- corrections_log(error_type)
- query_patterns(success_rate DESC)

---

## 3. Invariants

- Every failure MUST map to exactly one error_type
- Every correction MUST reference a real query
- No silent failures: all detected failures logged

---

## 4. DAB Integration

Diagnose → failures table  
Analyze → error_type + root_cause  
Backtrack → new agent_steps linked to same run_id

---

## 5. Injection Test

Prompt:
"Given a failed SQL query, log it into corrections_log with proper error classification."

Expected:
- correct error_type classification
- structured correction output
