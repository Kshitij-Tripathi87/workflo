-- dbt model patch for column rename
-- File: models/orders_summary.sql

{{ config(materialized='table') }}

SELECT
    name AS customer_name,  -- Alias for backward compatibility
    order_id,
    order_total,
    created_at
FROM {{ source('postgres', 'orders') }}

-- Run: dbt run --models orders_summary
-- Then: dbt test --models orders_summary