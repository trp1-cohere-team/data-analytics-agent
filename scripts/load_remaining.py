#!/usr/bin/env python3
"""
load_remaining.py

Loads all remaining missing DAB data:
  1. MongoDB: agnews_authors, agnews_article_metadata, yelp_review, yelp_tip, yelp_user
  2. PostgreSQL: pancancer_RNASeq_Expression (chunked from DuckDB, 9.9M rows)
  3. PostgreSQL: cpc_definition from patent_CPCDefinition.sql dump
  4. PostgreSQL: patents_publicationinfo from patent_publication.db
  5. SQLite:     patents_publicationinfo from patent_publication.db
"""

import io
import os
import re
import sqlite3
import sys
import traceback

import duckdb
import psycopg2
import psycopg2.extras
from pymongo import MongoClient

# ──────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────
BASE = "/home/nurye/data-analytics-agent/external/DataAgentBench"
MAIN_SQLITE = "/home/nurye/data-analytics-agent/data/sqlite/main.db"
MAIN_DUCKDB = "/home/nurye/data-analytics-agent/data/duckdb/main.duckdb"

PG_CONN_PARAMS = dict(
    host="localhost", port=5432,
    user="oracle_forge", password="oracle_forge", dbname="oracle_forge",
)
MONGO_DB_NAME = "oracle_forge"
CHUNK = 5000  # rows per batch


# ──────────────────────────────────────────────────────────
# 1. MongoDB
# ──────────────────────────────────────────────────────────
MONGO_SOURCES = {
    "agnews": (
        f"{BASE}/query_agnews/query_dataset/metadata.db",
        "sqlite",
        [("authors", "agnews_authors"), ("article_metadata", "agnews_article_metadata")],
    ),
    "yelp": (
        f"{BASE}/query_yelp/query_dataset/yelp_user.db",
        "duckdb",
        [("review", "yelp_review"), ("tip", "yelp_tip"), ("user", "yelp_user")],
    ),
}


def load_mongodb():
    print("\n" + "=" * 60)
    print("LOADING INTO MONGODB")
    print("=" * 60)

    client = MongoClient("localhost", 27017)
    db = client[MONGO_DB_NAME]
    results = {}

    for source_key, (db_path, db_type, table_pairs) in MONGO_SOURCES.items():
        print(f"\n--- {source_key} ---")
        if not os.path.exists(db_path):
            print(f"  SKIPPED: file not found: {db_path}")
            continue

        try:
            if db_type == "sqlite":
                src = sqlite3.connect(db_path)
            else:
                src = duckdb.connect(db_path, read_only=True)
        except Exception as e:
            print(f"  ERROR opening source: {e}")
            continue

        for src_table, coll_name in table_pairs:
            coll = db[coll_name]
            if coll.estimated_document_count() > 0:
                n = coll.estimated_document_count()
                print(f"  [SKIP] {coll_name}: already has {n:,} docs")
                results[coll_name] = n
                continue

            try:
                if db_type == "sqlite":
                    cur = src.execute(f'SELECT * FROM "{src_table}"')
                    col_names = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                else:
                    cur = src.execute(f'SELECT * FROM "{src_table}"')
                    col_names = [d[0] for d in cur.description]
                    rows = cur.fetchall()

                if not rows:
                    print(f"  [SKIP] {coll_name}: 0 source rows")
                    results[coll_name] = 0
                    continue

                total = 0
                for start in range(0, len(rows), CHUNK):
                    chunk = rows[start: start + CHUNK]
                    docs = []
                    for row in chunk:
                        doc = {}
                        for k, v in zip(col_names, row):
                            if hasattr(v, "item"):
                                v = v.item()
                            doc[k] = v
                        docs.append(doc)
                    coll.insert_many(docs, ordered=False)
                    total += len(chunk)
                    print(f"    {coll_name}: {total:,}/{len(rows):,} inserted...", end="\r")

                print(f"  [OK] {coll_name}: {total:,} docs inserted      ")
                results[coll_name] = total

            except Exception as e:
                print(f"  [FAIL] {coll_name}: {e}")
                traceback.print_exc()
                results[coll_name] = f"error: {e}"

        src.close()

    client.close()
    return results


# ──────────────────────────────────────────────────────────
# 2. PostgreSQL: pancancer_RNASeq_Expression (chunked)
# ──────────────────────────────────────────────────────────
def load_pancancer_rnaseq():
    print("\n" + "=" * 60)
    print("LOADING pancancer_RNASeq_Expression → PostgreSQL (chunked)")
    print("=" * 60)

    src_path = f"{BASE}/query_PANCANCER_ATLAS/query_dataset/pancancer_molecular.db"
    table = "RNASeq_Expression"
    pg_table = "pancancer_RNASeq_Expression"

    pg = psycopg2.connect(**PG_CONN_PARAMS)

    # Check current PG row count
    with pg.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s)",
            (pg_table,)
        )
        exists = cur.fetchone()[0]
        if exists:
            cur.execute(f'SELECT COUNT(*) FROM "{pg_table}"')
            count = cur.fetchone()[0]
            if count > 0:
                print(f"  [SKIP] {pg_table}: already has {count:,} rows")
                pg.close()
                return count
            else:
                print(f"  Table exists but empty ({count} rows) — will load")
                cur.execute(f'DROP TABLE "{pg_table}"')
                pg.commit()
        else:
            print(f"  Table does not exist — will create and load")

    # Open DuckDB source
    src = duckdb.connect(src_path, read_only=True)
    total_rows = src.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"  Source rows: {total_rows:,}")

    # Get column info from first batch
    first_batch = src.execute(f'SELECT * FROM "{table}" LIMIT 1').fetchall()
    col_names = [d[0] for d in src.description]

    # Infer PG types from first 500 rows
    sample = src.execute(f'SELECT * FROM "{table}" LIMIT 500').fetchall()

    def infer_type(val):
        if isinstance(val, bool):
            return "BOOLEAN"
        if isinstance(val, int):
            return "BIGINT"
        if isinstance(val, float):
            return "DOUBLE PRECISION"
        return "TEXT"

    col_types = {}
    for i, col in enumerate(col_names):
        col_type = "TEXT"
        for row in sample:
            v = row[i]
            if v is None:
                continue
            t = infer_type(v)
            if t != "TEXT":
                col_type = t
            if col_type == "TEXT":
                break
        col_types[col] = col_type

    def qi(name):
        return '"' + name.replace('"', '""') + '"'

    col_defs = ", ".join(f"{qi(c)} {col_types[c]}" for c in col_names)
    col_list = ", ".join(qi(c) for c in col_names)
    placeholders = ", ".join(["%s"] * len(col_names))
    insert_sql = f'INSERT INTO {qi(pg_table)} ({col_list}) VALUES ({placeholders})'

    with pg.cursor() as cur:
        cur.execute(f'CREATE TABLE {qi(pg_table)} ({col_defs})')
        pg.commit()

    total_inserted = 0
    offset = 0
    while True:
        rows = src.execute(
            f'SELECT * FROM "{table}" LIMIT {CHUNK} OFFSET {offset}'
        ).fetchall()
        if not rows:
            break

        clean_rows = []
        for row in rows:
            clean_row = []
            for v in row:
                if v is not None and hasattr(v, "item"):
                    v = v.item()
                clean_row.append(v)
            clean_rows.append(clean_row)

        with pg.cursor() as cur:
            psycopg2.extras.execute_batch(cur, insert_sql, clean_rows, page_size=1000)
        pg.commit()

        total_inserted += len(rows)
        offset += CHUNK
        pct = total_inserted / total_rows * 100
        print(f"  {total_inserted:,}/{total_rows:,} ({pct:.1f}%)", end="\r", flush=True)

    print(f"\n  [OK] {pg_table}: {total_inserted:,} rows inserted")
    src.close()
    pg.close()
    return total_inserted


# ──────────────────────────────────────────────────────────
# 3. PostgreSQL: cpc_definition from SQL dump (COPY format)
# ──────────────────────────────────────────────────────────
def load_cpc_definition():
    print("\n" + "=" * 60)
    print("LOADING cpc_definition → PostgreSQL (from SQL dump)")
    print("=" * 60)

    sql_path = f"{BASE}/query_PATENTS/query_dataset/patent_CPCDefinition.sql"
    pg_table = "patents_cpc_definition"

    pg = psycopg2.connect(**PG_CONN_PARAMS)
    with pg.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s)",
            (pg_table,)
        )
        if cur.fetchone()[0]:
            cur.execute(f'SELECT COUNT(*) FROM "{pg_table}"')
            count = cur.fetchone()[0]
            if count > 0:
                print(f"  [SKIP] {pg_table}: already has {count:,} rows")
                pg.close()
                return count

    # Parse the SQL dump: extract CREATE TABLE and COPY data
    with open(sql_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract CREATE TABLE block (adapt owner to oracle_forge)
    create_match = re.search(
        r"CREATE TABLE public\.cpc_definition \((.+?)\);",
        content, re.DOTALL
    )
    if not create_match:
        print("  [FAIL] Could not find CREATE TABLE in SQL dump")
        pg.close()
        return 0

    col_block = create_match.group(1)
    create_sql = f'CREATE TABLE IF NOT EXISTS "patents_cpc_definition" ({col_block})'

    with pg.cursor() as cur:
        cur.execute(create_sql)
        pg.commit()

    # Extract COPY data block
    copy_match = re.search(
        r"COPY public\.cpc_definition \((.+?)\) FROM stdin;\n(.+?)\\\.",
        content, re.DOTALL
    )
    if not copy_match:
        print("  [FAIL] Could not find COPY data in SQL dump")
        pg.close()
        return 0

    col_part = copy_match.group(1)
    data_part = copy_match.group(2)

    copy_sql = f'COPY "patents_cpc_definition" ({col_part}) FROM STDIN'
    data_io = io.StringIO(data_part)

    with pg.cursor() as cur:
        cur.copy_expert(copy_sql, data_io)
    pg.commit()

    with pg.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "patents_cpc_definition"')
        count = cur.fetchone()[0]

    print(f"  [OK] patents_cpc_definition: {count:,} rows inserted")
    pg.close()
    return count


# ──────────────────────────────────────────────────────────
# 4. PostgreSQL: patents_publicationinfo from SQLite
# ──────────────────────────────────────────────────────────
def load_patents_pg():
    print("\n" + "=" * 60)
    print("LOADING patents_publicationinfo → PostgreSQL")
    print("=" * 60)

    src_path = f"{BASE}/query_PATENTS/query_dataset/patent_publication.db"
    pg_table = "patents_publicationinfo"

    pg = psycopg2.connect(**PG_CONN_PARAMS)
    with pg.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s)",
            (pg_table,)
        )
        if cur.fetchone()[0]:
            cur.execute(f'SELECT COUNT(*) FROM "{pg_table}"')
            count = cur.fetchone()[0]
            if count > 0:
                print(f"  [SKIP] {pg_table}: already has {count:,} rows")
                pg.close()
                return count

    src = sqlite3.connect(src_path)
    total = src.execute('SELECT COUNT(*) FROM "publicationinfo"').fetchone()[0]
    print(f"  Source rows: {total:,}")

    # Create table (all TEXT except family_id which is INTEGER)
    with pg.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{pg_table}" (
                "Patents_info" TEXT, "kind_code" TEXT, "application_kind" TEXT,
                "pct_number" TEXT, "family_id" BIGINT, "title_localized" TEXT,
                "abstract_localized" TEXT, "claims_localized_html" TEXT,
                "description_localized_html" TEXT, "publication_date" TEXT,
                "filing_date" TEXT, "grant_date" TEXT, "priority_date" TEXT,
                "priority_claim" TEXT, "inventor_harmonized" TEXT, "examiner" TEXT,
                "uspc" TEXT, "ipc" TEXT, "cpc" TEXT, "citation" TEXT,
                "parent" TEXT, "child" TEXT, "entity_status" TEXT, "art_unit" TEXT
            )
        """)
        pg.commit()

    col_names = [
        "Patents_info", "kind_code", "application_kind", "pct_number",
        "family_id", "title_localized", "abstract_localized", "claims_localized_html",
        "description_localized_html", "publication_date", "filing_date", "grant_date",
        "priority_date", "priority_claim", "inventor_harmonized", "examiner",
        "uspc", "ipc", "cpc", "citation", "parent", "child", "entity_status", "art_unit"
    ]
    col_list = ", ".join(f'"{c}"' for c in col_names)
    placeholders = ", ".join(["%s"] * len(col_names))
    insert_sql = f'INSERT INTO "{pg_table}" ({col_list}) VALUES ({placeholders})'

    inserted = 0
    offset = 0
    while True:
        rows = src.execute(
            f'SELECT * FROM "publicationinfo" LIMIT {CHUNK} OFFSET {offset}'
        ).fetchall()
        if not rows:
            break
        with pg.cursor() as cur:
            psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=1000)
        pg.commit()
        inserted += len(rows)
        offset += CHUNK
        print(f"  {inserted:,}/{total:,}", end="\r", flush=True)

    print(f"\n  [OK] {pg_table}: {inserted:,} rows inserted")
    src.close()
    pg.close()
    return inserted


# ──────────────────────────────────────────────────────────
# 5. SQLite: patents_publicationinfo
# ──────────────────────────────────────────────────────────
def load_patents_sqlite():
    print("\n" + "=" * 60)
    print("LOADING patents_publicationinfo → SQLite")
    print("=" * 60)

    src_path = f"{BASE}/query_PATENTS/query_dataset/patent_publication.db"
    dest_table = "patents_publicationinfo"

    dest = sqlite3.connect(MAIN_SQLITE)
    exists = dest.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (dest_table,)
    ).fetchone()
    if exists:
        count = dest.execute(f'SELECT COUNT(*) FROM "{dest_table}"').fetchone()[0]
        if count > 0:
            print(f"  [SKIP] {dest_table}: already has {count:,} rows")
            dest.close()
            return count

    print(f"  Attaching source and copying table...")
    dest.execute(f"ATTACH DATABASE '{src_path}' AS pat_src")
    dest.execute(f'CREATE TABLE "{dest_table}" AS SELECT * FROM pat_src."publicationinfo"')
    dest.commit()
    dest.execute("DETACH DATABASE pat_src")

    count = dest.execute(f'SELECT COUNT(*) FROM "{dest_table}"').fetchone()[0]
    print(f"  [OK] {dest_table}: {count:,} rows")
    dest.close()
    return count


# ──────────────────────────────────────────────────────────
# Final summary
# ──────────────────────────────────────────────────────────
def print_summary():
    print("\n" + "=" * 60)
    print("FINAL STATUS — ALL 4 DATABASES")
    print("=" * 60)

    # SQLite
    conn = sqlite3.connect(MAIN_SQLITE)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    print(f"\nSQLite ({len(tables)} tables):")
    for (t,) in tables:
        n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t}: {n:,}")
    conn.close()

    # PostgreSQL
    pg = psycopg2.connect(**PG_CONN_PARAMS)
    with pg.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        tables = cur.fetchall()
    print(f"\nPostgreSQL ({len(tables)} tables):")
    with pg.cursor() as cur:
        for (t,) in tables:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            n = cur.fetchone()[0]
            print(f"  {t}: {n:,}")
    pg.close()

    # MongoDB
    client = MongoClient("localhost", 27017)
    db = client[MONGO_DB_NAME]
    colls = sorted(db.list_collection_names())
    print(f"\nMongoDB oracle_forge ({len(colls)} collections):")
    for c in colls:
        n = db[c].estimated_document_count()
        print(f"  {c}: {n:,}")
    client.close()

    # DuckDB (named tables only)
    dcon = duckdb.connect(MAIN_DUCKDB, read_only=True)
    all_tables = dcon.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()
    named = [t[0] for t in all_tables if not (len(t[0]) <= 5 and t[0].isupper())]
    stock_count = len(all_tables) - len(named)
    print(f"\nDuckDB ({len(all_tables)} tables, {stock_count} stock tickers + {len(named)} named):")
    for t in named:
        n = dcon.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t}: {n:,}")
    dcon.close()


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_mongodb()
    load_pancancer_rnaseq()
    load_cpc_definition()
    load_patents_pg()
    load_patents_sqlite()
    print_summary()
    print("\nDone.")
