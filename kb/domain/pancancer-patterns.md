# PanCancer Atlas Query Patterns

Each pattern states the user intent, data sources, and computation path.
**Always COMPUTE in SQL — do not return raw rows.**

## Data sources

- `clinical_database` (Postgres) — `clinical_info` table: 100+ patient attributes.
  Key fields: `Patient_description` (text blob containing uuid, barcode, gender, vital_status, cancer_type),
  `acronym` (e.g. 'LGG', 'BRCA'), demographic and survival fields.
- `molecular_database` (SQLite):
  - `Mutation_Data` — per-mutation records with `ParticipantBarcode`, `Hugo_Symbol` (e.g. 'TP53', 'CDH1'),
    `Variant_Classification`, `HGVSp_Short`, `FILTER` (use `FILTER = 'PASS'` for reliable calls).
  - `RNASeq_Expression` — per-gene expression with `ParticipantBarcode`, `Symbol`, `normalized_count` (float).

## Joining across DBs

The two DBs are joined on patient identifier:
- `clinical_info.Patient_description` contains the barcode (extract via substring / ILIKE).
- `Mutation_Data.ParticipantBarcode` and `RNASeq_Expression.ParticipantBarcode` are the molecular keys.
Pattern: query clinical in Postgres to get the patient set, then query molecular in SQLite filtered
by those barcodes (pass barcodes as a list in an `IN (...)` clause).

## Cancer-type codes

`LGG` = Brain Lower Grade Glioma. `BRCA` = Breast Invasive Carcinoma.
Filter on `clinical_info.acronym = 'LGG'` (or 'BRCA' etc.).

## Pattern 1: average log10 expression by histology

- Intent: "average log10-transformed IGF2 expression across histological types for LGG patients"
- Formula: `AVG(LOG(normalized_count + 1) / LOG(10))` grouped by histology
- Source: `RNASeq_Expression` (SQLite) filtered to `Symbol='IGF2'`, joined to clinical patients where `acronym='LGG'`
- Output shape: `Histology_Type, Average_Log_Expression` — one row per histology type

## Pattern 2: percentage of a gene mutation within subgroups

- Intent: "top histological types by percentage of CDH1 mutations in living BRCA patients"
- Steps:
  1. In Postgres: select patients where `acronym='BRCA'` and vital_status='Alive' (check `Patient_description` text for "vital_status: Alive")
  2. In SQLite: for those ParticipantBarcodes, count mutations where `Hugo_Symbol='CDH1' AND FILTER='PASS'`
  3. Compute `mutation_percentage = 100.0 * mutations / total_patients` per histology
- Output shape: `Histological_Type, mutation_count, total, mutation_percentage`
- Use ORDER BY mutation_percentage DESC LIMIT 3 for "top three"

## Pattern 3: Chi-square for association between categorical fields

- Formula: `χ² = Σ (Oij - Eij)² / Eij` where `Eij = (row_total * col_total) / grand_total`
- Build a 2×N contingency table in SQL using CASE expressions, compute expected values, sum squared-differences.
- Output shape: single scalar `Chi2`
- Example: association between histological type (rows) and CDH1-mutation-present (cols) among female BRCA patients.

## Common mistakes

- Returning "Found N results" instead of the computed statistic.
- Forgetting to filter `Mutation_Data` by `FILTER='PASS'`.
- Mixing up `Hugo_Symbol` (mutation) with `Symbol` (expression) — they are in different tables.
- Not joining clinical→molecular on the correct patient identifier.
