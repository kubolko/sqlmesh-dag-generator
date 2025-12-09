# Quick Reference - SQLMesh DAG Generator

**One-page cheat sheet for common tasks**

## 🚀 Installation

```bash
pip install sqlmesh-dag-generator  # (when published)
# OR
pip install -e .  # From source
```

## 📋 Basic Usage

### Simplest Possible (Auto-Everything!)

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator
from airflow import DAG
from datetime import datetime

# Create generator (auto-schedule enabled by default)
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
)

# Get auto-detected schedule
schedule = generator.get_recommended_schedule()

# Create DAG
with DAG(
    "my_dag",
    start_date=datetime(2024, 1, 1),
    schedule=schedule,  # Auto-detected!
    catchup=False,
) as dag:
    generator.create_tasks_in_dag(dag)
```

## 🎯 Common Patterns

### 1. With Airflow Connection (Recommended)

```python
from airflow.hooks.base import BaseHook

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    connection=BaseHook.get_connection("my_db_conn"),
)
```

### 2. With Connection ID

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    connection="my_db_conn",  # Just the ID
)
```

### 3. With Separate State Connection

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    connection="snowflake_prod",
    state_connection="postgres_state",
)
```

### 4. Manual Schedule Override

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    schedule_interval="@hourly",  # Disables auto-schedule
)
```

### 5. Inspect Then Decide

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
)

# Check recommendation
recommended = generator.get_recommended_schedule()
intervals = generator.get_model_intervals_summary()

print(f"Recommended: {recommended}")
print(f"Models: {intervals}")

# Use or override based on your needs
final_schedule = recommended if recommended != "* * * * *" else "@hourly"
```

## 📅 Auto-Scheduling

### How It Works

1. Analyzes all SQLMesh models
2. Finds shortest `interval_unit`
3. Converts to Airflow cron
4. DAG runs at that frequency
5. SQLMesh handles individual model schedules

### Supported Intervals

| SQLMesh | Airflow Cron | Runs |
|---------|--------------|------|
| `MINUTE` | `* * * * *` | Every minute |
| `FIVE_MINUTE` | `*/5 * * * *` | Every 5 min |
| `QUARTER_HOUR` | `*/15 * * * *` | Every 15 min |
| `HALF_HOUR` | `*/30 * * * *` | Every 30 min |
| `HOUR` | `@hourly` | Hourly |
| `DAY` | `@daily` | Daily |
| `WEEK` | `@weekly` | Weekly |
| `MONTH` | `@monthly` | Monthly |

### API Methods

```python
# Get recommended schedule
schedule = generator.get_recommended_schedule()

# See model distribution
summary = generator.get_model_intervals_summary()
# Returns: {'HOUR': ['model1', 'model2'], 'DAY': ['model3']}
```

## 🌍 Multi-Environment

### Using Gateways (Recommended)

```python
# Development
dev_gen = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="dev",  # Uses dev gateway from config.yaml
)

# Production
prod_gen = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",  # Uses prod gateway from config.yaml
)
```

### With Airflow Variables

```python
from airflow.models import Variable

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path=Variable.get("sqlmesh_project_path"),
    gateway=Variable.get("sqlmesh_gateway", "prod"),
)
```

## 🔐 Credential Parametrization

### Pass Connection at Runtime

```python
# Don't hardcode in config.yaml!
# Pass at runtime instead:
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    connection={
        "type": "postgres",
        "host": "{{ conn.my_db.host }}",
        "user": "{{ conn.my_db.login }}",
        "password": "{{ conn.my_db.password }}",
    }
)
```

### AWS Secrets Manager

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    connection="prod/database/credentials",
    credential_resolver="aws_secrets",
)
```

## 🔥 Dynamic vs Static DAGs

### Dynamic (Fire & Forget - Recommended)

```python
# Generate once, auto-updates forever
dag_code = generator.generate_dynamic_dag()

with open("dags/my_dag.py", "w") as f:
    f.write(dag_code)

# When models change, DAG updates automatically!
```

### Static (Full Control)

```python
# Regenerate when models change
dag_code = generator.generate_dag()

with open("dags/my_dag.py", "w") as f:
    f.write(dag_code)
```

### In-DAG (Direct Integration)

```python
# Best for complex DAGs
with DAG("my_dag", ...) as dag:
    # Your custom tasks
    start = DummyOperator(task_id="start")
    
    # Add SQLMesh tasks
    sqlmesh_tasks = generator.create_tasks_in_dag(dag)
    
    # Custom dependencies
    start >> list(sqlmesh_tasks.values())
```

## ⚙️ Configuration

### Python (Inline)

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    dag_id="my_pipeline",
    gateway="prod",
    auto_schedule=True,
    default_args={
        "owner": "data-team",
        "retries": 2,
    },
    tags=["sqlmesh", "production"],
    catchup=False,
)
```

### YAML File

```yaml
# config.yaml
sqlmesh:
  project_path: "/path/to/project"
  gateway: "prod"

airflow:
  dag_id: "my_pipeline"
  auto_schedule: true
  tags:
    - sqlmesh
    - production
  catchup: false
  default_args:
    owner: "data-team"
    retries: 2

generation:
  mode: "dynamic"
  operator_type: "python"
```

```python
from sqlmesh_dag_generator.config import DAGGeneratorConfig

config = DAGGeneratorConfig.from_file("config.yaml")
generator = SQLMeshDAGGenerator(config=config)
```

## 🎨 Operator Types

### Python (Default)

```python
generator = SQLMeshDAGGenerator(
    operator_type="python",  # Default
    ...
)
```

### Kubernetes

```python
generator = SQLMeshDAGGenerator(
    operator_type="kubernetes",
    docker_image="my-sqlmesh-image:latest",
    namespace="data-pipelines",
    ...
)
```

### Bash

```python
generator = SQLMeshDAGGenerator(
    operator_type="bash",
    ...
)
```

## 📊 Model Filtering

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    include_models=["model1", "model2"],  # Only these
    # OR
    exclude_models=["test_*"],  # Exclude patterns
)
```

## 🐛 Debugging

### Check Generated Code

```python
# Generate and inspect
dag_code = generator.generate_dynamic_dag()
print(dag_code)  # See exactly what will be deployed
```

### Validate Before Deploy

```python
import ast

dag_code = generator.generate_dynamic_dag()

try:
    ast.parse(dag_code)
    print("✓ Valid Python syntax")
except SyntaxError as e:
    print(f"✗ Syntax error: {e}")
```

### Test SQLMesh Connection

```python
generator.load_sqlmesh_context()
models = generator.extract_models()
print(f"Found {len(models)} models")
for name in models:
    print(f"  - {name}")
```

## 🚨 Common Issues

### "Gateway not found"

```python
# ❌ Wrong: using 'environment'
generator = SQLMeshDAGGenerator(
    environment="prod",  # Deprecated!
)

# ✅ Correct: using 'gateway'
generator = SQLMeshDAGGenerator(
    gateway="prod",  # Use this!
)
```

### "Connection failed"

```python
# ✅ Pass connection at runtime
generator = SQLMeshDAGGenerator(
    connection=BaseHook.get_connection("my_db"),
    # Don't hardcode credentials!
)
```

### "Schedule too frequent"

```python
# Inspect and throttle
recommended = generator.get_recommended_schedule()

if recommended == "* * * * *":
    # Too frequent, override
    schedule = "*/15 * * * *"
else:
    schedule = recommended
```

## 📚 Documentation

- **[Auto-Scheduling Guide](AUTO_SCHEDULING.md)** - Complete auto-schedule docs
- **[Runtime Configuration](RUNTIME_CONFIGURATION.md)** - Credential management
- **[Multi-Environment Setup](MULTI_ENVIRONMENT.md)** - Gateway configuration
- **[Quick Start](QUICKSTART.md)** - Step-by-step tutorial
- **[Usage Guide](USAGE.md)** - Complete reference
- **[Dynamic DAGs](DYNAMIC_DAGS.md)** - Fire-and-forget mode

## 🔗 Examples

See `examples/` directory:
- `simple_generate.py` - Bare minimum
- `5_custom_schedule.py` - Schedule customization
- `4_multi_environment.py` - Multi-env setup
- `7_recommended_approach.py` - Best practices

## 💡 Best Practices

1. ✅ Use **dynamic mode** (fire & forget)
2. ✅ Enable **auto-scheduling** (default)
3. ✅ Use **gateways** for environments
4. ✅ Pass **credentials at runtime**
5. ✅ Use **Airflow Connections**
6. ❌ Don't hardcode credentials
7. ❌ Don't use deprecated `environment` parameter
8. ❌ Don't create separate DAGs per interval

## 🆘 Getting Help

- Check [Troubleshooting](TROUBLESHOOTING.md)
- Review [Examples](../examples/)
- Read [Architecture](ARCHITECTURE.md) for deep dive
- Open an issue on GitHub

---

**Quick Start:** Copy `examples/simple_generate.py` and modify for your project!

