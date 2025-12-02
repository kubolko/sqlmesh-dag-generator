"""
Example 3: Using Configuration File

This example shows how to use a YAML configuration file for more control
over the generated DAG.

Configuration files are recommended for production deployments.
"""

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig

# ============================================================================
# Load Configuration
# ============================================================================

# Option 1: Load from YAML file
config = DAGGeneratorConfig.from_file("config.yaml")

# Option 2: Create from dictionary
config = DAGGeneratorConfig.from_dict({
    "sqlmesh": {
        "project_path": "/path/to/your/sqlmesh/project",  # ⚠️ UPDATE THIS
        "environment": "prod",
    },
    "airflow": {
        "dag_id": "sqlmesh_production_pipeline",
        "schedule_interval": "@daily",
        "description": "Production data pipeline",
        "tags": ["sqlmesh", "production", "analytics"],
        "default_args": {
            "owner": "data-team",
            "retries": 2,
            "retry_delay": 300,  # seconds
        },
    },
    "generation": {
        "mode": "dynamic",  # Dynamic is default (fire-and-forget!)
        "output_dir": "./dags",
    },
})

# ============================================================================
# Generate DAG
# ============================================================================

print("🚀 Generating DAG with configuration...")

generator = SQLMeshDAGGenerator(config=config)
dag_code = generator.generate_dynamic_dag()

print(f"✅ Generated: {config.airflow.dag_id}")
print(f"📊 Models: {len(generator.models)}")
print(f"📁 Mode: {config.generation.mode}")

