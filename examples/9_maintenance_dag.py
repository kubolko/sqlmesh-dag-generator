"""
A deploy DAG and a nightly maintenance DAG.

The interval DAG (examples/7_recommended_approach.py) should never block on a plan,
a backfill or a janitor run. Those belong here, where a long run is expected and
nobody is paged for it.
"""

from datetime import datetime, timedelta

from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator

PROJECT_PATH = "/opt/airflow/sqlmesh_project"

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path=PROJECT_PATH,
    gateway="prod",
    auto_replan_on_change=False,
)

# --- deploy: triggered by CI after a merge -------------------------------------
with DAG(
    dag_id="dwh_sqlmesh_deploy",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["sqlmesh", "deploy"],
) as deploy_dag:
    unit_tests = generator.create_unit_test_task(deploy_dag)
    lint = generator.create_lint_task(deploy_dag)
    plan_apply = generator.create_plan_apply_task(
        deploy_dag,
        execution_timeout=timedelta(hours=6),
    )

    [unit_tests, lint] >> plan_apply

# --- nightly maintenance --------------------------------------------------------
with DAG(
    dag_id="dwh_sqlmesh_maintenance",
    schedule="0 3 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["sqlmesh", "maintenance"],
) as maintenance_dag:
    generator.create_janitor_task(maintenance_dag)

# --- break glass: restate a window on demand ------------------------------------
# Trigger with: {"models": ["dwh.orders"], "start": "2024-05-01", "end": "2024-05-08"}
with DAG(
    dag_id="dwh_sqlmesh_restate",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["sqlmesh", "manual"],
) as restate_dag:
    generator.create_restate_task(restate_dag, execution_timeout=timedelta(hours=12))
