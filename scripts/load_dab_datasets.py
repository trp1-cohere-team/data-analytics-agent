"""
load_dab_datasets.py

Loads all DAB (DataAgentBench) datasets into the main SQLite and DuckDB databases.
Skips stock market data (already loaded).
Skips tables that already exist in the destination.
"""

import sqlite3
import duckdb
import os

DAB_BASE = "/home/nurye/data-analytics-agent/external/DataAgentBench"
MAIN_SQLITE = "/home/nurye/data-analytics-agent/data/sqlite/main.db"
MAIN_DUCKDB = "/home/nurye/data-analytics-agent/data/duckdb/main.duckdb"

# ---------------------------------------------------------------------------
# SQLite load plan: list of (source_db_path, src_table, dest_table)
# ---------------------------------------------------------------------------
SQLITE_LOAD_PLAN = [
    # bookreview
    (
        f"{DAB_BASE}/query_bookreview/query_dataset/review_query.db",
        "review",
        "bookreview_review",
    ),
    # crm – core_crm
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/core_crm.db",
        "User",
        "crm_User",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/core_crm.db",
        "Account",
        "crm_Account",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/core_crm.db",
        "Contact",
        "crm_Contact",
    ),
    # crm – products_orders
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "ProductCategory",
        "crm_ProductCategory",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "Product2",
        "crm_Product2",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "ProductCategoryProduct",
        "crm_ProductCategoryProduct",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "Pricebook2",
        "crm_Pricebook2",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "PricebookEntry",
        "crm_PricebookEntry",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "Order",
        "crm_Order",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/products_orders.db",
        "OrderItem",
        "crm_OrderItem",
    ),
    # crm – territory
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/territory.db",
        "Territory2",
        "crm_Territory2",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/territory.db",
        "UserTerritory2Association",
        "crm_UserTerritory2Association",
    ),
    # stockindex
    (
        f"{DAB_BASE}/query_stockindex/query_dataset/indexInfo_query.db",
        "index_info",
        "stockindex_info",
    ),
    # musicbrainz
    (
        f"{DAB_BASE}/query_music_brainz_20k/query_dataset/tracks.db",
        "tracks",
        "musicbrainz_tracks",
    ),
    # googlelocal
    (
        f"{DAB_BASE}/query_googlelocal/query_dataset/review_query.db",
        "review",
        "googlelocal_review",
    ),
    # agnews
    (
        f"{DAB_BASE}/query_agnews/query_dataset/metadata.db",
        "authors",
        "agnews_authors",
    ),
    (
        f"{DAB_BASE}/query_agnews/query_dataset/metadata.db",
        "article_metadata",
        "agnews_article_metadata",
    ),
]

# ---------------------------------------------------------------------------
# DuckDB load plan: list of (source_db_path, src_table, dest_table)
# ---------------------------------------------------------------------------
DUCKDB_LOAD_PLAN = [
    # crm – activities
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/activities.duckdb",
        "Event",
        "crm_Event",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/activities.duckdb",
        "Task",
        "crm_Task",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/activities.duckdb",
        "VoiceCallTranscript__c",
        "crm_VoiceCallTranscript__c",
    ),
    # crm – sales_pipeline
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/sales_pipeline.duckdb",
        "Contract",
        "crm_Contract",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/sales_pipeline.duckdb",
        "Lead",
        "crm_Lead",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/sales_pipeline.duckdb",
        "Opportunity",
        "crm_Opportunity",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/sales_pipeline.duckdb",
        "OpportunityLineItem",
        "crm_OpportunityLineItem",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/sales_pipeline.duckdb",
        "Quote",
        "crm_Quote",
    ),
    (
        f"{DAB_BASE}/query_crmarenapro/query_dataset/sales_pipeline.duckdb",
        "QuoteLineItem",
        "crm_QuoteLineItem",
    ),
    # musicbrainz – sales
    (
        f"{DAB_BASE}/query_music_brainz_20k/query_dataset/sales.duckdb",
        "sales",
        "musicbrainz_sales",
    ),
    # deps_dev
    (
        f"{DAB_BASE}/query_DEPS_DEV_V1/query_dataset/project_query.db",
        "project_info",
        "deps_project_info",
    ),
    (
        f"{DAB_BASE}/query_DEPS_DEV_V1/query_dataset/project_query.db",
        "project_packageversion",
        "deps_project_packageversion",
    ),
    # stockindex – indextrade
    (
        f"{DAB_BASE}/query_stockindex/query_dataset/indextrade_query.db",
        "index_trade",
        "stockindex_trade",
    ),
    # yelp
    (
        f"{DAB_BASE}/query_yelp/query_dataset/yelp_user.db",
        "review",
        "yelp_review",
    ),
    (
        f"{DAB_BASE}/query_yelp/query_dataset/yelp_user.db",
        "tip",
        "yelp_tip",
    ),
    (
        f"{DAB_BASE}/query_yelp/query_dataset/yelp_user.db",
        "user",
        "yelp_user",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sqlite_table_exists(conn, table_name):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def load_sqlite_tables():
    print("\n" + "=" * 60)
    print("LOADING SQLITE TABLES INTO main.db")
    print("=" * 60)

    successes = []
    skipped = []
    failures = []

    dest_conn = sqlite3.connect(MAIN_SQLITE)

    for src_path, src_table, dest_table in SQLITE_LOAD_PLAN:
        try:
            # Skip if destination table already exists
            if sqlite_table_exists(dest_conn, dest_table):
                print(f"  [SKIP]    {dest_table} (already exists)")
                skipped.append(dest_table)
                continue

            if not os.path.isfile(src_path):
                raise FileNotFoundError(f"Source file not found: {src_path}")

            # Attach source DB under alias 'src', copy table, detach
            dest_conn.execute(f"ATTACH DATABASE '{src_path}' AS src")
            dest_conn.execute(
                f'CREATE TABLE "{dest_table}" AS SELECT * FROM src."{src_table}"'
            )
            dest_conn.commit()
            dest_conn.execute("DETACH DATABASE src")

            row_count = dest_conn.execute(
                f'SELECT COUNT(*) FROM "{dest_table}"'
            ).fetchone()[0]
            print(f"  [OK]      {dest_table}  ({row_count:,} rows)")
            successes.append(dest_table)

        except Exception as e:
            # Make sure we detach if still attached
            try:
                dest_conn.execute("DETACH DATABASE src")
            except Exception:
                pass
            print(f"  [FAIL]    {dest_table}: {e}")
            failures.append((dest_table, str(e)))

    dest_conn.close()
    return successes, skipped, failures


def duckdb_table_exists(conn, table_name):
    result = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' AND table_name=?",
        [table_name],
    ).fetchone()
    return result is not None


def load_duckdb_tables():
    print("\n" + "=" * 60)
    print("LOADING DUCKDB TABLES INTO main.duckdb")
    print("=" * 60)

    successes = []
    skipped = []
    failures = []

    dest_conn = duckdb.connect(MAIN_DUCKDB)

    # Group by source file to minimise ATTACH/DETACH cycles
    seen_sources = {}
    attach_alias_counter = [0]

    def get_alias(src_path):
        if src_path not in seen_sources:
            attach_alias_counter[0] += 1
            alias = f"src{attach_alias_counter[0]}"
            seen_sources[src_path] = alias
        return seen_sources[src_path]

    for src_path, src_table, dest_table in DUCKDB_LOAD_PLAN:
        try:
            # Skip if destination table already exists
            if duckdb_table_exists(dest_conn, dest_table):
                print(f"  [SKIP]    {dest_table} (already exists)")
                skipped.append(dest_table)
                continue

            if not os.path.isfile(src_path):
                raise FileNotFoundError(f"Source file not found: {src_path}")

            alias = get_alias(src_path)

            # Attach if not already attached
            attached = dest_conn.execute(
                "SELECT database_name FROM duckdb_databases() WHERE database_name=?",
                [alias],
            ).fetchone()
            if not attached:
                dest_conn.execute(f"ATTACH '{src_path}' AS {alias} (READ_ONLY)")

            dest_conn.execute(
                f'CREATE TABLE "{dest_table}" AS SELECT * FROM {alias}."{src_table}"'
            )

            row_count = dest_conn.execute(
                f'SELECT COUNT(*) FROM "{dest_table}"'
            ).fetchone()[0]
            print(f"  [OK]      {dest_table}  ({row_count:,} rows)")
            successes.append(dest_table)

        except Exception as e:
            print(f"  [FAIL]    {dest_table}: {e}")
            failures.append((dest_table, str(e)))

    # Detach all source databases we attached
    for alias in seen_sources.values():
        try:
            dest_conn.execute(f"DETACH {alias}")
        except Exception:
            pass

    dest_conn.close()
    return successes, skipped, failures


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def print_sqlite_summary():
    print("\n--- main.db final table list ---")
    conn = sqlite3.connect(MAIN_SQLITE)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for (t,) in tables:
        count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t}  ({count:,} rows)")
    conn.close()
    print(f"  Total: {len(tables)} tables")


def print_duckdb_summary():
    print("\n--- main.duckdb final table list (non-stock) ---")
    conn = duckdb.connect(MAIN_DUCKDB, read_only=True)
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()
    # Show only non-ticker tables in full; summarise stock tickers
    non_stock = []
    stock_count = 0
    for (t,) in tables:
        # Ticker tables are short uppercase names (loaded previously)
        if len(t) <= 5 and t.isupper():
            stock_count += 1
        else:
            non_stock.append(t)
    for t in non_stock:
        count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t}  ({count:,} rows)")
    print(f"  ... plus {stock_count} stock ticker tables (pre-existing)")
    conn.close()
    print(f"  Total: {len(tables)} tables")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    sq_ok, sq_skip, sq_fail = load_sqlite_tables()
    dk_ok, dk_skip, dk_fail = load_duckdb_tables()

    print("\n" + "=" * 60)
    print("LOAD SUMMARY")
    print("=" * 60)
    print(f"SQLite  — loaded: {len(sq_ok)}, skipped: {len(sq_skip)}, failed: {len(sq_fail)}")
    print(f"DuckDB  — loaded: {len(dk_ok)}, skipped: {len(dk_skip)}, failed: {len(dk_fail)}")

    if sq_fail:
        print("\nSQLite failures:")
        for tbl, err in sq_fail:
            print(f"  {tbl}: {err}")
    if dk_fail:
        print("\nDuckDB failures:")
        for tbl, err in dk_fail:
            print(f"  {tbl}: {err}")

    print_sqlite_summary()
    print_duckdb_summary()


if __name__ == "__main__":
    main()
