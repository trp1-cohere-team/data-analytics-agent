# Domain Injection Tests

## Test D1
- Prompt: "How should the agent handle ETF and exchange filters for stockmarket questions?"
- Expected answer: "Filter in SQLite `stockinfo`, then compute price metrics in DuckDB."

## Test D2
- Prompt: "Why can a direct join between SQLite and DuckDB fail?"
- Expected answer: "They are separate backends; resolve symbol universe first, then run per-symbol DuckDB queries."

## Test D3
- Prompt: "What is a safe join key strategy for this benchmark?"
- Expected answer: "Use canonical symbol/entity IDs and explicit normalization from glossary rules."
