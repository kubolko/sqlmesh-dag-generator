"""
One SQLMesh project, several Airflow DAGs.

Finance models run every 15 minutes and page the on-call; marketing models run
nightly and are scheduled by the finance models they read, rather than by a clock
that hopefully fires late enough.

Drop this file in Airflow's dags/ folder. It creates two DAGs from a single
SQLMesh context, so DAG parsing stays cheap.
"""

from sqlmesh_dag_generator import DAGGeneratorConfig, build_dag_groups

CONFIG = {
    "sqlmesh": {
        "project_path": "/opt/airflow/sqlmesh_project",
        "gateway": "prod",
    },
    "airflow": {
        "dag_id": "dwh",  # fallback settings shared by the groups
        "start_date": "2024-01-01",
        "tags": ["sqlmesh"],
        "default_args": {"owner": "data-platform", "retries": 2},
    },
    "generation": {
        # Deploys live on their own DAG - see examples/7_recommended_approach.py
        "auto_replan_on_change": False,
        "task_overrides": [
            {
                "select": ["tag:heavy"],
                "pool": "heavy_pool",
                "execution_timeout_minutes": 120,
            }
        ],
    },
    "selectors": {
        "finance_core": {
            "union": ["tag:finance+"],
            "exclude": ["tag:deprecated"],
        }
    },
    "dag_groups": [
        {
            "dag_id": "dwh_finance",
            "select": ["selector:finance_core"],
            "schedule": "*/15 * * * *",
            "tags": ["sqlmesh", "finance", "oncall"],
        },
        {
            "dag_id": "dwh_marketing",
            "select": ["tag:marketing+"],
            # No schedule: this DAG runs when the finance models it reads are fresh.
            "wait_for_upstream": "dataset",
            "default_args": {"owner": "marketing-analytics", "retries": 0},
        },
    ],
}

config = DAGGeneratorConfig.from_dict(CONFIG)

# Airflow only picks up DAG objects it finds in module globals.
for dag_id, dag in build_dag_groups(config).items():
    globals()[dag_id] = dag
