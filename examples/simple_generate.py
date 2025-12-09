"""
Simplest Example - Bare Minimum

Shows the absolute minimum code needed to use SQLMesh DAG Generator.
Copy this to /opt/airflow/dags/ and it works!

The DAG schedule is automatically detected from your SQLMesh models!
If you have models with different intervals (5min, hourly, daily),
the DAG will run at the shortest interval and SQLMesh handles the rest.

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
GATEWAY = Variable.get("sqlmesh_gateway", default_var="docker_local")

# Create generator first to get recommended schedule
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path=SQLMESH_PROJECT,
    gateway=GATEWAY,
    auto_schedule=True,  # ✨ Automatically detect schedule from models!
)

# Get the recommended schedule based on your models
# This finds the shortest interval across all models
recommended_schedule = generator.get_recommended_schedule()

with DAG(
    "simple_sqlmesh",
    start_date=datetime(2024, 1, 1),
    schedule=recommended_schedule,  # 🚀 Dynamic schedule!
    catchup=False,
) as dag:
    # Dynamically create all tasks - fire and forget!
    generator.create_tasks_in_dag(dag)

# Optional: Print schedule info (visible in Airflow logs)
print(f"📅 DAG scheduled at: {recommended_schedule}")
print(f"📊 Model intervals: {generator.get_model_intervals_summary()}")

