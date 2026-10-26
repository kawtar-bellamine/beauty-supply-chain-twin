-- Staging: typed columns, padded zip prefixes, cleaned coordinates.
CREATE OR REPLACE TABLE stg_geo AS
SELECT lpad(geolocation_zip_code_prefix, 5, '0') AS zip,
       median(CAST(geolocation_lat AS DOUBLE)) AS lat,
       median(CAST(geolocation_lng AS DOUBLE)) AS lng
FROM raw_geolocation
WHERE CAST(geolocation_lat AS DOUBLE) BETWEEN -34 AND 6
  AND CAST(geolocation_lng AS DOUBLE) BETWEEN -74 AND -34
GROUP BY 1;

CREATE OR REPLACE TABLE stg_orders AS
SELECT order_id, customer_id, order_status AS status,
       CAST(order_purchase_timestamp AS TIMESTAMP) AS purchased,
       TRY_CAST(order_approved_at AS TIMESTAMP) AS approved,
       TRY_CAST(order_delivered_carrier_date AS TIMESTAMP) AS to_carrier,
       TRY_CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered,
       CAST(order_estimated_delivery_date AS TIMESTAMP) AS promised
FROM raw_orders;

CREATE OR REPLACE TABLE stg_items AS
SELECT order_id, CAST(order_item_id AS INTEGER) AS item, product_id, seller_id,
       CAST(shipping_limit_date AS TIMESTAMP) AS ship_limit,
       CAST(price AS DOUBLE) AS price, CAST(freight_value AS DOUBLE) AS freight
FROM raw_items;

CREATE OR REPLACE TABLE stg_products AS
SELECT p.product_id, coalesce(p.product_category_name, 'unknown') AS category_pt,
       coalesce(t.product_category_name_english, coalesce(p.product_category_name, 'unknown')) AS category,
       TRY_CAST(p.product_weight_g AS DOUBLE) AS weight_g
FROM raw_products p
LEFT JOIN raw_category_translation t ON t.product_category_name = p.product_category_name;

CREATE OR REPLACE TABLE stg_customers AS
SELECT customer_id, lpad(customer_zip_code_prefix, 5, '0') AS zip, customer_state AS state FROM raw_customers;

CREATE OR REPLACE TABLE stg_sellers AS
SELECT seller_id, lpad(seller_zip_code_prefix, 5, '0') AS zip, seller_state AS state FROM raw_sellers;

CREATE OR REPLACE TABLE dim_state AS
SELECT * FROM (VALUES
 ('AC','N'),('AP','N'),('AM','N'),('PA','N'),('RO','N'),('RR','N'),('TO','N'),
 ('AL','NE'),('BA','NE'),('CE','NE'),('MA','NE'),('PB','NE'),('PE','NE'),('PI','NE'),('RN','NE'),('SE','NE'),
 ('DF','CO'),('GO','CO'),('MT','CO'),('MS','CO'),
 ('ES','SE'),('MG','SE'),('RJ','SE'),('SP','SE'),
 ('PR','S'),('RS','S'),('SC','S')) AS t(state, region);
