"""
Multi-Environment SQLMesh DAG Example

This example demonstrates how to properly configure SQLMesh DAG Generator
for multi-environment deployments (dev/staging/prod) using Airflow Variables.

Key Points:
1. Use 'gateway' to switch environments, NOT 'environment'
2. Default to 'docker_local' for local development
3. Use Airflow Variables for production deployment
4. Same DAG works across all environments!
"""

from datetime import datetime
from airflow import DAG
from airflow.models import Variable
from sqlmesh_dag_generator import SQLMeshDAGGenerator

# ==============================================================================
# Configuration via Airflow Variables
# ==============================================================================
# Set these in Airflow UI (Admin > Variables):
#
# Development/Local:
#   sqlmesh_project_path = /opt/airflow/core/sqlmesh_project
#   sqlmesh_gateway = docker_local
#
# Production:
#   sqlmesh_project_path = /opt/airflow/core/sqlmesh_project
#   sqlmesh_gateway = prod
#
# Staging:
#   sqlmesh_gateway = staging
# ==============================================================================

# Get SQLMesh project path from Airflow Variables
SQLMESH_PROJECT = Variable.get(
    "sqlmesh_project_path",
    default_var="/opt/airflow/core/sqlmesh_project"
)

# Gateway controls which environment (docker_local, dev, staging, prod)
# This is the CORRECT way to switch environments with SQLMesh!
GATEWAY = Variable.get("sqlmesh_gateway", default_var="docker_local")

# ==============================================================================
# DAG Definition
# ==============================================================================
with DAG(
    dag_id="sqlmesh_multi_env_pipeline",
    description="SQLMesh pipeline with multi-environment support",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["sqlmesh", "dwh", "multi-env"],
    max_active_runs=1,
) as dag:

    # Create the generator - gateway determines which environment
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY,  # ✅ This is what matters!
        # Note: 'environment' parameter is deprecated/not used
    )

    # Dynamically create all tasks and dependencies
    # This discovers models at runtime - fire and forget!
    generator.create_tasks_in_dag(dag)


# ==============================================================================
# Expected SQLMesh Configuration (config.yaml)
# ==============================================================================
# Your SQLMesh project should have a config.yaml like this:
#
# default_gateway: docker_local
#
# model_defaults:
#   dialect: redshift
#   start: 2023-01-01
#
# project: my_dwh
#
# state_connection:
#   type: postgres
#   host: "{{ env_var('POSTGRES_HOST') }}"
#   port: 5432
#   user: "{{ env_var('POSTGRES_USER') }}"
#   password: "{{ env_var('POSTGRES_PASSWORD') }}"
#   database: sqlmesh
#
# gateways:
#   docker_local:
#     connection:
#       type: duckdb
#       database: ":memory:"
#     state_connection:
#       type: duckdb
#       database: .sqlmesh/state.db
#
#   dev:
#     connection:
#       type: redshift
#       host: "{{ env_var('REDSHIFT_DEV_HOST') }}"
#       port: 5439
#       user: "{{ env_var('REDSHIFT_USER') }}"
#       password: "{{ env_var('REDSHIFT_PASSWORD') }}"
#       database: dev
#
#   staging:
#     connection:
#       type: redshift
#       host: "{{ env_var('REDSHIFT_STAGING_HOST') }}"
#       port: 5439
#       user: "{{ env_var('REDSHIFT_USER') }}"
#       password: "{{ env_var('REDSHIFT_PASSWORD') }}"
#       database: staging
#
#   prod:
#     connection:
#       type: redshift
#       host: "{{ env_var('REDSHIFT_PROD_HOST') }}"
#       port: 5439
#       user: "{{ env_var('REDSHIFT_USER') }}"
#       password: "{{ env_var('REDSHIFT_PASSWORD') }}"
#       database: prod
# ==============================================================================

# ==============================================================================
# Environment Variables
# ==============================================================================
# Set these in your Airflow deployment (docker-compose.yml, K8s ConfigMap, etc.):
#
# POSTGRES_HOST=your-postgres-host
# POSTGRES_USER=airflow
# POSTGRES_PASSWORD=your-postgres-password
# REDSHIFT_DEV_HOST=your-dev-redshift-host
# REDSHIFT_STAGING_HOST=your-staging-redshift-host
# REDSHIFT_PROD_HOST=your-prod-redshift-host
# REDSHIFT_USER=your-redshift-user
# REDSHIFT_PASSWORD=your-redshift-password
# ==============================================================================

# ==============================================================================
# Switching Environments
# ==============================================================================
# To switch environments, just change the Airflow Variable:
#
# Development:
#   airflow variables set sqlmesh_gateway "docker_local"
#
# Staging:
#   airflow variables set sqlmesh_gateway "staging"
#
# Production:
#   airflow variables set sqlmesh_gateway "prod"
#
# The same DAG file works in all environments! 🎉
# ==============================================================================

