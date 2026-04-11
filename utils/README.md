
# 4. Root `utils/README.md`

# Shared Utility Library

This directory contains reusable modules maintained by Intelligence Officers for team-wide use.

## Modules

### 1. `join_key_resolver`
Normalizes mismatched entity identifiers across systems before comparison or join.

### 2. `schema_introspection`
Converts raw schema metadata into a normalized structure for planner and KB use.

### 3. `benchmark_wrapper`
Wraps the team agent in a benchmark-friendly request/response format.

## Design Principles

- small and reusable
- documented
- testable
- directly useful to Drivers and evaluation workflows
