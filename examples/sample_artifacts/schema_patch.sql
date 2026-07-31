-- SQL patch for column removal
-- Review downstream dependencies before applying.

-- Option 1: Create compatibility view
CREATE OR REPLACE VIEW orders_compat AS
SELECT 
    order_id,
    order_total,
    created_at,
    NULL AS customer_name  -- Placeholder for removed column
FROM orders;

-- Option 2: Update downstream queries to not reference customer_name
-- SELECT order_id, order_total FROM orders;