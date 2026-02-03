-- Supabase Schema for Boardroom-in-a-Box
-- Run this in: https://supabase.com/dashboard/project/nqeseybqwlnntnkrlyxc/sql

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
DROP TABLE IF EXISTS supplier_product CASCADE;
DROP TABLE IF EXISTS sku CASCADE;
DROP TABLE IF EXISTS supplier CASCADE;
DROP TABLE IF EXISTS product CASCADE;
DROP TABLE IF EXISTS product_category CASCADE;
DROP TABLE IF EXISTS brand CASCADE;
DROP TABLE IF EXISTS dc CASCADE;
DROP TABLE IF EXISTS store CASCADE;
DROP TABLE IF EXISTS customer CASCADE;

-- Create tables (all IDs are VARCHAR to match Excel data with prefixes like B60227, CU682357, etc.)

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
    pack_size VARCHAR(20),
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

-- Enable Row Level Security (optional but recommended)
-- ALTER TABLE brand ENABLE ROW LEVEL SECURITY;
-- etc.

-- Create policies to allow API access (needed for REST API)
-- For simplicity, allow all operations for authenticated users
