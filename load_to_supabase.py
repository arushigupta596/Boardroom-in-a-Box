#!/usr/bin/env python3
"""
Load Data to Supabase via REST API
===================================
Uses Supabase REST API to load Excel data.

Usage: python load_to_supabase.py
"""

import os
import sys
from pathlib import Path
import requests
import pandas as pd
from datetime import datetime

# Supabase config
SUPABASE_URL = "https://nqeseybqwlnntnkrlyxc.supabase.co"
SUPABASE_KEY = "sb_secret_HTSJ1WfJGQ46FjC2mAJqTA_KO-YoRjz"  # Service role key

DATA_DIR = Path(__file__).parent / "Data" / "retail_erp_excel_tables"

# Headers for Supabase API
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


def create_table_via_sql(sql):
    """Execute SQL via Supabase SQL endpoint."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    response = requests.post(url, headers=HEADERS, json={"query": sql})
    return response.status_code == 200


def load_table(table_name: str, excel_file: str, batch_size: int = 50):
    """Load data from Excel to Supabase table."""
    file_path = DATA_DIR / excel_file
    if not file_path.exists():
        print(f"  {table_name}: file not found")
        return 0

    df = pd.read_excel(file_path)
    if df.empty:
        print(f"  {table_name}: empty")
        return 0

    # Convert column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    # Convert data to JSON-serializable format
    records = []
    for _, row in df.iterrows():
        record = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                record[col] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                record[col] = val.isoformat()
            else:
                record[col] = val
        records.append(record)

    # Insert in batches
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    total = 0
    errors = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        try:
            response = requests.post(url, headers=HEADERS, json=batch)
            if response.status_code in [200, 201]:
                total += len(batch)
            else:
                errors += 1
                if errors <= 2:
                    print(f"    Error: {response.status_code} - {response.text[:200]}")
        except Exception as e:
            errors += 1
            if errors <= 2:
                print(f"    Exception: {e}")

    print(f"  {table_name}: {total} rows loaded")
    return total


def main():
    print("=" * 60)
    print("Loading Data to Supabase")
    print("=" * 60)
    print(f"URL: {SUPABASE_URL}")

    # First, we need to create tables via Supabase SQL Editor
    print("\n⚠️  IMPORTANT: First create tables in Supabase SQL Editor!")
    print("Go to: https://supabase.com/dashboard/project/nqeseybqwlnntnkrlyxc/sql")
    print("Run the schema SQL from setup_vercel_db.py")
    print()

    input("Press Enter after creating tables...")

    # Load tables in order
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

    total = 0
    for table_name, file_name in tables:
        count = load_table(table_name, file_name)
        total += count

    print(f"\n{'=' * 60}")
    print(f"Done! Loaded {total} total rows")
    print("=" * 60)


if __name__ == "__main__":
    main()
