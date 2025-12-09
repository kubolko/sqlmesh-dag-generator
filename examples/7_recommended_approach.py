"""
RECOMMENDED APPROACH: Direct Connection Usage

This example demonstrates the NEW, CLEANER way to configure SQLMesh DAG Generator.

Key improvements over the old approach:
✅ Pass connection objects directly - no conversion needed
✅ Works with ANY credential source (Airflow, AWS, Vault, etc.)
✅ Extensible via plugins
✅ Less boilerplate
✅ More Pythonic

OLD WAY (still works, but deprecated):
    connection_config = airflow_connection_to_sqlmesh_config("postgres_prod")
    generator = SQLMeshDAGGenerator(..., connection_config=connection_config)

NEW WAY:
    generator = SQLMeshDAGGenerator(..., connection="postgres_prod")
    # Or even better, pass the Connection object directly!
"""

from datetime import datetime
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.models import Variable
from sqlmesh_dag_generator import SQLMeshDAGGenerator

# Get configuration from Airflow Variables
SQLMESH_PROJECT = Variable.get("sqlmesh_project_path")
GATEWAY = Variable.get("sqlmesh_gateway", default_var="prod")


# ==============================================================================
# APPROACH 1: Pass Connection Object Directly (BEST - Most Pythonic)
# ==============================================================================
# This is the cleanest and most straightforward approach

with DAG(
    dag_id="sqlmesh_direct_connection",
    description="SQLMesh with direct connection object (RECOMMENDED)",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["sqlmesh", "recommended"],
) as dag1:

    # Get the connection object - this is standard Airflow code
    conn = BaseHook.get_connection("postgres_prod")

    # Pass it directly - NO conversion needed!
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY,
        connection=conn,  # ✅ Direct object - clean and Pythonic!
    )

    generator.create_tasks_in_dag(dag1)


# ==============================================================================
# APPROACH 2: Pass Connection ID (Simple and Clean)
# ==============================================================================
# Even simpler - just pass the connection ID as a string

with DAG(
    dag_id="sqlmesh_connection_id",
    description="SQLMesh with connection ID",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["sqlmesh", "simple"],
) as dag2:

    # Just pass the connection ID - automatic resolution!
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY,
        connection="postgres_prod",  # ✅ Simple string - auto-resolved!
    )

    generator.create_tasks_in_dag(dag2)


# ==============================================================================
# APPROACH 3: Pass Dict Directly (For Manual Config)
# ==============================================================================
# If you want to build the config manually, just pass a dict

with DAG(
    dag_id="sqlmesh_dict_config",
    description="SQLMesh with dict configuration",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["sqlmesh", "manual"],
) as dag3:

    # Build config dict however you want
    connection_config = {
        "type": "postgres",
        "host": Variable.get("db_host"),
        "port": 5432,
        "user": Variable.get("db_user"),
        "password": Variable.get("db_password"),
        "database": Variable.get("db_name"),
    }

    # Pass it directly - no conversion needed!
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY,
        connection=connection_config,  # ✅ Dict works too!
    )

    generator.create_tasks_in_dag(dag3)


# ==============================================================================
# APPROACH 4: Separate Data and State Connections
# ==============================================================================
# Production best practice: separate data and state connections

with DAG(
    dag_id="sqlmesh_separate_connections",
    description="SQLMesh with separate data and state connections",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["sqlmesh", "production"],
) as dag4:

    # Data warehouse connection (e.g., Snowflake)
    data_conn = BaseHook.get_connection("snowflake_prod")

    # State tracking connection (e.g., Postgres)
    state_conn = BaseHook.get_connection("postgres_state")

    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY,
        connection=data_conn,        # ✅ Direct objects
        state_connection=state_conn,  # ✅ No conversion!
    )

    generator.create_tasks_in_dag(dag4)


# ==============================================================================
# APPROACH 5: AWS Secrets Manager (Extensible!)
# ==============================================================================
# The new architecture supports ANY credential source

with DAG(
    dag_id="sqlmesh_aws_secrets",
    description="SQLMesh with AWS Secrets Manager",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["sqlmesh", "aws"],
) as dag5:

    # Just pass the secret name - automatic resolution!
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY,
        connection="prod/database/credentials",
        credential_resolver="aws_secrets",  # ✅ Specify resolver type
    )

    generator.create_tasks_in_dag(dag5)


# ==============================================================================
# APPROACH 6: Custom Credential Resolver (For Advanced Cases)
# ==============================================================================
# You can even create your own resolver for HashiCorp Vault, etc.

from sqlmesh_dag_generator import CredentialResolver, register_credential_resolver

class VaultResolver(CredentialResolver):
    """Custom resolver for HashiCorp Vault."""

    def resolve(self, identifier):
        # Your Vault integration logic here
        import hvac
        client = hvac.Client(url='https://vault.company.com')
        secret = client.secrets.kv.v2.read_secret_version(path=identifier)
        return secret['data']['data']

# Register your custom resolver
register_credential_resolver('vault', VaultResolver())

with DAG(
    dag_id="sqlmesh_vault",
    description="SQLMesh with HashiCorp Vault",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["sqlmesh", "vault"],
) as dag6:

    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=SQLMESH_PROJECT,
        gateway=GATEWAY,
        connection="secret/data/database",
        credential_resolver="vault",  # ✅ Use your custom resolver!
    )

    generator.create_tasks_in_dag(dag6)


# ==============================================================================
# Why This Approach is Better
# ==============================================================================
#
# 1. PYTHONIC: Pass objects directly, no conversion functions needed
# 2. FLEXIBLE: Works with Airflow, AWS, Vault, custom sources
# 3. EXTENSIBLE: Add your own resolvers via plugins
# 4. CLEAN: Less boilerplate, more readable
# 5. SECURE: Credentials never in code, use any secure source
# 6. SIMPLE: For common cases, just pass a string!
#
# Compare:
#   OLD: connection_config = airflow_connection_to_sqlmesh_config("postgres")
#        generator = SQLMeshDAGGenerator(..., connection_config=connection_config)
#
#   NEW: generator = SQLMeshDAGGenerator(..., connection="postgres")
#
# That's it! 2 lines → 1 line, and it works with ANY credential source!
# ==============================================================================

