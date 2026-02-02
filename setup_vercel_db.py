#!/usr/bin/env python3
"""
Setup Vercel Postgres Database
==============================
Loads the retail ERP schema and data into a cloud Postgres database.

Usage:
    1. Set environment variables:
       export DB_HOST=your-host.postgres.vercel-storage.com
       export DB_NAME=verceldb
       export DB_USER=default
       export DB_PASSWORD=your-password
       export DB_SSLMODE=require

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
    """Create database schema."""
    print("Creating schema...")

    schema_sql = """
    -- Drop existing tables
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
    DROP TABLE IF EXISTS sku CASCADE;
    DROP TABLE IF EXISTS supplier_product CASCADE;
    DROP TABLE IF EXISTS supplier CASCADE;
    DROP TABLE IF EXISTS product CASCADE;
    DROP TABLE IF EXISTS product_category CASCADE;
    DROP TABLE IF EXISTS brand CASCADE;
    DROP TABLE IF EXISTS dc CASCADE;
    DROP TABLE IF EXISTS store CASCADE;
    DROP TABLE IF EXISTS customer CASCADE;

    -- Create tables
    CREATE TABLE brand (
        brand_id SERIAL PRIMARY KEY,
        brand_name VARCHAR(100) NOT NULL
    );

    CREATE TABLE product_category (
        category_id SERIAL PRIMARY KEY,
        category_name VARCHAR(100) NOT NULL,
        parent_category_id INTEGER REFERENCES product_category(category_id)
    );

    CREATE TABLE product (
        product_id SERIAL PRIMARY KEY,
        product_name VARCHAR(200) NOT NULL,
        brand_id INTEGER REFERENCES brand(brand_id),
        category_id INTEGER REFERENCES product_category(category_id),
        unit_cost DECIMAL(10,2),
        unit_price DECIMAL(10,2)
    );

    CREATE TABLE store (
        store_id SERIAL PRIMARY KEY,
        store_name VARCHAR(100) NOT NULL,
        city VARCHAR(100),
        state VARCHAR(50),
        region VARCHAR(50)
    );

    CREATE TABLE dc (
        dc_id SERIAL PRIMARY KEY,
        dc_name VARCHAR(100) NOT NULL,
        city VARCHAR(100),
        state VARCHAR(50)
    );

    CREATE TABLE customer (
        customer_id SERIAL PRIMARY KEY,
        first_name VARCHAR(50),
        last_name VARCHAR(50),
        email VARCHAR(100),
        loyalty_tier VARCHAR(20),
        created_date DATE
    );

    CREATE TABLE supplier (
        supplier_id SERIAL PRIMARY KEY,
        supplier_name VARCHAR(100) NOT NULL,
        lead_time_days INTEGER
    );

    CREATE TABLE supplier_product (
        supplier_id INTEGER REFERENCES supplier(supplier_id),
        product_id INTEGER REFERENCES product(product_id),
        supplier_cost DECIMAL(10,2),
        PRIMARY KEY (supplier_id, product_id)
    );

    CREATE TABLE sku (
        sku_id SERIAL PRIMARY KEY,
        product_id INTEGER REFERENCES product(product_id),
        sku_code VARCHAR(50) UNIQUE,
        size VARCHAR(20),
        color VARCHAR(30)
    );

    CREATE TABLE store_inventory (
        store_id INTEGER REFERENCES store(store_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        quantity_on_hand INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (store_id, sku_id)
    );

    CREATE TABLE dc_inventory (
        dc_id INTEGER REFERENCES dc(dc_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        quantity_on_hand INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (dc_id, sku_id)
    );

    CREATE TABLE price_list (
        price_list_id SERIAL PRIMARY KEY,
        price_list_name VARCHAR(100),
        effective_date DATE,
        end_date DATE
    );

    CREATE TABLE price (
        price_id SERIAL PRIMARY KEY,
        sku_id INTEGER REFERENCES sku(sku_id),
        price_list_id INTEGER REFERENCES price_list(price_list_id),
        unit_price DECIMAL(10,2),
        effective_date DATE,
        end_date DATE
    );

    CREATE TABLE promotion (
        promotion_id SERIAL PRIMARY KEY,
        promotion_name VARCHAR(100),
        discount_percent DECIMAL(5,2),
        start_date DATE,
        end_date DATE
    );

    CREATE TABLE promotion_sku (
        promotion_id INTEGER REFERENCES promotion(promotion_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        PRIMARY KEY (promotion_id, sku_id)
    );

    CREATE TABLE pos_transaction (
        transaction_id SERIAL PRIMARY KEY,
        store_id INTEGER REFERENCES store(store_id),
        customer_id INTEGER REFERENCES customer(customer_id),
        transaction_date TIMESTAMP,
        total_amount DECIMAL(12,2),
        payment_method VARCHAR(30)
    );

    CREATE TABLE pos_transaction_line (
        line_id SERIAL PRIMARY KEY,
        transaction_id INTEGER REFERENCES pos_transaction(transaction_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        quantity INTEGER,
        unit_price DECIMAL(10,2),
        discount_amount DECIMAL(10,2) DEFAULT 0,
        line_total DECIMAL(12,2)
    );

    CREATE TABLE purchase_order (
        po_id SERIAL PRIMARY KEY,
        supplier_id INTEGER REFERENCES supplier(supplier_id),
        dc_id INTEGER REFERENCES dc(dc_id),
        order_date DATE,
        expected_date DATE,
        status VARCHAR(30)
    );

    CREATE TABLE purchase_order_line (
        line_id SERIAL PRIMARY KEY,
        po_id INTEGER REFERENCES purchase_order(po_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        quantity INTEGER,
        unit_cost DECIMAL(10,2)
    );

    CREATE TABLE goods_receipt (
        receipt_id SERIAL PRIMARY KEY,
        po_id INTEGER REFERENCES purchase_order(po_id),
        dc_id INTEGER REFERENCES dc(dc_id),
        receipt_date DATE
    );

    CREATE TABLE goods_receipt_line (
        line_id SERIAL PRIMARY KEY,
        receipt_id INTEGER REFERENCES goods_receipt(receipt_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        quantity_received INTEGER
    );

    CREATE TABLE return (
        return_id SERIAL PRIMARY KEY,
        transaction_id INTEGER REFERENCES pos_transaction(transaction_id),
        store_id INTEGER REFERENCES store(store_id),
        return_date DATE,
        reason VARCHAR(100)
    );

    CREATE TABLE return_line (
        line_id SERIAL PRIMARY KEY,
        return_id INTEGER REFERENCES return(return_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        quantity INTEGER,
        refund_amount DECIMAL(10,2)
    );

    CREATE TABLE transfer_order (
        transfer_id SERIAL PRIMARY KEY,
        from_dc_id INTEGER REFERENCES dc(dc_id),
        to_store_id INTEGER REFERENCES store(store_id),
        transfer_date DATE,
        status VARCHAR(30)
    );

    CREATE TABLE transfer_order_line (
        line_id SERIAL PRIMARY KEY,
        transfer_id INTEGER REFERENCES transfer_order(transfer_id),
        sku_id INTEGER REFERENCES sku(sku_id),
        quantity INTEGER
    );
    """

    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("Schema created.")


def load_table(conn, table_name: str, excel_file: Path):
    """Load data from Excel into table."""
    if not excel_file.exists():
        print(f"  Skipping {table_name} - file not found")
        return

    df = pd.read_excel(excel_file)
    if df.empty:
        print(f"  Skipping {table_name} - no data")
        return

    # Convert column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    # Build INSERT statement
    columns = ", ".join(df.columns)
    placeholders = ", ".join(["%s"] * len(df.columns))

    insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

    # Insert rows
    with conn.cursor() as cur:
        for _, row in df.iterrows():
            values = [None if pd.isna(v) else v for v in row.values]
            try:
                cur.execute(insert_sql, values)
            except Exception as e:
                print(f"    Error inserting row: {e}")

    conn.commit()
    print(f"  Loaded {len(df)} rows into {table_name}")


def update_dates(conn):
    """Update transaction dates to be recent (for data freshness)."""
    print("Updating dates to be recent...")

    with conn.cursor() as cur:
        # Get the most recent transaction date
        cur.execute("SELECT MAX(transaction_date) FROM pos_transaction")
        max_date = cur.fetchone()[0]

        if max_date:
            # Calculate days to shift
            today = datetime.now()
            days_diff = (today - max_date).days - 7  # Make data 7 days old

            if days_diff > 0:
                # Update all date columns
                cur.execute(f"UPDATE pos_transaction SET transaction_date = transaction_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE purchase_order SET order_date = order_date + INTERVAL '{days_diff} days', expected_date = expected_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE goods_receipt SET receipt_date = receipt_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE return SET return_date = return_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE transfer_order SET transfer_date = transfer_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE promotion SET start_date = start_date + INTERVAL '{days_diff} days', end_date = end_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE price SET effective_date = effective_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE price_list SET effective_date = effective_date + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE store_inventory SET last_updated = last_updated + INTERVAL '{days_diff} days'")
                cur.execute(f"UPDATE dc_inventory SET last_updated = last_updated + INTERVAL '{days_diff} days'")

                print(f"  Shifted dates forward by {days_diff} days")

    conn.commit()


def main():
    print("=" * 60)
    print("Boardroom-in-a-Box: Database Setup")
    print("=" * 60)
    print(f"\nConnecting to: {DB_CONFIG['host']}/{DB_CONFIG['database']}")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("Connected successfully!")
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
            ("supplier_product", "SUPPLIER_PRODUCT.xlsx"),
            ("sku", "SKU.xlsx"),
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

        for table_name, file_name in tables:
            load_table(conn, table_name, DATA_DIR / file_name)

        # Update dates to be recent
        update_dates(conn)

        print("\n" + "=" * 60)
        print("Database setup complete!")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
