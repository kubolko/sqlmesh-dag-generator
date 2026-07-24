# Usage Guide

## Per-model downstream DAG triggers (≥0.9.14)

Fire an Airflow DAG **only after a specific SQLMesh model** succeeds (not after the whole pipeline). Ideal for RT unload / notify steps.

### Option A — SQLMesh tags (preferred for SoC)

```sql
MODEL (
  name dwh.rt_fraud_da_set,
  kind FULL,
  cron '*/10 * * * *',
  tags (
    rt,
    flink,
    'trigger_dag:etl_rt_fraud_da_unload',
    'trigger_conf:source=sqlmesh'
  )
);
```

### Option B — generator config

```yaml
generation:
  model_triggers:
    dwh.rt_fraud_da_set:
      dag_id: etl_rt_fraud_da_unload
      conf:
        source: sqlmesh
```

Or kwargs: `SQLMeshDAGGenerator(..., model_triggers={"dwh.rt_fraud_da_set": "etl_rt_fraud_da_unload"})`.

**Priority:** explicit `model_triggers` > tags.  
**Pipeline-level** `trigger_dag_id` still runs after all leaf models (optional, separate).

---

## 🚀 Quick Start

### Simplest Usage (Dynamic Mode - Default)

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

# 1. Point to your SQLMesh project
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/your/sqlmesh/project",
    dag_id="my_pipeline"
)

# 2. Generate DAG (dynamic mode is default - fire and forget!)
dag_code = generator.generate_dynamic_dag()

# 3. Save it
with open("my_pipeline.py", "w") as f:
    f.write(dag_code)

# 4. Deploy to Airflow
# cp my_pipeline.py /opt/airflow/dags/
```

**That's it!** The DAG will auto-discover SQLMesh models at runtime. No regeneration needed when models change.

---

## 📋 Configuration

### Using Config File (Recommended for Production)

Create `config.yaml`:
```yaml
sqlmesh:
  project_path: "/path/to/your/sqlmesh/project"
  environment: "prod"

airflow:
  dag_id: "my_pipeline"
  schedule_interval: "@daily"
  tags: ["sqlmesh", "production"]
  default_args:
    owner: "data-team"
    retries: 2

generation:
  output_dir: "./dags"
  # mode: "dynamic" is the default!
```

Generate:
```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig

config = DAGGeneratorConfig.from_file("config.yaml")
generator = SQLMeshDAGGenerator(config=config)
dag_code = generator.generate_dynamic_dag()
```

---

## 🔄 Generation Modes

### Dynamic Mode (Default) ✨

**Fire and forget!** Place DAG once, it auto-discovers models at runtime.

```python
dag_code = generator.generate_dynamic_dag()
```

**Benefits:**
- ✅ No regeneration needed when models change
- ✅ Uses Airflow Variables for multi-environment
- ✅ Always in sync with SQLMesh project

**When to use:** Most use cases (recommended default)

### Static Mode

Pre-generates all task code for full control.

```python
dag_code = generator.generate_dag()  # Static mode
```

**Benefits:**
- ✅ Full control over generated code
- ✅ Faster DAG parse time

**When to use:** When you need to customize generated code or have very stable pipelines

See [Dynamic DAGs Documentation](DYNAMIC_DAGS.md) for details.

---

## 🌍 Multi-Environment Support

### Using Airflow Variables

Set in Airflow UI (Admin > Variables):

| Variable | Example Value | Description |
|----------|---------------|-------------|
| `sqlmesh_project_path` | `/opt/sqlmesh/project` | Path to SQLMesh project |
| `sqlmesh_environment` | `prod` | Environment name |
| `sqlmesh_gateway` | `production_db` | SQLMesh gateway (optional) |

The generated dynamic DAG automatically uses these, allowing the same DAG file to work across dev/staging/prod.

---

## 🎯 What You Get

### Input (Your SQLMesh Project):
```
models/
  ├── raw_orders.sql
  ├── stg_orders.sql      # depends on: raw_orders
  └── orders_summary.sql  # depends on: stg_orders
```

### Output (Airflow DAG):
```
Airflow Graph View:
  [sqlmesh_raw_orders] → [sqlmesh_stg_orders] → [sqlmesh_orders_summary]
```

- ✅ One Airflow task per SQLMesh model
- ✅ Dependencies match SQLMesh lineage
- ✅ Full data lineage visible in Airflow UI

---

## 🐛 Troubleshooting

### "Failed to load SQLMesh context"

**Check your SQLMesh `config.yaml`:**
```yaml
model_defaults:
  dialect: duckdb  # or postgres, snowflake, etc.

gateways:
  local:
    connection:
      type: duckdb
      database: 'db.db'

default_gateway: local
```

### "No models found"

**Verify SQLMesh can see your models:**
```bash
cd /path/to/your/sqlmesh/project
sqlmesh plan  # Should list your models
```

### "DAG not appearing in Airflow"

**Debug steps:**
1. Check file location: `ls /opt/airflow/dags/your_dag.py`
2. Verify syntax: `python /opt/airflow/dags/your_dag.py`
3. Check Airflow logs: `docker logs airflow-scheduler`

### "Syntax errors in generated DAG"

**Validate before deploying:**
```python
import ast
ast.parse(dag_code)  # Will raise SyntaxError if invalid
```

---

## 📚 See Also

- [Quick Start Guide](QUICKSTART.md) - Step-by-step tutorial
- [Dynamic DAGs](DYNAMIC_DAGS.md) - Deep dive into dynamic mode
- [Examples](../examples/) - Code examples
- [Contributing](../CONTRIBUTING.md) - How to contribute

