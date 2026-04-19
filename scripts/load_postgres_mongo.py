#!/usr/bin/env python3
"""
Load DAB benchmark datasets into PostgreSQL and MongoDB.

PostgreSQL targets:
  bookreview_review, googlelocal_review,
  crm_User, crm_Account, crm_Contact,
  crm_ProductCategory, crm_Product2, crm_ProductCategoryProduct,
  crm_Pricebook2, crm_PricebookEntry, crm_Order, crm_OrderItem,
  crm_Territory2, crm_UserTerritory2Association,
  pancancer_Mutation_Data, pancancer_RNASeq_Expression

MongoDB targets (db=oracle_forge):
  agnews_authors, agnews_article_metadata,
  yelp_review, yelp_tip, yelp_user
"""

import os
import sqlite3
import sys
import traceback

import duckdb
import psycopg2
import psycopg2.extras
from pymongo import MongoClient

# ──────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────
BASE = "/home/nurye/data-analytics-agent/external/DataAgentBench"

SOURCES = {
    # (db_path, db_type, [tables], pg_prefix)
    "bookreview": (
        f"{BASE}/query_bookreview/query_dataset/review_query.db",
        "sqlite",
        ["review"],
        "bookreview_",
    ),
    "googlelocal": (
        f"{BASE}/query_googlelocal/query_dataset/review_query.db",
        "sqlite",
        ["review"],
        "googlelocal_",
    ),
    "crm_core": (
        f"{BASE}/query_crmarenapro/query_dataset/core_crm.db",
        "sqlite",
        ["User", "Account", "Contact"],
        "crm_",
    ),
    "crm_products": (
        f"{BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "sqlite",
        [
            "ProductCategory",
            "Product2",
            "ProductCategoryProduct",
            "Pricebook2",
            "PricebookEntry",
            "Order",
            "OrderItem",
        ],
        "crm_",
    ),
    "crm_territory": (
        f"{BASE}/query_crmarenapro/query_dataset/territory.db",
        "sqlite",
        ["Territory2", "UserTerritory2Association"],
        "crm_",
    ),
    "pancancer": (
        f"{BASE}/query_PANCANCER_ATLAS/query_dataset/pancancer_molecular.db",
        "duckdb",
        ["Mutation_Data", "RNASeq_Expression"],
        "pancancer_",
    ),
}

MONGO_SOURCES = {
    "agnews": (
        f"{BASE}/query_agnews/query_dataset/metadata.db",
        "sqlite",
        ["authors", "article_metadata"],
        "agnews_",
    ),
    "yelp": (
        f"{BASE}/query_yelp/query_dataset/yelp_user.db",
        "duckdb",
        ["review", "tip", "user"],
        "yelp_",
    ),
}

# ──────────────────────────────────────────────────────────
# PostgreSQL helpers
# ──────────────────────────────────────────────────────────
PG_CONN_PARAMS = dict(
    host="localhost",
    port=5432,
    user="oracle_forge",
    password="oracle_forge",
    dbname="oracle_forge",
)

CHUNK = 1000


def infer_pg_type(value):
    """Return PostgreSQL type string for a Python value."""
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "BIGINT"
    if isinstance(value, float):
        return "DOUBLE PRECISION"
    return "TEXT"


def infer_column_types(rows, col_names):
    """
    Walk the first up-to-500 non-null values per column to infer PG type.
    Defaults to TEXT for all-null columns.
    """
    types = {}
    for i, col in enumerate(col_names):
        col_type = "TEXT"
        for row in rows[:500]:
            val = row[i]
            if val is None:
                continue
            t = infer_pg_type(val)
            if t != "TEXT":
                col_type = t
            # TEXT wins over everything else → stop early
            if col_type == "TEXT":
                break
        types[col] = col_type
    return types


def quote_ident(name):
    """Double-quote a PostgreSQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def create_pg_table(pg_cur, table_name, col_names, col_types):
    col_defs = ", ".join(
        f"{quote_ident(c)} {col_types[c]}" for c in col_names
    )
    ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table_name)} ({col_defs})"
    pg_cur.execute(ddl)


def load_table_to_pg(pg_conn, table_name, col_names, rows):
    """Create table (if not exists) and bulk-insert rows."""
    if not rows:
        print(f"  [pg] {table_name}: 0 rows — skipping")
        return 0

    col_types = infer_column_types(rows, col_names)

    with pg_conn.cursor() as cur:
        create_pg_table(cur, table_name, col_names, col_types)
        pg_conn.commit()

        # Convert rows to list-of-dicts for execute_values
        placeholders = ", ".join(["%s"] * len(col_names))
        col_list = ", ".join(quote_ident(c) for c in col_names)
        insert_sql = (
            f"INSERT INTO {quote_ident(table_name)} ({col_list}) "
            f"VALUES ({placeholders})"
        )

        total = 0
        for start in range(0, len(rows), CHUNK):
            chunk = rows[start : start + CHUNK]
            # Cast values to correct Python types to avoid psycopg2 issues
            clean_chunk = []
            for row in chunk:
                clean_row = []
                for val in row:
                    # Convert numpy/duckdb types to native Python
                    if val is not None:
                        if hasattr(val, "item"):  # numpy scalar
                            val = val.item()
                    clean_row.append(val)
                clean_chunk.append(clean_row)
            cur.executemany(insert_sql, clean_chunk)
            total += len(chunk)
        pg_conn.commit()

    print(f"  [pg] {table_name}: {total:,} rows loaded (types: {col_types})")
    return total


def open_source(db_path, db_type):
    if db_type == "sqlite":
        return sqlite3.connect(db_path)
    elif db_type == "duckdb":
        return duckdb.connect(db_path, read_only=True)
    raise ValueError(f"Unknown db_type: {db_type}")


def fetch_all(conn, table, db_type):
    """Return (col_names, rows) from source connection."""
    if db_type == "sqlite":
        cur = conn.execute(f'SELECT * FROM "{table}"')
        col_names = [d[0] for d in cur.description]
        rows = cur.fetchall()
    else:  # duckdb
        cur = conn.execute(f'SELECT * FROM "{table}"')
        col_names = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return col_names, rows


# ──────────────────────────────────────────────────────────
# MongoDB helpers
# ──────────────────────────────────────────────────────────
MONGO_DB = "oracle_forge"


def load_collection(mongo_db, coll_name, col_names, rows):
    """Insert rows as documents; skip if collection already has data."""
    coll = mongo_db[coll_name]

    if coll.estimated_document_count() > 0:
        print(
            f"  [mongo] {coll_name}: already has data "
            f"({coll.estimated_document_count():,} docs) — skipping"
        )
        return 0

    if not rows:
        print(f"  [mongo] {coll_name}: 0 rows — skipping")
        return 0

    total = 0
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start : start + CHUNK]
        docs = []
        for row in chunk:
            doc = {}
            for k, v in zip(col_names, row):
                if hasattr(v, "item"):  # numpy/duckdb scalar
                    v = v.item()
                doc[k] = v
            docs.append(doc)
        coll.insert_many(docs, ordered=False)
        total += len(chunk)

    print(f"  [mongo] {coll_name}: {total:,} docs inserted")
    return total


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────
def main():
    pg_results = {}  # table_name -> row_count or error string
    mongo_results = {}  # coll_name -> doc_count or error string

    # ── PostgreSQL ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("LOADING INTO POSTGRESQL")
    print("=" * 60)

    pg_conn = psycopg2.connect(**PG_CONN_PARAMS)

    for source_key, (db_path, db_type, tables, prefix) in SOURCES.items():
        print(f"\n--- {source_key} ({db_path}) ---")
        if not os.path.exists(db_path):
            print(f"  SKIPPED: file not found: {db_path}")
            for t in tables:
                pg_results[prefix + t] = "file not found"
            continue

        try:
            src_conn = open_source(db_path, db_type)
        except Exception as e:
            print(f"  ERROR opening source: {e}")
            for t in tables:
                pg_results[prefix + t] = f"open error: {e}"
            continue

        for table in tables:
            pg_table = prefix + table
            try:
                col_names, rows = fetch_all(src_conn, table, db_type)
                n = load_table_to_pg(pg_conn, pg_table, col_names, rows)
                pg_results[pg_table] = n
            except Exception as e:
                pg_conn.rollback()
                print(f"  ERROR loading {pg_table}: {e}")
                traceback.print_exc()
                pg_results[pg_table] = f"error: {e}"

        src_conn.close()

    pg_conn.close()

    # ── MongoDB ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("LOADING INTO MONGODB")
    print("=" * 60)

    mongo_client = MongoClient("localhost", 27017)
    mongo_db = mongo_client[MONGO_DB]

    # NOTE: patents source is known-corrupt — skip with message
    print("\n--- patents (SKIPPED) ---")
    print("  SKIP: patents source file is corrupt/malformed — skipping as requested")

    for source_key, (db_path, db_type, tables, prefix) in MONGO_SOURCES.items():
        print(f"\n--- {source_key} ({db_path}) ---")
        if not os.path.exists(db_path):
            print(f"  SKIPPED: file not found: {db_path}")
            for t in tables:
                mongo_results[prefix + t] = "file not found"
            continue

        try:
            src_conn = open_source(db_path, db_type)
        except Exception as e:
            print(f"  ERROR opening source: {e}")
            for t in tables:
                mongo_results[prefix + t] = f"open error: {e}"
            continue

        for table in tables:
            coll_name = prefix + table
            try:
                col_names, rows = fetch_all(src_conn, table, db_type)
                n = load_collection(mongo_db, coll_name, col_names, rows)
                mongo_results[coll_name] = n
            except Exception as e:
                print(f"  ERROR loading {coll_name}: {e}")
                traceback.print_exc()
                mongo_results[coll_name] = f"error: {e}"

        src_conn.close()

    mongo_client.close()

    # ── Final Summary ────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    print("\nPostgreSQL tables (oracle_forge):")
    pg_verify = psycopg2.connect(**PG_CONN_PARAMS)
    with pg_verify.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        pg_tables = [r[0] for r in cur.fetchall()]
    pg_verify.close()

    for t in pg_tables:
        status = pg_results.get(t, "(pre-existing)")
        if isinstance(status, int):
            print(f"  {t}: {status:,} rows")
        else:
            print(f"  {t}: {status}")

    tables_not_shown = set(pg_results) - set(pg_tables)
    for t in sorted(tables_not_shown):
        print(f"  {t}: {pg_results[t]}")

    print("\nMongoDB collections (oracle_forge):")
    mongo_client2 = MongoClient("localhost", 27017)
    colls = sorted(mongo_client2[MONGO_DB].list_collection_names())
    mongo_client2.close()

    for c in colls:
        status = mongo_results.get(c, "(pre-existing)")
        if isinstance(status, int):
            print(f"  {c}: {status:,} docs")
        else:
            print(f"  {c}: {status}")

    colls_not_shown = set(mongo_results) - set(colls)
    for c in sorted(colls_not_shown):
        print(f"  {c}: {mongo_results[c]}")

    print("\nDone.")


if __name__ == "__main__":
    main()
