"""
SQLMesh DAG Generator - Open Source Airflow Integration for SQLMesh
"""

__version__ = "0.4.0"

from sqlmesh_dag_generator.generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig
from sqlmesh_dag_generator.airflow_utils import (
    resolve_credentials,
    register_credential_resolver,
    CredentialResolver,
)

__all__ = [
    "SQLMeshDAGGenerator",
    "DAGGeneratorConfig",
    "resolve_credentials",
    "register_credential_resolver",
    "CredentialResolver",
]

