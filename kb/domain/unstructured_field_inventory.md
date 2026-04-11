# Unstructured Field Inventory

## Purpose

Identifies fields requiring transformation before use.

---

## CRM Support Notes

Field:
- support_notes (MongoDB)

Type:
- free text

Required Extraction:
- sentiment (positive / negative / neutral)
- issue category (billing, product, service)
- urgency indicator

Common Failure:
Counting raw text entries instead of extracting structured signals.

---

## Customer Feedback

Field:
- review_text

Type:
- free text

Required Extraction:
- sentiment
- keywords (complaint vs praise)

---

## Product Description

Field:
- description

Type:
- semi-structured text

Usage:
- entity extraction (features, category)

---

## Rule

Text fields must NOT be:
- directly aggregated
- directly counted for semantic meaning

Always:
→ extract → structure → then aggregate
