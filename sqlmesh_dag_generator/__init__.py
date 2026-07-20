"""
SQLMesh DAG Generator - Open Source Airflow Integration for SQLMesh
"""

__version__ = "0.9.11"


from sqlmesh_dag_generator.generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig, RecoveryConfig
from sqlmesh_dag_generator.airflow_utils import (
    resolve_credentials,
    register_credential_resolver,
    CredentialResolver,
)
from sqlmesh_dag_generator.airflow_compat import (
    BaseHook,
    BashOperator,
    EmptyOperator,
    PythonOperator,
    TriggerDagRunOperator,
    Variable,
    dag_schedule_kwargs,
    is_airflow_3,
)

__all__ = [
    "SQLMeshDAGGenerator",
    "DAGGeneratorConfig",
    "RecoveryConfig",
    "resolve_credentials",
    "register_credential_resolver",
    "CredentialResolver",
    # AF2/AF3 shims (import from here or sqlmesh_dag_generator.airflow_compat)
    "BaseHook",
    "BashOperator",
    "EmptyOperator",
    "PythonOperator",
    "TriggerDagRunOperator",
    "Variable",
    "dag_schedule_kwargs",
    "is_airflow_3",
]



