-- Core orders model — used by dashboards and ML feature pipelines.
-- Dropping any of these columns breaks downstream assets.

SELECT
    order_id,
    customer_id,
    customer_name,
    order_date,
    amount,
    status

FROM {{ ref('stg_orders') }}
