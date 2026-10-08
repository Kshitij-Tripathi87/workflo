# Airflow DAG patch for pipeline failure
# File: dags/etl_customer_sync_patch.py

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'etl_customer_sync',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False,
)

def retry_with_backoff(**context):
    """Retry logic with exponential backoff."""
    import time
    attempt = context.get('task_instance').try_number
    delay = min(300, (2 ** attempt) * 60)
    time.sleep(delay)
    # Retry logic here

retry_task = PythonOperator(
    task_id='retry_with_backoff',
    python_callable=retry_with_backoff,
    dag=dag,
)