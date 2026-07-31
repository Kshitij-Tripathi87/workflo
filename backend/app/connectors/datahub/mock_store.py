MOCK_ASSETS = {
    "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)": {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
        "name": "orders",
        "kind": "dataset",
        "description": "Raw orders table from production PostgreSQL",
        "owner": "data-platform",
        "schema_fields": ["order_id", "customer_name", "order_total", "created_at"],
        "expected_schema_fields": ["order_id", "customer_name", "order_total", "created_at"],
        "upstream": [],
        "downstream": [
            "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)",
            "urn:li:dashboard:(looker,orders_monitoring)",
            "urn:li:mlModel:(sagemaker,order_forecast,PROD)"
        ],
        "tags": ["pii", "critical", "finance"],
        "criticality": "critical",
        "freshness": "fresh"
    },
    "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)": {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)",
        "name": "orders_summary",
        "kind": "dataset",
        "description": "Aggregated daily order summary",
        "owner": "analytics",
        "schema_fields": ["date", "total_orders", "total_revenue"],
        "expected_schema_fields": ["date", "total_orders", "total_revenue"],
        "upstream": ["urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"],
        "downstream": [
            "urn:li:dashboard:(looker,orders_monitoring)",
            "urn:li:dashboard:(tableau,executive_kpis)"
        ],
        "tags": ["aggregated", "finance"],
        "criticality": "high",
        "freshness": "fresh"
    },
    "urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)": {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)",
        "name": "customers",
        "kind": "dataset",
        "description": "Customer dimension table",
        "owner": None,
        "schema_fields": ["customer_id", "customer_name", "email", "region"],
        "expected_schema_fields": ["customer_id", "customer_name", "email", "region"],
        "upstream": [],
        "downstream": [
            "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_lifetime_value,PROD)",
            "urn:li:pipeline:(airflow,etl_customer_sync)"
        ],
        "tags": ["pii", "core"],
        "criticality": "high",
        "freshness": "stale"
    },
    "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_lifetime_value,PROD)": {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_lifetime_value,PROD)",
        "name": "customer_lifetime_value",
        "kind": "dataset",
        "description": "Computed CLV per customer",
        "owner": "analytics",
        "schema_fields": ["customer_id", "clv_score", "segment"],
        "expected_schema_fields": ["customer_id", "clv_score", "segment"],
        "upstream": ["urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)"],
        "downstream": ["urn:li:dashboard:(tableau,executive_kpis)"],
        "tags": ["ml-feature", "analytics"],
        "criticality": "medium",
        "freshness": "fresh"
    },
    "urn:li:pipeline:(airflow,etl_customer_sync)": {
        "urn": "urn:li:pipeline:(airflow,etl_customer_sync)",
        "name": "etl_customer_sync",
        "kind": "pipeline",
        "description": "Daily ETL job syncing customer data to warehouse",
        "owner": "data-platform",
        "schema_fields": [],
        "expected_schema_fields": [],
        "upstream": ["urn:li:dataset:(urn:li:dataPlatform:postgres,customers,PROD)"],
        "downstream": ["urn:li:dataset:(urn:li:dataPlatform:dbt,customer_lifetime_value,PROD)"],
        "tags": ["etl", "daily"],
        "criticality": "high",
        "freshness": "fresh",
        "status": "running"
    },
    "urn:li:pipeline:(airflow,order_ingestion)": {
        "urn": "urn:li:pipeline:(airflow,order_ingestion)",
        "name": "order_ingestion",
        "kind": "pipeline",
        "description": "Real-time order ingestion pipeline",
        "owner": "data-platform",
        "schema_fields": [],
        "expected_schema_fields": [],
        "upstream": [],
        "downstream": ["urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"],
        "tags": ["streaming", "critical"],
        "criticality": "critical",
        "freshness": "fresh",
        "status": "running"
    },
    "urn:li:dashboard:(looker,orders_monitoring)": {
        "urn": "urn:li:dashboard:(looker,orders_monitoring)",
        "name": "orders_monitoring",
        "kind": "dashboard",
        "description": "Real-time order monitoring dashboard",
        "owner": "analytics",
        "schema_fields": [],
        "expected_schema_fields": [],
        "upstream": [
            "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
            "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)"
        ],
        "downstream": [],
        "tags": ["operational", "finance"],
        "criticality": "high",
        "freshness": "fresh"
    },
    "urn:li:dashboard:(tableau,executive_kpis)": {
        "urn": "urn:li:dashboard:(tableau,executive_kpis)",
        "name": "executive_kpis",
        "kind": "dashboard",
        "description": "Executive KPI dashboard for leadership",
        "owner": "leadership",
        "schema_fields": [],
        "expected_schema_fields": [],
        "upstream": [
            "urn:li:dataset:(urn:li:dataPlatform:dbt,orders_summary,PROD)",
            "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_lifetime_value,PROD)"
        ],
        "downstream": [],
        "tags": ["executive", "kpi"],
        "criticality": "critical",
        "freshness": "fresh"
    },
    "urn:li:mlModel:(sagemaker,order_forecast,PROD)": {
        "urn": "urn:li:mlModel:(sagemaker,order_forecast,PROD)",
        "name": "order_forecast",
        "kind": "model",
        "description": "Demand forecasting model for orders",
        "owner": "ml-team",
        "schema_fields": ["order_id", "predicted_date", "confidence"],
        "expected_schema_fields": ["order_id", "predicted_date", "confidence"],
        "upstream": ["urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"],
        "downstream": ["urn:li:dashboard:(looker,orders_monitoring)"],
        "tags": ["ml", "forecasting"],
        "criticality": "high",
        "freshness": "fresh"
    }
}