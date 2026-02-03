#!/usr/bin/env python3
"""
Setup Vercel/Neon Postgres Database
===================================
Loads the retail ERP schema and data into a cloud Postgres database.

Usage:
    1. Set environment variables in .env file
    2. Run: python setup_vercel_db.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# Database config from environment
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "retail_erp"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# Add SSL if specified
if os.getenv("DB_SSLMODE"):
    DB_CONFIG["sslmode"] = os.getenv("DB_SSLMODE")

DATA_DIR = Path(__file__).parent / "Data" / "retail_erp_excel_tables"


def create_schema(conn):
    """Create database schema matching Excel data."""
    print("Creating schema...")

    schema_sql = """
    -- Drop existing tables (in reverse dependency order)
    DROP TABLE IF EXISTS transfer_order_line CASCADE;
    DROP TABLE IF EXISTS transfer_order CASCADE;
    DROP TABLE IF EXISTS return_line CASCADE;
    DROP TABLE IF EXISTS return CASCADE;
    DROP TABLE IF EXISTS goods_receipt_line CASCADE;
    DROP TABLE IF EXISTS goods_receipt CASCADE;
    DROP TABLE IF EXISTS purchase_order_line CASCADE;
    DROP TABLE IF EXISTS purchase_order CASCADE;
    DROP TABLE IF EXISTS pos_transaction_line CASCADE;
    DROP TABLE IF EXISTS pos_transaction CASCADE;
    DROP TABLE IF EXISTS promotion_sku CASCADE;
    DROP TABLE IF EXISTS promotion CASCADE;
    DROP TABLE IF EXISTS price CASCADE;
    DROP TABLE IF EXISTS price_list CASCADE;
    DROP TABLE IF EXISTS dc_inventory CASCADE;
    DROP TABLE IF EXISTS store_inventory CASCADE;
    DROP TABLE IF EXISTS supplier_product CASCADE;
    DROP TABLE IF EXISTS sku CASCADE;
    DROP TABLE IF EXISTS supplier CASCADE;
    DROP TABLE IF EXISTS product CASCADE;
    DROP TABLE IF EXISTS product_category CASCADE;
    DROP TABLE IF EXISTS brand CASCADE;
    DROP TABLE IF EXISTS dc CASCADE;
    DROP TABLE IF EXISTS store CASCADE;
    DROP TABLE IF EXISTS customer CASCADE;

    -- Create tables matching Excel structure (all IDs are VARCHAR with prefixes)

    CREATE TABLE brand (
        brand_id VARCHAR(20) PRIMARY KEY,
        brand_name VARCHAR(100) NOT NULL
    );

    CREATE TABLE product_category (
        category_id VARCHAR(20) PRIMARY KEY,
        parent_category_id VARCHAR(20),
        category_name VARCHAR(100) NOT NULL
    );

    CREATE TABLE product (
        product_id VARCHAR(20) PRIMARY KEY,
        brand_id VARCHAR(20) REFERENCES brand(brand_id),
        category_id VARCHAR(20) REFERENCES product_category(category_id),
        product_name VARCHAR(200) NOT NULL,
        status VARCHAR(30)
    );

    CREATE TABLE store (
        store_id VARCHAR(20) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        city VARCHAR(100),
        region VARCHAR(50),
        store_format VARCHAR(50)
    );

    CREATE TABLE dc (
        dc_id VARCHAR(20) PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        location VARCHAR(100)
    );

    CREATE TABLE customer (
        customer_id VARCHAR(20) PRIMARY KEY,
        loyalty_id VARCHAR(50),
        segment VARCHAR(50)
    );

    CREATE TABLE supplier (
        supplier_id VARCHAR(20) PRIMARY KEY,
        supplier_name VARCHAR(100) NOT NULL,
        lead_time_days INTEGER,
        payment_terms VARCHAR(50)
    );

    CREATE TABLE sku (
        sku_id VARCHAR(20) PRIMARY KEY,
        product_id VARCHAR(20) REFERENCES product(product_id),
        upc VARCHAR(50),
        uom VARCHAR(20),
        pack_size INTEGER,
        status VARCHAR(30)
    );

    CREATE TABLE supplier_product (
        supplier_id VARCHAR(20) REFERENCES supplier(supplier_id),
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        supplier_sku_code VARCHAR(50),
        cost DECIMAL(10,2),
        moq INTEGER,
        PRIMARY KEY (supplier_id, sku_id)
    );

    CREATE TABLE store_inventory (
        store_id VARCHAR(20) REFERENCES store(store_id),
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        on_hand_qty INTEGER DEFAULT 0,
        in_transit_qty INTEGER DEFAULT 0,
        reorder_point INTEGER,
        PRIMARY KEY (store_id, sku_id)
    );

    CREATE TABLE dc_inventory (
        dc_id VARCHAR(20) REFERENCES dc(dc_id),
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        on_hand_qty INTEGER DEFAULT 0,
        reserved_qty INTEGER DEFAULT 0,
        PRIMARY KEY (dc_id, sku_id)
    );

    CREATE TABLE price_list (
        price_list_id VARCHAR(20) PRIMARY KEY,
        name VARCHAR(100),
        currency VARCHAR(10),
        effective_start DATE,
        effective_end DATE
    );

    CREATE TABLE price (
        price_list_id VARCHAR(20) REFERENCES price_list(price_list_id),
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        store_id VARCHAR(20) REFERENCES store(store_id),
        price DECIMAL(10,2),
        effective_start DATE,
        effective_end DATE,
        PRIMARY KEY (price_list_id, sku_id, store_id)
    );

    CREATE TABLE promotion (
        promo_id VARCHAR(20) PRIMARY KEY,
        promo_name VARCHAR(100),
        type VARCHAR(50),
        start_date DATE,
        end_date DATE
    );

    CREATE TABLE promotion_sku (
        promo_id VARCHAR(20) REFERENCES promotion(promo_id),
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        discount_type VARCHAR(30),
        discount_value DECIMAL(10,2),
        PRIMARY KEY (promo_id, sku_id)
    );

    CREATE TABLE pos_transaction (
        txn_id VARCHAR(20) PRIMARY KEY,
        store_id VARCHAR(20) REFERENCES store(store_id),
        customer_id VARCHAR(20) REFERENCES customer(customer_id),
        txn_ts TIMESTAMP,
        payment_method VARCHAR(30),
        total_amount DECIMAL(12,2)
    );

    CREATE TABLE pos_transaction_line (
        txn_id VARCHAR(20) REFERENCES pos_transaction(txn_id),
        line_no INTEGER,
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        qty INTEGER,
        unit_price DECIMAL(10,2),
        discount_amount DECIMAL(10,2) DEFAULT 0,
        tax_amount DECIMAL(10,2) DEFAULT 0,
        PRIMARY KEY (txn_id, line_no)
    );

    CREATE TABLE purchase_order (
        po_id VARCHAR(20) PRIMARY KEY,
        supplier_id VARCHAR(20) REFERENCES supplier(supplier_id),
        dc_id VARCHAR(20) REFERENCES dc(dc_id),
        order_date DATE,
        expected_date DATE,
        status VARCHAR(30)
    );

    CREATE TABLE purchase_order_line (
        po_id VARCHAR(20) REFERENCES purchase_order(po_id),
        line_no INTEGER,
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        qty_ordered INTEGER,
        unit_cost DECIMAL(10,2),
        PRIMARY KEY (po_id, line_no)
    );

    CREATE TABLE goods_receipt (
        grn_id VARCHAR(20) PRIMARY KEY,
        po_id VARCHAR(20) REFERENCES purchase_order(po_id),
        received_date DATE,
        status VARCHAR(30)
    );

    CREATE TABLE goods_receipt_line (
        grn_id VARCHAR(20) REFERENCES goods_receipt(grn_id),
        line_no INTEGER,
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        qty_received INTEGER,
        qty_damaged INTEGER DEFAULT 0,
        PRIMARY KEY (grn_id, line_no)
    );

    CREATE TABLE return (
        return_id VARCHAR(20) PRIMARY KEY,
        txn_id VARCHAR(20) REFERENCES pos_transaction(txn_id),
        store_id VARCHAR(20) REFERENCES store(store_id),
        return_ts TIMESTAMP,
        reason_code VARCHAR(50)
    );

    CREATE TABLE return_line (
        return_id VARCHAR(20) REFERENCES return(return_id),
        line_no INTEGER,
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        qty INTEGER,
        refund_amount DECIMAL(10,2),
        PRIMARY KEY (return_id, line_no)
    );

    CREATE TABLE transfer_order (
        to_id VARCHAR(20) PRIMARY KEY,
        from_dc_id VARCHAR(20) REFERENCES dc(dc_id),
        to_store_id VARCHAR(20) REFERENCES store(store_id),
        ship_date DATE,
        status VARCHAR(30)
    );

    CREATE TABLE transfer_order_line (
        to_id VARCHAR(20) REFERENCES transfer_order(to_id),
        line_no INTEGER,
        sku_id VARCHAR(20) REFERENCES sku(sku_id),
        qty_shipped INTEGER,
        qty_received INTEGER,
        PRIMARY KEY (to_id, line_no)
    );

    -- Create useful views for agents
    CREATE OR REPLACE VIEW v_sales_summary AS
    SELECT
        s.store_id, s.name as store_name, s.region,
        DATE(t.txn_ts) as sale_date,
        COUNT(DISTINCT t.txn_id) as transaction_count,
        SUM(t.total_amount) as total_revenue,
        SUM(tl.qty) as units_sold
    FROM pos_transaction t
    JOIN store s ON t.store_id = s.store_id
    JOIN pos_transaction_line tl ON t.txn_id = tl.txn_id
    GROUP BY s.store_id, s.name, s.region, DATE(t.txn_ts);

    CREATE OR REPLACE VIEW v_inventory_status AS
    SELECT
        s.store_id, s.name as store_name,
        sk.sku_id, p.product_name,
        si.on_hand_qty, si.in_transit_qty, si.reorder_point,
        CASE WHEN si.on_hand_qty <= si.reorder_point THEN 'LOW' ELSE 'OK' END as stock_status
    FROM store_inventory si
    JOIN store s ON si.store_id = s.store_id
    JOIN sku sk ON si.sku_id = sk.sku_id
    JOIN product p ON sk.product_id = p.product_id;
    """

    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("Schema created.")


def load_table(conn, table_name: str, excel_file: Path):
    """Load data from Excel into table."""
    if not excel_file.exists():
        print(f"  Skipping {table_name} - file not found")
        return 0

    df = pd.read_excel(excel_file)
    if df.empty:
        print(f"  Skipping {table_name} - no data")
        return 0

    # Convert column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    # Build INSERT statement
    columns = ", ".join(df.columns)
    placeholders = ", ".join(["%s"] * len(df.columns))

    insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    # Batch insert for better performance
    success_count = 0
    batch_size = 100
    rows = []

    for _, row in df.iterrows():
        values = tuple(None if pd.isna(v) else v for v in row.values)
        rows.append(values)

        if len(rows) >= batch_size:
            try:
                with conn.cursor() as cur:
                    cur.executemany(insert_sql, rows)
                conn.commit()
                success_count += len(rows)
            except Exception as e:
                conn.rollback()
                print(f"    Batch error: {e}")
            rows = []

    # Insert remaining rows
    if rows:
        try:
            with conn.cursor() as cur:
                cur.executemany(insert_sql, rows)
            conn.commit()
            success_count += len(rows)
        except Exception as e:
            conn.rollback()
            print(f"    Final batch error: {e}")

    print(f"  Loaded {success_count} rows into {table_name}")
    return success_count


def update_dates(conn):
    """Update transaction dates to be recent (for data freshness)."""
    print("\nUpdating dates to be recent...")

    try:
        with conn.cursor() as cur:
            # Get the most recent transaction date
            cur.execute("SELECT MAX(txn_ts) FROM pos_transaction")
            max_date = cur.fetchone()[0]

            if max_date:
                # Calculate days to shift
                today = datetime.now()
                days_diff = (today - max_date).days - 7  # Make data 7 days old

                if days_diff > 0:
                    print(f"  Shifting dates forward by {days_diff} days...")

                    # Update all date columns
                    cur.execute(f"UPDATE pos_transaction SET txn_ts = txn_ts + INTERVAL '{days_diff} days'")
                    cur.execute(f"UPDATE purchase_order SET order_date = order_date + INTERVAL '{days_diff} days', expected_date = expected_date + INTERVAL '{days_diff} days'")
                    cur.execute(f"UPDATE goods_receipt SET received_date = received_date + INTERVAL '{days_diff} days'")
                    cur.execute(f"UPDATE return SET return_ts = return_ts + INTERVAL '{days_diff} days'")
                    cur.execute(f"UPDATE transfer_order SET ship_date = ship_date + INTERVAL '{days_diff} days'")
                    cur.execute(f"UPDATE promotion SET start_date = start_date + INTERVAL '{days_diff} days', end_date = end_date + INTERVAL '{days_diff} days'")
                    cur.execute(f"UPDATE price SET effective_start = effective_start + INTERVAL '{days_diff} days', effective_end = effective_end + INTERVAL '{days_diff} days'")
                    cur.execute(f"UPDATE price_list SET effective_start = effective_start + INTERVAL '{days_diff} days', effective_end = effective_end + INTERVAL '{days_diff} days'")

                    conn.commit()
                    print(f"  Dates updated!")
                else:
                    print("  Data is already recent, no update needed.")
            else:
                print("  No transactions found to update.")
    except Exception as e:
        conn.rollback()
        print(f"  Error updating dates: {e}")


def main():
    print("=" * 60)
    print("Boardroom-in-a-Box: Database Setup")
    print("=" * 60)
    print(f"\nConnecting to: {DB_CONFIG['host']}/{DB_CONFIG['database']}")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("Connected successfully!\n")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    try:
        # Create schema
        create_schema(conn)

        # Load tables in order (respect foreign keys)
        print("\nLoading data...")
        tables = [
            ("brand", "BRAND.xlsx"),
            ("product_category", "PRODUCT_CATEGORY.xlsx"),
            ("product", "PRODUCT.xlsx"),
            ("store", "STORE.xlsx"),
            ("dc", "DC.xlsx"),
            ("customer", "CUSTOMER.xlsx"),
            ("supplier", "SUPPLIER.xlsx"),
            ("sku", "SKU.xlsx"),
            ("supplier_product", "SUPPLIER_PRODUCT.xlsx"),
            ("store_inventory", "STORE_INVENTORY.xlsx"),
            ("dc_inventory", "DC_INVENTORY.xlsx"),
            ("price_list", "PRICE_LIST.xlsx"),
            ("price", "PRICE.xlsx"),
            ("promotion", "PROMOTION.xlsx"),
            ("promotion_sku", "PROMOTION_SKU.xlsx"),
            ("pos_transaction", "POS_TRANSACTION.xlsx"),
            ("pos_transaction_line", "POS_TRANSACTION_LINE.xlsx"),
            ("purchase_order", "PURCHASE_ORDER.xlsx"),
            ("purchase_order_line", "PURCHASE_ORDER_LINE.xlsx"),
            ("goods_receipt", "GOODS_RECEIPT.xlsx"),
            ("goods_receipt_line", "GOODS_RECEIPT_LINE.xlsx"),
            ("return", "RETURN.xlsx"),
            ("return_line", "RETURN_LINE.xlsx"),
            ("transfer_order", "TRANSFER_ORDER.xlsx"),
            ("transfer_order_line", "TRANSFER_ORDER_LINE.xlsx"),
        ]

        total_rows = 0
        for table_name, file_name in tables:
            total_rows += load_table(conn, table_name, DATA_DIR / file_name)

        # Update dates to be recent
        update_dates(conn)

        print("\n" + "=" * 60)
        print(f"Database setup complete! Loaded {total_rows} total rows.")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
