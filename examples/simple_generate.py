"""
Simplest Example - Bare Minimum

Shows the absolute minimum code needed to use SQLMesh DAG Generator.
Copy this to /opt/airflow/dags/ and it works!
"""

from datetime import datetime
from airflow import DAG
from sqlmesh_dag_generator import SQLMeshDAGGenerator

# ⚠️ UPDATE THIS
SQLMESH_PROJECT = "/path/to/your/sqlmesh/project"

with DAG(
    "simple_sqlmesh",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:
    SQLMeshDAGGenerator(SQLMESH_PROJECT).create_tasks_in_dag(dag)

