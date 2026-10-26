import { AssetNode } from "./types";

export const assets: AssetNode[] = [
  {
    urn: "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
    name: "orders",
    kind: "dataset",
    owner: "data-platform",
    description: "Raw orders table from production PostgreSQL",
    schema_fields: ["order_id", "customer_name", "order_total", "created_at"],
    upstream: [],
    downstream: [
      "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)",
      "urn:li:dashboard:(looker,orders_monitoring)",
      "urn:li:mlModel:(sagemaker,order_forecast,PROD)"
    ],
    tags: ["pii", "critical", "finance"],
    freshness: "fresh",
    criticality: "critical",
    status: null
  },
  {
    urn: "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)",
    name: "orders_summary",
    kind: "dataset",
    owner: "analytics",
    description: "Aggregated daily order summary",
    schema_fields: ["date", "total_orders", "total_revenue"],
    upstream: ["urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"],
    downstream: [
      "urn:li:dashboard:(looker,orders_monitoring)",
      "urn:li:dashboard:(tableau,executive_kpis)"
    ],
    tags: ["aggregated", "finance"],
    freshness: "fresh",
    criticality: "high",
    status: null
  },
  {
    urn: "urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)",
    name: "customers",
    kind: "dataset",
    owner: null,
    description: "Customer dimension table",
    schema_fields: ["customer_id", "customer_name", "email", "region"],
    upstream: [],
    downstream: [
      "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_lifetime_value,PROD)",
      "urn:li:pipeline:(airflow,etl_customer_sync)"
    ],
    tags: ["pii", "core"],
    freshness: "stale",
    criticality: "high",
    status: null
  },
  {
    urn: "urn:li:pipeline:(airflow,etl_customer_sync)",
    name: "etl_customer_sync",
    kind: "pipeline",
    owner: "data-platform",
    description: "Daily ETL job syncing customer data to warehouse",
    schema_fields: [],
    upstream: ["urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)"],
    downstream: ["urn:li:dataset:(urn:li:dataPlatform:dbt,customer_lifetime_value,PROD)"],
    tags: ["etl", "daily"],
    freshness: "fresh",
    criticality: "high",
    status: "running"
  },
  {
    urn: "urn:li:dashboard:(looker,orders_monitoring)",
    name: "orders_monitoring",
    kind: "dashboard",
    owner: "analytics",
    description: "Real-time order monitoring dashboard",
    schema_fields: [],
    upstream: [
      "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
      "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)"
    ],
    downstream: [],
    tags: ["operational", "finance"],
    freshness: "fresh",
    criticality: "high",
    status: null
  },
  {
    urn: "urn:li:mlModel:(sagemaker,order_forecast,PROD)",
    name: "order_forecast",
    kind: "model",
    owner: "ml-team",
    description: "Demand forecasting model for orders",
    schema_fields: ["order_id", "predicted_date", "confidence"],
    upstream: ["urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"],
    downstream: ["urn:li:dashboard:(looker,orders_monitoring)"],
    tags: ["ml", "forecasting"],
    freshness: "fresh",
    criticality: "high",
    status: null
  }
];