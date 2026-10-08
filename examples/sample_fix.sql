-- Remediation draft for orders schema drift
-- Replace customer_name with name in downstream transformation logic
SELECT
  order_id,
  name AS customer_name,
  order_total
FROM raw_orders;
