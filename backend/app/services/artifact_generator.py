from app.models.recommendation import Recommendation
from app.models.artifact import ArtifactDraft


# Templates for each (action_type, scenario_type) pair
ARTIFACT_TEMPLATES = {
    ("patch_sql", "schema_rename"): """-- SQL patch for column rename
-- Review downstream dependencies before applying.

ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name};

-- Update downstream views
-- CREATE OR REPLACE VIEW downstream_view AS
-- SELECT ..., {new_name} AS {old_name}, ... FROM {table_name};
""",
    ("patch_sql", "schema_remove"): """-- SQL patch for column removal
-- WARNING: This will break downstream consumers.

-- Option 1: Create compatibility view
CREATE OR REPLACE VIEW {table_name}_compat AS
SELECT 
    *,
    NULL AS {removed_column}  -- Placeholder for removed column
FROM {table_name};

-- Option 2: Update downstream queries to not reference {removed_column}
""",
    ("patch_dbt", "schema_rename"): """-- dbt model patch for column rename
-- File: models/{model_name}.sql

{{ config(materialized='table') }}

SELECT
    {new_name} AS {old_name},  -- Alias for backward compatibility
    *
FROM {{ source('{source_name}', '{table_name}') }}

-- Run: dbt run --models {model_name}
""",
    ("patch_dbt", "schema_remove"): """-- dbt model patch for column removal
-- File: models/{model_name}.sql

{{ config(materialized='table') }}

SELECT
    -- Removed: {removed_column}
    column_a,
    column_b,
    column_c
FROM {{ source('{source_name}', '{table_name}') }}

-- Run: dbt run --models {model_name}
-- Then: dbt test --models {model_name}
""",
    ("patch_dag", "pipeline_failure"): """# Airflow DAG patch for pipeline failure
# File: dags/{dag_name}_patch.py

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {{
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
}}

dag = DAG(
    '{dag_name}',
    default_args=default_args,
    schedule_interval='@hourly',
    catchup=False,
)

# Add retry logic with exponential backoff
def retry_with_backoff(**context):
    # Implementation here
    pass

retry_task = PythonOperator(
    task_id='retry_with_backoff',
    python_callable=retry_with_backoff,
    dag=dag,
)
""",
    ("assign_owner", "owner_missing"): f"""# Ownership Assignment Template
# Asset: {{asset_name}}

## Action Required
Assign a responsible owner for this asset.

## Steps
1. Identify the team or individual responsible for this data
2. Update DataHub ownership metadata:
   ```
   owner: <owner_urn>
   steward: <steward_urn>
   ```
3. Add to team's on-call rotation
4. Document in runbook

## Template for DataHub
```yaml
ownership:
  owner: urn:li:corpuser:<username>
  steward: urn:li:corpGroup:<team>
```
""",
    ("create_temp_view", "schema_remove"): """-- Temporary compatibility view
-- Use this as a stopgap while downstream consumers migrate

CREATE OR REPLACE VIEW {table_name}_temp AS
SELECT
    column_a,
    column_b,
    column_c,
    NULL AS {removed_column}  -- Placeholder to prevent immediate breakage
FROM {table_name}

-- Notify downstream consumers to migrate within 7 days
-- After migration: DROP VIEW {table_name}_temp;
""",
    ("rollback_change", "pipeline_failure"): """# Rollback procedure for pipeline failure

## Steps
1. Identify the failing commit/change:
   ```bash
   git log --oneline -10
   ```

2. Revert the change:
   ```bash
   git revert <commit-hash>
   ```

3. Redeploy the pipeline:
   ```bash
   airflow dags unpause {dag_name}
   airflow dags trigger {dag_name}
   ```

4. Monitor for successful completion
""",
    ("archive_asset", "dataset_deprecation"): """# Asset Archive Procedure
# Asset: {asset_name}

## Deprecation Checklist
- [ ] Notify all downstream consumers
- [ ] Create migration guide
- [ ] Set deprecation date: {deprecation_date}
- [ ] Update DataHub status to 'deprecated'
- [ ] After migration window: archive asset

## DataHub metadata update
```yaml
status: deprecated
deprecationDate: "{deprecation_date}"
deprecationReason: "Asset scheduled for archival"
```

## Archive command (after migration)
# sql
-- ALTER TABLE {table_name} SET TBLPROPERTIES ('archived'='true');
""",
    ("escalate", "auto_detected"): """# Incident Escalation

## Summary
Auto-detected issue requires human investigation.

## Details
- Asset: {asset_name}
- Severity: {severity}
- Detected: {detection_time}

## Next Steps
1. Review blast radius and affected assets
2. Identify root cause
3. Assign appropriate owner
4. Create targeted remediation plan

## Escalation Path
- Primary: Data Platform Team
- Secondary: On-call Engineering
""",
}


def _get_template(action_type: str, scenario_type: str) -> str:
    """Get template for action/scenario pair, with fallback."""
    key = (action_type, scenario_type)
    if key in ARTIFACT_TEMPLATES:
        return ARTIFACT_TEMPLATES[key]
    
    # Fallback to generic template
    return f"""# {action_type.replace('_', ' ').title()} Template
# Scenario: {scenario_type}

## Action
Implement {action_type} to address {scenario_type}.

## Notes
No specific template available - implement based on context.
"""


def _fill_template(template: str, context: dict) -> str:
    """Fill template placeholders with context values."""
    try:
        return template.format(**context)
    except KeyError:
        # Return template with placeholders if context is incomplete
        return template


def generate_artifact(
    recommendation: Recommendation,
    scenario_type: str = "auto_detected",
    asset_name: str = "asset",
    **kwargs
) -> ArtifactDraft:
    """
    Turn a recommendation into a concrete artifact.
    Uses deterministic templates - no LLM.
    """
    template = _get_template(recommendation.action_type, scenario_type)
    
    # Build context for template
    context = {
        "asset_name": asset_name,
        "table_name": asset_name,
        "model_name": asset_name,
        "dag_name": f"{asset_name}_dag",
        "source_name": "source",
        "old_name": "old_column",
        "new_name": "new_column",
        "removed_column": "removed_column",
        "severity": kwargs.get("severity", "medium"),
        "detection_time": kwargs.get("detection_time", "now"),
        "deprecation_date": kwargs.get("deprecation_date", "TBD"),
        **kwargs
    }
    
    body = _fill_template(template, context)
    
    # Determine artifact type based on action
    type_mapping = {
        "patch_sql": "sql",
        "patch_dbt": "dbt",
        "patch_dag": "dag",
        "assign_owner": "yaml",
        "create_temp_view": "sql",
        "rollback_change": "markdown",
        "archive_asset": "markdown",
        "escalate": "markdown",
    }
    
    artifact_type = type_mapping.get(recommendation.action_type, "markdown")
    
    return ArtifactDraft(
        recommendation_id=recommendation.recommendation_id,
        artifact_type=artifact_type,
        title=f"{recommendation.action_type.replace('_', ' ').title()} for {asset_name}",
        body=body,
        confidence=recommendation.confidence
    )