# Incident Summary

## Asset
- **URN:** `urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)`
- **Name:** orders
- **Criticality:** critical

## Scenario
- **Type:** schema_remove
- **Change:** Removed column `customer_name`

## Impact
- **Severity:** high
- **Affected Assets:** 3 downstream assets
- **Affected Dashboards:** orders_monitoring
- **Affected ML Models:** order_forecast

## Recommendation
- **Action:** patch_sql
- **Rationale:** Column removal breaks downstream consumers

## Resolution
- **Status:** triaged
- **Artifact:** schema_patch.sql