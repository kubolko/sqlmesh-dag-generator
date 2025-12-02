"""
Example 1: Production-Ready Dynamic DAG

This example shows a production-ready SQLMesh DAG with:
- Airflow Variables for multi-environment support
- Proper error handling and logging
- Configurable retries and timeouts
- Tags for organization
- Email notifications (optional)

Copy this to Airflow's dags/ folder for production use.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from sqlmesh_dag_generator import SQLMeshDAGGenerator
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration via Airflow Variables (set in Airflow UI: Admin > Variables)
# ============================================================================

# Required: SQLMesh project configuration
SQLMESH_PROJECT = Variable.get(
    "sqlmesh_project_path",
    default_var="/path/to/your/sqlmesh/project"  # ⚠️ UPDATE DEFAULT
)

# Optional: Environment and gateway settings
ENVIRONMENT = Variable.get("sqlmesh_environment", default_var="prod")
GATEWAY = Variable.get("sqlmesh_gateway", default_var=None)

# Optional: Email notifications
ALERT_EMAIL = Variable.get("data_team_email", default_var=None)

# ============================================================================
# DAG Configuration
# ============================================================================

default_args = {
    "owner": "data-team",
    "depends_on_past": False,
    "email": [ALERT_EMAIL] if ALERT_EMAIL else [],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}

# ============================================================================
# Create DAG
# ============================================================================

with DAG(
    dag_id="sqlmesh_production_pipeline",
    default_args=default_args,
    description="Production SQLMesh pipeline - auto-discovers models",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["sqlmesh", "production", "data-pipeline"],
    doc_md=__doc__,
) as dag:

    # Optional: Add start/end markers for monitoring
    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    # Create SQLMesh generator
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        environment=ENVIRONMENT,
        gateway=GATEWAY,
    )

    # Generate all SQLMesh tasks
    logger.info(f"Creating tasks from SQLMesh project: {SQLMESH_PROJECT}")
    tasks = generator.create_tasks_in_dag(dag)
    logger.info(f"Created {len(tasks)} tasks")

    # Set up start/end dependencies
    # Find root tasks (tasks with no dependencies)
    root_tasks = [t for name, t in tasks.items()
                  if not generator.models[name].dependencies]

    # Find leaf tasks (tasks with no dependents)
    all_deps = set()
    for model in generator.models.values():
        all_deps.update(model.dependencies)
    leaf_tasks = [t for name, t in tasks.items() if name not in all_deps]

    # Connect markers
    if root_tasks:
        start >> root_tasks
    if leaf_tasks:
        leaf_tasks >> end


