# Quick Start Guide - SQLMesh DAG Generator

This guide shows you how to generate Airflow DAGs from your SQLMesh project in **under 5 minutes**.

---

## Prerequisites

- Python 3.8+
- An existing SQLMesh project
- Airflow 2.0+ (for running the generated DAGs)

---

## Installation

### Option 1: Install from PyPI (when published)
```bash
pip install sqlmesh-dag-generator
```

### Option 2: Install from Source (current)
```bash
# Clone the repository
git clone https://github.com/yourusername/SQLMeshDAGGenerator.git
cd SQLMeshDAGGenerator

# Install the package
pip install -e .
```

### Option 3: Install Dependencies Only
```bash
pip install sqlmesh airflow pyyaml
```

---

## Use Case: Generate DAG for Your SQLMesh Project

### Step 1: Prepare Your SQLMesh Project

Make sure your SQLMesh project has:
```
my_sqlmesh_project/
├── config.yaml          # SQLMesh config with database credentials
├── models/              # Your SQL models
│   ├── staging/
│   │   └── stg_users.sql
│   ├── marts/
│   │   └── dim_users.sql
│   └── ...
└── ...
```

**Example SQLMesh model:**
```sql
-- models/staging/stg_users.sql
MODEL (
  name my_project.stg_users,
  kind FULL,
  owner 'data-team',
);

SELECT
  user_id,
  email,
  created_at
FROM raw.users;
```

---

## Option A: Dynamic DAG (Recommended - Fire & Forget)

**Best for:** Projects where models change frequently. Place the DAG file once and forget about it!

### Step 1: Create a Configuration File

Create `dag_config.yaml`:
```yaml
sqlmesh:
  project_path: "/path/to/my_sqlmesh_project"  # UPDATE THIS
  environment: "prod"
  gateway: null  # Optional: specify SQLMesh gateway

airflow:
  dag_id: "my_sqlmesh_pipeline"
  schedule_interval: "@daily"
  description: "My SQLMesh data pipeline"
  tags:
    - sqlmesh
    - data-pipeline
  catchup: false
  max_active_runs: 1
  default_args:
    owner: "data-team"
    retries: 2

generation:
  output_dir: "./dags"
  mode: "dynamic"  # Dynamic mode - auto-discovers models!
  operator_type: "python"
  dry_run: false
```

### Step 2: Generate the DAG

```bash
# Using Python API
python << EOF
from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig

# Load config
config = DAGGeneratorConfig.from_file("dag_config.yaml")

# Generate dynamic DAG
generator = SQLMeshDAGGenerator(config=config)
dag_code = generator.generate_dynamic_dag()

print("Dynamic DAG generated!")
print(f"File: {config.generation.output_dir}/{config.airflow.dag_id}.py")
EOF
```

**OR use the config directly:**
```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/my_sqlmesh_project",
    dag_id="my_sqlmesh_pipeline",
    schedule_interval="@daily"
)

dag_code = generator.generate_dynamic_dag()

# Save to file
with open("dags/my_sqlmesh_pipeline.py", "w") as f:
    f.write(dag_code)
```

### Step 3: Deploy to Airflow

```bash
# Copy generated DAG to Airflow's dags folder
cp dags/my_sqlmesh_pipeline.py /opt/airflow/dags/

# Or if using Docker Composer setup
cp dags/my_sqlmesh_pipeline.py ./airflow/dags/
```

### Step 4: Configure Airflow Variables (Optional - for multi-environment)

In Airflow UI, go to **Admin > Variables** and set:

| Key | Value | Description |
|-----|-------|-------------|
| `sqlmesh_project_path` | `/path/to/my_sqlmesh_project` | Path to SQLMesh project |
| `sqlmesh_environment` | `prod` | Environment (prod/dev/staging) |
| `sqlmesh_gateway` | `my_gateway` | Optional: SQLMesh gateway |

**That's it! ** The DAG will:
- Auto-discover all SQLMesh models
- Create one task per model
- Build dependencies from SQLMesh lineage
- Update automatically when models change (no regeneration needed!)

---

## Option B: Static DAG (More Control)

**Best for:** Stable pipelines where you want full control over the generated code.

### Step 1: Create Configuration

```yaml
# dag_config.yaml
sqlmesh:
  project_path: "/path/to/my_sqlmesh_project"

airflow:
  dag_id: "my_sqlmesh_pipeline"
  schedule_interval: "@daily"

generation:
  output_dir: "./dags"
  mode: "static"  # Static mode - generates fixed code
  operator_type: "python"
```

### Step 2: Generate DAG

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig

config = DAGGeneratorConfig.from_file("dag_config.yaml")
generator = SQLMeshDAGGenerator(config=config)

# Generate static DAG
dag_code = generator.generate_dag()
```

### Step 3: Deploy

Same as Option A - copy to Airflow's dags folder.

**Note:** With static mode, you need to regenerate when SQLMesh models change.

---

## What You Get

### Generated DAG Structure

```
Your Airflow UI will show:
┌─────────────────────────────────────┐
│  my_sqlmesh_pipeline                │
├─────────────────────────────────────┤
│                                     │
│  [raw_users]                        │
│       │
│  [stg_users]                        │
│       ��
│  [dim_users]                        │
│                                     │
└─────────────────────────────────────┘
```

Each model becomes a separate task with proper dependencies!

### Task Naming Convention

SQLMesh model names are sanitized for Airflow:
- `"my_db"."my_schema"."my_model"` `sqlmesh_my_db_my_schema_my_model`
- Quotes, dots, spaces removed
- Prefix `sqlmesh_` added

---

## Example: Complete Workflow

Let's say you have this SQLMesh project:

```
my_data_project/
├── config.yaml
└── models/
    ├── raw_orders.sql      # No dependencies
    ├── stg_orders.sql      # Depends on: raw_orders
    └── orders_summary.sql  # Depends on: stg_orders
```

**1. Generate DAG:**
```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="./my_data_project",
    dag_id="orders_pipeline",
)

# Generate dynamic DAG
dag_code = generator.generate_dynamic_dag()

with open("dags/orders_pipeline.py", "w") as f:
    f.write(dag_code)

print("Generated DAG with 3 models")
```

**2. View in Airflow:**
```
Graph View shows:
  raw_orders stg_orders orders_summary
```

**3. Run the DAG:**
- Click "Trigger DAG" in Airflow UI
- Each task runs `sqlmesh run --select-model <model>`
- Tasks run in correct order based on dependencies
- Incremental models use proper time ranges

---

## Verify the Generation

### Before Deploying, Check:

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    dag_id="my_dag"
)

# 1. Extract models
models = generator.extract_models()

print(f"Found {len(models)} models:")
for name, info in models.items():
    print(f"  - {name}")
    if info.dependencies:
        print(f"    Dependencies: {info.dependencies}")

# 2. Validate SQLMesh context loads
try:
    generator.load_sqlmesh_context()
    print("SQLMesh context loaded successfully")
except Exception as e:
    print(f"Error loading SQLMesh: {e}")

# 3. Generate and validate syntax
dag_code = generator.generate_dynamic_dag()

import ast
try:
    ast.parse(dag_code)
    print("Generated DAG syntax is valid")
except SyntaxError as e:
    print(f"Syntax error: {e}")
```

---

## Troubleshooting

### Issue: "Failed to load SQLMesh context"

**Solution:** Check your SQLMesh config:
```yaml
# Your SQLMesh config.yaml must have:
model_defaults:
  dialect: duckdb  # or postgres, snowflake, etc.

gateways:
  local:
    connection:
      type: duckdb
      database: 'my_db.db'

default_gateway: local
```

### Issue: "No models discovered"

**Solution:** Verify your SQLMesh models directory:
```bash
# Check models exist
ls -la my_sqlmesh_project/models/

# Verify SQLMesh can load them
cd my_sqlmesh_project
sqlmesh plan  # Should show your models
```

### Issue: "DAG not appearing in Airflow"

**Solutions:**
1. Check DAG file is in correct location:
   ```bash
   ls /opt/airflow/dags/my_sqlmesh_pipeline.py
   ```

2. Check Airflow logs for parse errors:
   ```bash
   docker logs airflow-scheduler  # if using Docker
   ```

3. Verify DAG syntax:
   ```bash
   python /opt/airflow/dags/my_sqlmesh_pipeline.py
   ```

### Issue: "Airflow Variables not found"

**Solution:** Dynamic DAGs use fallback defaults, but for multi-environment:
```python
# In Airflow UI: Admin > Variables
# Or via CLI:
airflow variables set sqlmesh_project_path "/path/to/project"
airflow variables set sqlmesh_environment "prod"
```

---

## Next Steps

### Learn More:
- [Usage reference: dynamic vs static mode](USAGE.md)
- [Configuration Reference](examples/config_example.yaml)
- [Advanced Examples](examples/basic_usage.py)

### Customize Your DAG:
```yaml
# Advanced options in config.yaml
generation:
  mode: "dynamic"
  operator_type: "python"  # or "bash"
  include_models:          # Only include specific models
    - "my_schema.important_model"
  exclude_models:          # Exclude specific models
    - "my_schema.test_model"
```

---

## Pro Tips

### 1. **Use Dynamic Mode for Active Development**
```yaml
generation:
  mode: "dynamic"
```
- No regeneration needed when adding/removing models
- Always in sync with SQLMesh

### 2. **Use Airflow Variables for Multi-Environment**
```python
# Same DAG file works for dev/staging/prod
# Just change Airflow Variables per environment
```

### 3. **Monitor in Airflow UI**
- Graph View: See full lineage
- Task Logs: SQLMesh-specific error messages
- Task Duration: Identify slow models

### 4. **Test Locally First**
```bash
# Generate with dry_run to preview
generation:
  dry_run: true
```

---

## Success!

You now have:
Airflow DAG generated from SQLMesh
Full data lineage visible in Airflow
One task per SQLMesh model
Proper dependencies from SQLMesh
Multi-environment support

**Questions?** Check the [documentation](README.md) or [examples](examples/).

---

**Happy orchestrating! **

