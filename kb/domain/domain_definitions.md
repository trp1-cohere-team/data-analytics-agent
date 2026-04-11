# Domain Definitions

## Purpose

Defines business terms that cannot be inferred directly from schema.

These definitions must override naive interpretations.

---

## Active Customer

Definition:
A customer who has made at least one purchase within the last 90 days.

Common Failure:
Using total customer table or existence as proxy.

Correct Usage:
Filter transactions by date before counting distinct customers.

---

## Repeat Purchase Rate

Definition:
Percentage of customers who made more than one purchase within a defined time window.

Formula:
(number of customers with >1 purchase) / (total customers in cohort)

Common Failure:
Using total purchase count instead of customer-level aggregation.

---

## Support Ticket Volume

Definition:
Number of valid support tickets recorded in CRM within a given period.

Notes:
- Exclude invalid or duplicate tickets
- May require filtering by status (e.g. "open", "resolved")

Common Failure:
Counting raw documents without filtering.

---

## Customer Segment

Definition:
Grouping of customers based on predefined attributes (e.g. region, plan type).

Constraint:
Must use existing segmentation field, not inferred grouping.

---

## Correlation (Operational Interpretation)

Definition:
Comparison of trends across two metrics over the same grouping and time window.

Important:
Unless explicitly computed, do NOT claim statistical correlation.
Use descriptive comparison instead.
