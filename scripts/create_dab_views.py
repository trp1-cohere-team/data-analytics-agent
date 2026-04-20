"""Create views in SQLite, DuckDB, and Postgres that expose DAB's original
table names as views over our prefix-loaded tables.

Background: our load scripts wrote data under prefixed names (``crm_Lead``,
``bookreview_review``, ``agnews_authors``, etc.) but DAB's ``db_description.txt``
references the original unprefixed names (``Lead``, ``review``, ``authors``).
The agent writes ``SELECT ... FROM Lead`` per the description, so every query
fails until a matching view exists.

This script is idempotent: it drops and recreates views each run.

Collision note:
- SQLite ``review`` collides between ``bookreview_review`` and
  ``googlelocal_review``. We point the view at ``bookreview_review`` because
  bookreview was scoring 0%; googlelocal's own pass rate does not depend on
  the bare ``review`` view (its queries hit ``googlelocal_review`` through
  joins and prefix guessing, per the baseline run).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import duckdb
import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "data" / "sqlite" / "main.db"
DUCKDB_PATH = ROOT / "data" / "duckdb" / "main.duckdb"
PG_DSN = "postgresql://oracle_forge:oracle_forge@localhost:5432/oracle_forge"

# (original_name_in_description, actual_loaded_table_name)
SQLITE_VIEWS = [
    # bookreview
    ("review", "bookreview_review"),
    # agnews
    ("authors", "agnews_authors"),
    ("article_metadata", "agnews_article_metadata"),
    # PATENTS
    ("publicationinfo", "patents_publicationinfo"),
    # stockindex
    ("index_info", "stockindex_info"),
    # crmarenapro — SQLite-hosted tables (core_crm, products_orders, territory)
    ("User", "crm_User"),
    ("Account", "crm_Account"),
    ("Contact", "crm_Contact"),
    ("Territory2", "crm_Territory2"),
    ("UserTerritory2Association", "crm_UserTerritory2Association"),
    ("Order", "crm_Order"),
    ("OrderItem", "crm_OrderItem"),
    ("Pricebook2", "crm_Pricebook2"),
    ("PricebookEntry", "crm_PricebookEntry"),
    ("Product2", "crm_Product2"),
    ("ProductCategory", "crm_ProductCategory"),
    ("ProductCategoryProduct", "crm_ProductCategoryProduct"),
    # music_brainz_20k
    ("tracks", "musicbrainz_tracks"),
]

DUCKDB_VIEWS = [
    # crmarenapro — DuckDB-hosted tables (activities, sales_pipeline)
    ("Event", "crm_Event"),
    ("Task", "crm_Task"),
    ("VoiceCallTranscript__c", "crm_VoiceCallTranscript__c"),
    ("Contract", "crm_Contract"),
    ("Lead", "crm_Lead"),
    ("Opportunity", "crm_Opportunity"),
    ("OpportunityLineItem", "crm_OpportunityLineItem"),
    ("Quote", "crm_Quote"),
    ("QuoteLineItem", "crm_QuoteLineItem"),
    # DEPS_DEV_V1
    ("project_info", "deps_project_info"),
    ("project_packageversion", "deps_project_packageversion"),
    # stockindex
    ("index_trade", "stockindex_trade"),
    # music_brainz_20k
    ("sales", "musicbrainz_sales"),
    # yelp — user-generated content in DuckDB
    ("review", "yelp_review"),
    ("tip", "yelp_tip"),
    ("user", "yelp_user"),
]

POSTGRES_VIEWS = [
    # PATENTS
    ("publicationinfo", "patents_publicationinfo"),
    ("cpc_definition", "patents_cpc_definition"),
    # PANCANCER_ATLAS (clinical_info is already unprefixed)
    ("Mutation_Data", "pancancer_Mutation_Data"),
    ("RNASeq_Expression", "pancancer_RNASeq_Expression"),
]


def _q_sqlite(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def create_sqlite_views(views: list[tuple[str, str]]) -> tuple[int, int]:
    conn = sqlite3.connect(SQLITE_PATH)
    cur = conn.cursor()
    existing_tables = {
        r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
    }
    created = skipped = 0
    for view_name, source_name in views:
        if source_name not in existing_tables:
            print(f"  sqlite: skip {view_name!r} -> {source_name!r} (source missing)")
            skipped += 1
            continue
        cur.execute(f"DROP VIEW IF EXISTS {_q_sqlite(view_name)}")
        cur.execute(
            f"CREATE VIEW {_q_sqlite(view_name)} AS "
            f"SELECT * FROM {_q_sqlite(source_name)}"
        )
        created += 1
    conn.commit()
    conn.close()
    return created, skipped


def create_duckdb_views(views: list[tuple[str, str]]) -> tuple[int, int]:
    conn = duckdb.connect(str(DUCKDB_PATH))
    existing_rows = conn.execute(
        "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    existing_tables = {r[0] for r in existing_rows if r[1] == 'BASE TABLE'}
    existing_views = {r[0] for r in existing_rows if r[1] == 'VIEW'}
    # DuckDB resolves names case-insensitively; check collisions against all base
    # tables with the same uppercase form (e.g. crm_Lead view name 'Lead' would
    # collide with stock ticker 'LEAD').
    existing_tables_upper = {t.upper(): t for t in existing_tables}
    created = skipped = 0
    for view_name, source_name in views:
        if source_name not in existing_tables:
            print(f"  duckdb: skip {view_name!r} -> {source_name!r} (source missing)")
            skipped += 1
            continue
        collide = existing_tables_upper.get(view_name.upper())
        if collide and collide != source_name:
            print(
                f"  duckdb: skip {view_name!r} -> {source_name!r} "
                f"(name collides case-insensitively with base table {collide!r})"
            )
            skipped += 1
            continue
        # Drop any existing view with that exact name so CREATE succeeds cleanly
        if view_name in existing_views:
            conn.execute(f'DROP VIEW "{view_name}"')
        conn.execute(f'CREATE VIEW "{view_name}" AS SELECT * FROM "{source_name}"')
        created += 1
    conn.close()
    return created, skipped


def create_postgres_views(views: list[tuple[str, str]]) -> tuple[int, int]:
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    existing = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT viewname FROM pg_views WHERE schemaname='public'")
    existing |= {r[0] for r in cur.fetchall()}
    created = skipped = 0
    for view_name, source_name in views:
        if source_name not in existing:
            print(f"  postgres: skip {view_name!r} -> {source_name!r} (source missing)")
            skipped += 1
            continue
        cur.execute(f'DROP VIEW IF EXISTS "{view_name}"')
        cur.execute(f'CREATE VIEW "{view_name}" AS SELECT * FROM "{source_name}"')
        created += 1
    conn.commit()
    conn.close()
    return created, skipped


def main() -> int:
    print("== SQLite ==")
    c, s = create_sqlite_views(SQLITE_VIEWS)
    print(f"  -> {c} created, {s} skipped")

    print("== DuckDB ==")
    c2, s2 = create_duckdb_views(DUCKDB_VIEWS)
    print(f"  -> {c2} created, {s2} skipped")

    print("== Postgres ==")
    c3, s3 = create_postgres_views(POSTGRES_VIEWS)
    print(f"  -> {c3} created, {s3} skipped")

    total_c = c + c2 + c3
    total_s = s + s2 + s3
    print(f"\nTOTAL: {total_c} views created, {total_s} skipped (source missing).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
