-- Marts: one row per delivered order line with geography and stage times; beauty orders; daily demand.
CREATE OR REPLACE TABLE fct_order_lines AS
SELECT i.order_id, i.item, i.seller_id, i.product_id, p.category, p.weight_g, i.price, i.freight, i.ship_limit,
       o.purchased, o.approved, o.to_carrier, o.delivered, o.promised,
       s.state AS seller_state, c.state AS customer_state, ds.region AS customer_region,
       gs.lat AS seller_lat, gs.lng AS seller_lng, gc.lat AS customer_lat, gc.lng AS customer_lng,
       2 * 6371 * asin(sqrt(pow(sin(radians(gc.lat - gs.lat) / 2), 2)
           + cos(radians(gs.lat)) * cos(radians(gc.lat)) * pow(sin(radians(gc.lng - gs.lng) / 2), 2))) AS km,
       p.category IN ('health_beauty', 'perfumery') AS is_beauty
FROM stg_items i
JOIN stg_orders o USING (order_id)
JOIN stg_products p USING (product_id)
JOIN stg_sellers s USING (seller_id)
JOIN stg_customers c ON c.customer_id = o.customer_id
LEFT JOIN dim_state ds ON ds.state = c.state
LEFT JOIN stg_geo gs ON gs.zip = s.zip
LEFT JOIN stg_geo gc ON gc.zip = c.zip
WHERE o.status = 'delivered' AND o.delivered IS NOT NULL;

-- Stage durations in days, for every delivered order (first line gives the seller and the distance).
CREATE OR REPLACE TABLE fct_orders AS
WITH first_line AS (
    SELECT * FROM fct_order_lines QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY item) = 1
), agg AS (
    SELECT order_id, count(*) AS units, sum(price) AS gmv, sum(freight) AS freight_total,
           bool_or(is_beauty) AS has_beauty, max(ship_limit) AS ship_limit_max
    FROM fct_order_lines GROUP BY 1
)
SELECT f.order_id, f.seller_id, f.seller_state, f.customer_state, f.customer_region, f.km,
       f.customer_lat, f.customer_lng, f.purchased, f.approved, f.to_carrier, f.delivered, f.promised,
       a.units, a.gmv, a.freight_total, a.has_beauty,
       date_diff('second', f.purchased, f.approved) / 86400.0 AS d_approval,
       date_diff('second', f.approved, f.to_carrier) / 86400.0 AS d_handling,
       date_diff('second', f.to_carrier, f.delivered) / 86400.0 AS d_transit,
       date_diff('second', f.purchased, f.delivered) / 86400.0 AS d_total,
       date_diff('second', f.purchased, f.promised) / 86400.0 AS d_promise,
       f.delivered > f.promised + INTERVAL 1 DAY - INTERVAL 1 SECOND AS late,
       f.to_carrier > a.ship_limit_max AS shipped_late
FROM first_line f JOIN agg a USING (order_id)
ORDER BY f.order_id;

CREATE OR REPLACE TABLE daily_beauty_demand AS
SELECT CAST(o.purchased AS DATE) AS day, o.customer_state AS state, ds.region,
       sum(CASE WHEN l.is_beauty THEN 1 ELSE 0 END) AS units, count(DISTINCT o.order_id) AS orders
FROM fct_orders o
JOIN fct_order_lines l USING (order_id)
LEFT JOIN dim_state ds ON ds.state = o.customer_state
WHERE o.has_beauty
GROUP BY ALL
ORDER BY day, state;
