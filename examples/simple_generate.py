"""
Simplest Example - Bare Minimum

Shows the absolute minimum code needed to use SQLMesh DAG Generator.
Copy this to /opt/airflow/dags/ and it works!

For multi-environment setup, see: examples/4_multi_environment.py
"""

from datetime import datetime
from airflow import DAG
from airflow.models import Variable
from sqlmesh_dag_generator import SQLMeshDAGGenerator

# ⚠️ UPDATE THESE (or set as Airflow Variables)
SQLMESH_PROJECT = Variable.get(
    "sqlmesh_project_path",
    default_var="/path/to/your/sqlmesh/project"
)

# Use gateway to select environment (docker_local, dev, staging, prod)
# NOT the 'environment' parameter - that's deprecated!
GATEWAY = Variable.get("sqlmesh_gateway", default_var="docker_local")

with DAG(
    "simple_sqlmesh",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:
    # Create generator with gateway (NOT environment!)
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY  # ✅ This selects your environment
    )

    # Dynamically create all tasks - fire and forget!
    generator.create_tasks_in_dag(dag)


