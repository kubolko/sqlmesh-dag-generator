"""
SQLMesh DAG Generator - Airflow orchestration for SQLMesh projects, self-hosted.
"""

__version__ = "0.10.1"


from sqlmesh_dag_generator.airflow_compat import (
    BaseHook,
    BashOperator,
    Dataset,
    EmptyOperator,
    PythonOperator,
    TriggerDagRunOperator,
    Variable,
    dag_schedule_kwargs,
    is_airflow_3,
    make_dataset,
    supports_datasets,
)
from sqlmesh_dag_generator.airflow_utils import (
    CredentialResolver,
    register_credential_resolver,
    resolve_credentials,
)
from sqlmesh_dag_generator.config import (
    DAGGeneratorConfig,
    DAGGroupConfig,
    RecoveryConfig,
    TaskOverride,
)
from sqlmesh_dag_generator.dag_groups import (
    build_dag_groups,
    describe_dag_groups,
    plan_dag_groups,
)
from sqlmesh_dag_generator.generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.manifest import build_manifest, diff_manifests, write_manifest
from sqlmesh_dag_generator.selectors import (
    SelectionError,
    explain_selection,
    select_models,
)
from sqlmesh_dag_generator.triggers import (
    ModelTriggerConfig,
    parse_trigger_from_tags,
    resolve_model_trigger,
)
from sqlmesh_dag_generator.utils import (
    interval_end_matches_cron,
    not_due_skip_result,
    should_skip_model_for_tick,
)

__all__ = [
    "SQLMeshDAGGenerator",
    "DAGGeneratorConfig",
    "DAGGroupConfig",
    "RecoveryConfig",
    "TaskOverride",
    # One project, several DAGs
    "build_dag_groups",
    "describe_dag_groups",
    "plan_dag_groups",
    # dbt-style model selection
    "select_models",
    "explain_selection",
    "SelectionError",
    # Orchestration manifest (dbt's manifest.json, for the Airflow side)
    "build_manifest",
    "write_manifest",
    "diff_manifests",
    "ModelTriggerConfig",
    "parse_trigger_from_tags",
    "resolve_model_trigger",
    "resolve_credentials",
    "register_credential_resolver",
    "CredentialResolver",
    # AF2/AF3 shims (import from here or sqlmesh_dag_generator.airflow_compat)
    "BaseHook",
    "BashOperator",
    "Dataset",
    "EmptyOperator",
    "PythonOperator",
    "TriggerDagRunOperator",
    "Variable",
    "dag_schedule_kwargs",
    "is_airflow_3",
    "make_dataset",
    "supports_datasets",
    # Mixed-cadence due-skip helpers
    "interval_end_matches_cron",
    "not_due_skip_result",
    "should_skip_model_for_tick",
]
