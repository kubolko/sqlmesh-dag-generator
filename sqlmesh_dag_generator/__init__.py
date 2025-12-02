"""
SQLMesh DAG Generator - Open Source Airflow Integration for SQLMesh
"""

__version__ = "0.1.0"

from sqlmesh_dag_generator.generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig

__all__ = [
    "SQLMeshDAGGenerator",
    "DAGGeneratorConfig",
]

