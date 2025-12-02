"""
Example 2: Generate DAG File (Simplest Usage)

This example shows the simplest way to use the SQLMesh DAG Generator:
- Load your SQLMesh project
- Generate a dynamic DAG file
- Deploy to Airflow

Run this script to generate a DAG file, then copy it to your Airflow dags folder.
"""

from sqlmesh_dag_generator import SQLMeshDAGGenerator

# ============================================================================
# Configuration
# ============================================================================

SQLMESH_PROJECT_PATH = "/path/to/your/sqlmesh/project"  # ⚠️ UPDATE THIS
DAG_ID = "my_sqlmesh_pipeline"

# ============================================================================
# Generate DAG
# ============================================================================

print("🚀 Generating Airflow DAG from SQLMesh project...")

# Create generator
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path=SQLMESH_PROJECT_PATH,
    dag_id=DAG_ID,
)

# Generate dynamic DAG (fire-and-forget!)
dag_code = generator.generate_dynamic_dag()

# Save to file
output_file = f"{DAG_ID}.py"
with open(output_file, "w") as f:
    f.write(dag_code)

print(f"✅ DAG generated: {output_file}")
print(f"📊 Models discovered: {len(generator.models)}")
print()
print("📋 Next steps:")
print(f"   1. Review: cat {output_file}")
print(f"   2. Deploy: cp {output_file} /opt/airflow/dags/")
print(f"   3. The DAG will auto-discover models at runtime!")

