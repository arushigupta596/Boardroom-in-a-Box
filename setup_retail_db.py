#!/usr/bin/env python3
"""
Retail ERP Database Setup Script
Creates PostgreSQL schema, tables, and loads data from Excel files.
"""

import pandas as pd
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine
import os
from pathlib import Path

# Database connection parameters - adjust as needed
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'postgres',  # Connect to default database first
    'user': 'arushigupta',
    'password': ''  # Empty for local peer auth
}

# Target database name
TARGET_DB = 'retail_erp'

# Path to Excel files
EXCEL_DIR = Path(__file__).parent / 'data' / 'retail_erp_excel_tables'

# SQL for creating schema and tables
SCHEMA_SQL = """
-- ============================================================
-- Retail ERP Schema (PostgreSQL)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS retail;

-- ----------------------------
-- MASTER / CATALOG
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.brand (
  brand_id    TEXT PRIMARY KEY,
  brand_name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retail.product_category (
  category_id         TEXT PRIMARY KEY,
  parent_category_id  TEXT NULL REFERENCES retail.product_category(category_id) ON DELETE SET NULL,
  category_name       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retail.product (
  product_id    TEXT PRIMARY KEY,
  brand_id      TEXT NOT NULL REFERENCES retail.brand(brand_id) ON UPDATE CASCADE,
  category_id   TEXT NOT NULL REFERENCES retail.product_category(category_id) ON UPDATE CASCADE,
  product_name  TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE IF NOT EXISTS retail.sku (
  sku_id     TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES retail.product(product_id) ON UPDATE CASCADE,
  upc        TEXT,
  uom        TEXT,
  pack_size  TEXT,
  status     TEXT NOT NULL DEFAULT 'ACTIVE'
);

CREATE INDEX IF NOT EXISTS idx_product_brand   ON retail.product(brand_id);
CREATE INDEX IF NOT EXISTS idx_product_category ON retail.product(category_id);
CREATE INDEX IF NOT EXISTS idx_sku_product     ON retail.sku(product_id);

-- ----------------------------
-- SUPPLIERS & PROCUREMENT
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.supplier (
  supplier_id     TEXT PRIMARY KEY,
  supplier_name   TEXT NOT NULL,
  lead_time_days  INTEGER NOT NULL CHECK (lead_time_days >= 0),
  payment_terms   TEXT
);

CREATE TABLE IF NOT EXISTS retail.supplier_product (
  supplier_id        TEXT NOT NULL REFERENCES retail.supplier(supplier_id) ON UPDATE CASCADE ON DELETE CASCADE,
  sku_id             TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE ON DELETE CASCADE,
  supplier_sku_code  TEXT,
  cost               NUMERIC(12,2) NOT NULL CHECK (cost >= 0),
  moq                INTEGER NOT NULL CHECK (moq >= 0),
  PRIMARY KEY (supplier_id, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_supplier_product_sku ON retail.supplier_product(sku_id);

-- ----------------------------
-- LOCATIONS (DC / STORE)
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.dc (
  dc_id     TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  location  TEXT
);

CREATE TABLE IF NOT EXISTS retail.store (
  store_id      TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  city          TEXT,
  region        TEXT,
  store_format  TEXT
);

-- ----------------------------
-- PROCUREMENT: PO + GRN
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.purchase_order (
  po_id          TEXT PRIMARY KEY,
  supplier_id    TEXT NOT NULL REFERENCES retail.supplier(supplier_id) ON UPDATE CASCADE,
  dc_id          TEXT NOT NULL REFERENCES retail.dc(dc_id) ON UPDATE CASCADE,
  order_date     DATE NOT NULL,
  expected_date  DATE,
  status         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retail.purchase_order_line (
  po_id         TEXT NOT NULL REFERENCES retail.purchase_order(po_id) ON UPDATE CASCADE ON DELETE CASCADE,
  line_no       INTEGER NOT NULL,
  sku_id        TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE,
  qty_ordered   INTEGER NOT NULL CHECK (qty_ordered >= 0),
  unit_cost     NUMERIC(12,2) NOT NULL CHECK (unit_cost >= 0),
  PRIMARY KEY (po_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_po_supplier   ON retail.purchase_order(supplier_id);
CREATE INDEX IF NOT EXISTS idx_po_dc         ON retail.purchase_order(dc_id);
CREATE INDEX IF NOT EXISTS idx_pol_sku       ON retail.purchase_order_line(sku_id);

CREATE TABLE IF NOT EXISTS retail.goods_receipt (
  grn_id         TEXT PRIMARY KEY,
  po_id          TEXT NOT NULL REFERENCES retail.purchase_order(po_id) ON UPDATE CASCADE ON DELETE CASCADE,
  received_date  DATE NOT NULL,
  status         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retail.goods_receipt_line (
  grn_id        TEXT NOT NULL REFERENCES retail.goods_receipt(grn_id) ON UPDATE CASCADE ON DELETE CASCADE,
  line_no       INTEGER NOT NULL,
  sku_id        TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE,
  qty_received  INTEGER NOT NULL CHECK (qty_received >= 0),
  qty_damaged   INTEGER NOT NULL DEFAULT 0 CHECK (qty_damaged >= 0),
  PRIMARY KEY (grn_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_grn_po       ON retail.goods_receipt(po_id);
CREATE INDEX IF NOT EXISTS idx_grnl_sku     ON retail.goods_receipt_line(sku_id);

-- ----------------------------
-- INVENTORY (DC + STORE)
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.dc_inventory (
  dc_id        TEXT NOT NULL REFERENCES retail.dc(dc_id) ON UPDATE CASCADE ON DELETE CASCADE,
  sku_id       TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE ON DELETE CASCADE,
  on_hand_qty  INTEGER NOT NULL DEFAULT 0 CHECK (on_hand_qty >= 0),
  reserved_qty INTEGER NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),
  PRIMARY KEY (dc_id, sku_id)
);

CREATE TABLE IF NOT EXISTS retail.store_inventory (
  store_id        TEXT NOT NULL REFERENCES retail.store(store_id) ON UPDATE CASCADE ON DELETE CASCADE,
  sku_id          TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE ON DELETE CASCADE,
  on_hand_qty     INTEGER NOT NULL DEFAULT 0 CHECK (on_hand_qty >= 0),
  in_transit_qty  INTEGER NOT NULL DEFAULT 0 CHECK (in_transit_qty >= 0),
  reorder_point   INTEGER NOT NULL DEFAULT 0 CHECK (reorder_point >= 0),
  PRIMARY KEY (store_id, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_store_inventory_sku ON retail.store_inventory(sku_id);

-- ----------------------------
-- TRANSFERS (DC -> STORE)
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.transfer_order (
  to_id        TEXT PRIMARY KEY,
  from_dc_id   TEXT NOT NULL REFERENCES retail.dc(dc_id) ON UPDATE CASCADE,
  to_store_id  TEXT NOT NULL REFERENCES retail.store(store_id) ON UPDATE CASCADE,
  ship_date    DATE NOT NULL,
  status       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retail.transfer_order_line (
  to_id          TEXT NOT NULL REFERENCES retail.transfer_order(to_id) ON UPDATE CASCADE ON DELETE CASCADE,
  line_no        INTEGER NOT NULL,
  sku_id         TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE,
  qty_shipped    INTEGER NOT NULL CHECK (qty_shipped >= 0),
  qty_received   INTEGER NOT NULL DEFAULT 0 CHECK (qty_received >= 0),
  PRIMARY KEY (to_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_to_fromdc     ON retail.transfer_order(from_dc_id);
CREATE INDEX IF NOT EXISTS idx_to_tostore    ON retail.transfer_order(to_store_id);
CREATE INDEX IF NOT EXISTS idx_tol_sku       ON retail.transfer_order_line(sku_id);

-- ----------------------------
-- PRICING & PROMOTIONS
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.price_list (
  price_list_id   TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  currency        TEXT NOT NULL,
  effective_start DATE NOT NULL,
  effective_end   DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS retail.price (
  price_id        SERIAL PRIMARY KEY,
  price_list_id   TEXT NOT NULL REFERENCES retail.price_list(price_list_id) ON UPDATE CASCADE ON DELETE CASCADE,
  sku_id          TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE ON DELETE CASCADE,
  store_id        TEXT NULL REFERENCES retail.store(store_id) ON UPDATE CASCADE ON DELETE CASCADE,
  price           NUMERIC(12,2) NOT NULL CHECK (price >= 0),
  effective_start DATE NOT NULL,
  effective_end   DATE NOT NULL,
  UNIQUE NULLS NOT DISTINCT (price_list_id, sku_id, effective_start, store_id)
);

CREATE INDEX IF NOT EXISTS idx_price_sku          ON retail.price(sku_id);
CREATE INDEX IF NOT EXISTS idx_price_store        ON retail.price(store_id);
CREATE INDEX IF NOT EXISTS idx_price_effective    ON retail.price(effective_start, effective_end);

CREATE TABLE IF NOT EXISTS retail.promotion (
  promo_id    TEXT PRIMARY KEY,
  promo_name  TEXT NOT NULL,
  type        TEXT NOT NULL,
  start_date  DATE NOT NULL,
  end_date    DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS retail.promotion_sku (
  promo_id        TEXT NOT NULL REFERENCES retail.promotion(promo_id) ON UPDATE CASCADE ON DELETE CASCADE,
  sku_id          TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE ON DELETE CASCADE,
  discount_type   TEXT NOT NULL,
  discount_value  NUMERIC(12,2) NOT NULL CHECK (discount_value >= 0),
  PRIMARY KEY (promo_id, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_promo_sku_sku ON retail.promotion_sku(sku_id);

-- ----------------------------
-- CUSTOMER / POS / RETURNS
-- ----------------------------

CREATE TABLE IF NOT EXISTS retail.customer (
  customer_id  TEXT PRIMARY KEY,
  loyalty_id   TEXT,
  segment      TEXT
);

CREATE TABLE IF NOT EXISTS retail.pos_transaction (
  txn_id         TEXT PRIMARY KEY,
  store_id       TEXT NOT NULL REFERENCES retail.store(store_id) ON UPDATE CASCADE,
  customer_id    TEXT NULL REFERENCES retail.customer(customer_id) ON UPDATE CASCADE,
  txn_ts         TIMESTAMPTZ NOT NULL,
  payment_method TEXT NOT NULL,
  total_amount   NUMERIC(14,2) NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE IF NOT EXISTS retail.pos_transaction_line (
  txn_id           TEXT NOT NULL REFERENCES retail.pos_transaction(txn_id) ON UPDATE CASCADE ON DELETE CASCADE,
  line_no          INTEGER NOT NULL,
  sku_id           TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE,
  qty              INTEGER NOT NULL CHECK (qty > 0),
  unit_price       NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
  discount_amount  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
  tax_amount       NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
  PRIMARY KEY (txn_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_pos_store      ON retail.pos_transaction(store_id);
CREATE INDEX IF NOT EXISTS idx_pos_customer   ON retail.pos_transaction(customer_id);
CREATE INDEX IF NOT EXISTS idx_pos_ts         ON retail.pos_transaction(txn_ts);
CREATE INDEX IF NOT EXISTS idx_posl_sku       ON retail.pos_transaction_line(sku_id);

CREATE TABLE IF NOT EXISTS retail.return (
  return_id   TEXT PRIMARY KEY,
  txn_id      TEXT NOT NULL REFERENCES retail.pos_transaction(txn_id) ON UPDATE CASCADE ON DELETE CASCADE,
  store_id    TEXT NOT NULL REFERENCES retail.store(store_id) ON UPDATE CASCADE,
  return_ts   TIMESTAMPTZ NOT NULL,
  reason_code TEXT
);

CREATE TABLE IF NOT EXISTS retail.return_line (
  return_id     TEXT NOT NULL REFERENCES retail.return(return_id) ON UPDATE CASCADE ON DELETE CASCADE,
  line_no       INTEGER NOT NULL,
  sku_id        TEXT NOT NULL REFERENCES retail.sku(sku_id) ON UPDATE CASCADE,
  qty           INTEGER NOT NULL CHECK (qty > 0),
  refund_amount NUMERIC(14,2) NOT NULL CHECK (refund_amount >= 0),
  PRIMARY KEY (return_id, line_no)
);

CREATE INDEX IF NOT EXISTS idx_return_txn   ON retail.return(txn_id);
CREATE INDEX IF NOT EXISTS idx_return_store ON retail.return(store_id);
CREATE INDEX IF NOT EXISTS idx_return_ts    ON retail.return(return_ts);
CREATE INDEX IF NOT EXISTS idx_returnl_sku  ON retail.return_line(sku_id);
"""

# Mapping of Excel files to table names (in load order to respect foreign keys)
TABLE_LOAD_ORDER = [
    # Master data first
    ('BRAND.xlsx', 'brand'),
    ('PRODUCT_CATEGORY.xlsx', 'product_category'),
    ('PRODUCT.xlsx', 'product'),
    ('SKU.xlsx', 'sku'),

    # Suppliers
    ('SUPPLIER.xlsx', 'supplier'),
    ('SUPPLIER_PRODUCT.xlsx', 'supplier_product'),

    # Locations
    ('DC.xlsx', 'dc'),
    ('STORE.xlsx', 'store'),

    # Procurement
    ('PURCHASE_ORDER.xlsx', 'purchase_order'),
    ('PURCHASE_ORDER_LINE.xlsx', 'purchase_order_line'),
    ('GOODS_RECEIPT.xlsx', 'goods_receipt'),
    ('GOODS_RECEIPT_LINE.xlsx', 'goods_receipt_line'),

    # Inventory
    ('DC_INVENTORY.xlsx', 'dc_inventory'),
    ('STORE_INVENTORY.xlsx', 'store_inventory'),

    # Transfers
    ('TRANSFER_ORDER.xlsx', 'transfer_order'),
    ('TRANSFER_ORDER_LINE.xlsx', 'transfer_order_line'),

    # Pricing
    ('PRICE_LIST.xlsx', 'price_list'),
    ('PRICE.xlsx', 'price'),
    ('PROMOTION.xlsx', 'promotion'),
    ('PROMOTION_SKU.xlsx', 'promotion_sku'),

    # Customer/POS
    ('CUSTOMER.xlsx', 'customer'),
    ('POS_TRANSACTION.xlsx', 'pos_transaction'),
    ('POS_TRANSACTION_LINE.xlsx', 'pos_transaction_line'),
    ('RETURN.xlsx', 'return'),
    ('RETURN_LINE.xlsx', 'return_line'),
]


def create_database(config, db_name):
    """Create the target database if it doesn't exist."""
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    cur = conn.cursor()

    # Check if database exists
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = cur.fetchone()

    if not exists:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        print(f"Created database: {db_name}")
    else:
        print(f"Database {db_name} already exists")

    cur.close()
    conn.close()


def create_schema_and_tables(config, db_name):
    """Create the retail schema and all tables."""
    conn_config = config.copy()
    conn_config['database'] = db_name

    conn = psycopg2.connect(**conn_config)
    conn.autocommit = True
    cur = conn.cursor()

    # Execute schema creation SQL
    cur.execute(SCHEMA_SQL)
    print("Created schema and tables successfully")

    cur.close()
    conn.close()


def load_excel_data(config, db_name, excel_dir):
    """Load data from Excel files into PostgreSQL tables."""
    conn_config = config.copy()
    conn_config['database'] = db_name

    # Create SQLAlchemy engine for pandas
    engine_url = f"postgresql://{conn_config['user']}:{conn_config['password']}@{conn_config['host']}:{conn_config['port']}/{conn_config['database']}"
    engine = create_engine(engine_url)

    for excel_file, table_name in TABLE_LOAD_ORDER:
        file_path = excel_dir / excel_file

        if not file_path.exists():
            print(f"Warning: {excel_file} not found, skipping...")
            continue

        print(f"Loading {excel_file} into retail.{table_name}...")

        try:
            # Read Excel file
            df = pd.read_excel(file_path)

            # Convert column names to lowercase (PostgreSQL convention)
            df.columns = [col.lower() for col in df.columns]

            # Handle special cases for datetime columns
            for col in df.columns:
                if 'date' in col or col.endswith('_ts'):
                    df[col] = pd.to_datetime(df[col], errors='coerce')

            # Remove duplicates based on primary key columns
            pk_columns = {
                'brand': ['brand_id'],
                'product_category': ['category_id'],
                'product': ['product_id'],
                'sku': ['sku_id'],
                'supplier': ['supplier_id'],
                'supplier_product': ['supplier_id', 'sku_id'],
                'dc': ['dc_id'],
                'store': ['store_id'],
                'purchase_order': ['po_id'],
                'purchase_order_line': ['po_id', 'line_no'],
                'goods_receipt': ['grn_id'],
                'goods_receipt_line': ['grn_id', 'line_no'],
                'dc_inventory': ['dc_id', 'sku_id'],
                'store_inventory': ['store_id', 'sku_id'],
                'transfer_order': ['to_id'],
                'transfer_order_line': ['to_id', 'line_no'],
                'price_list': ['price_list_id'],
                'price': ['price_list_id', 'sku_id', 'effective_start', 'store_id'],
                'promotion': ['promo_id'],
                'promotion_sku': ['promo_id', 'sku_id'],
                'customer': ['customer_id'],
                'pos_transaction': ['txn_id'],
                'pos_transaction_line': ['txn_id', 'line_no'],
                'return': ['return_id'],
                'return_line': ['return_id', 'line_no'],
            }

            if table_name in pk_columns:
                original_len = len(df)
                df = df.drop_duplicates(subset=pk_columns[table_name], keep='first')
                if len(df) < original_len:
                    print(f"  Removed {original_len - len(df)} duplicate rows")

            # Load data into table
            df.to_sql(
                table_name,
                engine,
                schema='retail',
                if_exists='append',
                index=False,
                method='multi'
            )

            print(f"  Loaded {len(df)} rows into retail.{table_name}")

        except Exception as e:
            print(f"  Error loading {excel_file}: {e}")
            raise


def verify_data(config, db_name):
    """Verify data was loaded by counting rows in each table."""
    conn_config = config.copy()
    conn_config['database'] = db_name

    conn = psycopg2.connect(**conn_config)
    cur = conn.cursor()

    print("\n--- Data Verification ---")

    for _, table_name in TABLE_LOAD_ORDER:
        cur.execute(f"SELECT COUNT(*) FROM retail.{table_name}")
        count = cur.fetchone()[0]
        print(f"retail.{table_name}: {count} rows")

    cur.close()
    conn.close()


def main():
    print("=" * 60)
    print("Retail ERP Database Setup")
    print("=" * 60)

    # Step 1: Create database
    print("\n1. Creating database...")
    create_database(DB_CONFIG, TARGET_DB)

    # Step 2: Create schema and tables
    print("\n2. Creating schema and tables...")
    create_schema_and_tables(DB_CONFIG, TARGET_DB)

    # Step 3: Load data from Excel files
    print("\n3. Loading data from Excel files...")
    load_excel_data(DB_CONFIG, TARGET_DB, EXCEL_DIR)

    # Step 4: Verify data
    print("\n4. Verifying loaded data...")
    verify_data(DB_CONFIG, TARGET_DB)

    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
