# SQLMesh DAG Generator

Generate Apache Airflow DAGs from SQLMesh projects - **no cloud dependencies required**.

Transform your SQLMesh models into production-ready Airflow DAGs with **full data lineage**, automatically!

## ✨ Key Features

- 🔥 **Dynamic DAG Generation (Default)**: Fire-and-forget - place DAG once, auto-discovers models at runtime
- 📅 **Auto-Scheduling**: Automatically detects DAG schedule from SQLMesh model intervals - no manual configuration!
- 🔐 **Runtime Connection Parametrization**: Pass database credentials via Airflow Connections - no hardcoded secrets!
- ✅ **Full Lineage in Airflow**: Each SQLMesh model = One Airflow task with proper dependencies
- 🌍 **Multi-Environment Support**: Use Airflow Variables + SQLMesh gateways for dev/staging/prod
- ⚡ **Incremental Models**: Proper handling with `data_interval_start/end`
- 🩺 **Integrity Guardrails**: Warn when sub-hourly incremental models run with `catchup=False`, with optional bounded recovery helpers
- 🎯 **Enhanced Error Handling**: SQLMesh-specific error messages in Airflow logs
- 🛠️ **Dual Mode**: Dynamic (auto-discovery, default) or Static (full control)
- 🚫 **No Vendor Lock-in**: Open source, no cloud dependencies

## ⚠️ Important: Gateway vs Environment

**SQLMesh uses "gateways" to switch between environments, NOT an "environment" parameter.**

```python
# ❌ WRONG - environment parameter is deprecated
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    environment="prod",  # This doesn't work!
)

# ✅ CORRECT - Use gateway to switch environments
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod"  # This is how you select your environment!
)
```

**See [Multi-Environment Configuration Guide](docs/MULTI_ENVIRONMENT.md) for complete setup instructions.**

## 🚀 Quick Start (3 Steps)

### 1. Install
```bash
pip install sqlmesh-dag-generator  # (when published)
# OR
git clone <repo> && cd SQLMeshDAGGenerator && pip install -e .
```

### 2. Generate DAG (Dynamic Mode - Default!)
```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

# Point to your SQLMesh project
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/your/sqlmesh/project",
    dag_id="my_pipeline",
    schedule_interval="@daily"
)

# Generate dynamic DAG (default - fire and forget!)
dag_code = generator.generate_dynamic_dag()

# Save it
with open("my_pipeline.py", "w") as f:
    f.write(dag_code)
```

### 3. Deploy to Airflow
```bash
cp my_pipeline.py /opt/airflow/dags/
```

**That's it! 🎉** Your SQLMesh models are now orchestrated by Airflow. The DAG will auto-discover models at runtime - no regeneration needed when models change!

## Recovery And Completeness

SQLMesh DAG Generator forwards Airflow's `data_interval_start` and `data_interval_end` into `ctx.run(start=..., end=...)`.
That means the package executes the interval Airflow gives it, but it does **not** invent missed Airflow runs on its own.

If you run sub-hourly incremental models with `catchup=False`, outages can leave completeness gaps unless you replay the missed windows.

The package now supports an explicit recovery policy:

- `recovery_mode="disabled"` (default): no runtime recovery tasks are added.
- `recovery_mode="warn"`: add an integrity guard task that detects missing intervals and logs them.
- `recovery_mode="bounded_auto"`: add the same guard task plus a bounded recovery task that replays missing intervals when the gap is within `recovery_max_intervals`.

Example:

```python
generator = SQLMeshDAGGenerator(
  sqlmesh_project_path="/path/to/project",
  dag_id="my_pipeline",
  recovery_mode="bounded_auto",
  recovery_max_intervals=6,
)
```

When `recovery_mode` is enabled, the package adds stable helper tasks to the DAG instead of mutating the graph at runtime:

- `sqlmesh_integrity_guard`
- `sqlmesh_recovery_backfill` in `bounded_auto` mode

This keeps recovery explicit and observable in Airflow while preserving the default "no surprise backfills" behavior.

## 💡 What You Get

### Your SQLMesh Project:
```
my_project/
└── models/
    ├── raw_orders.sql
    ├── stg_orders.sql      # depends on raw_orders
    └── orders_summary.sql  # depends on stg_orders
```

### Generated Airflow DAG:
```
Airflow Graph View:
  [raw_orders] → [stg_orders] → [orders_summary]
  
✅ Each model = separate task
✅ SQLMesh dependencies = Airflow dependencies  
✅ Full lineage visible in Airflow UI
```

## 📚 Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Step-by-step tutorial (start here!)
- **[Quick Reference](docs/QUICK_REFERENCE.md)** - One-page cheat sheet
- **[Auto-Scheduling Guide](docs/AUTO_SCHEDULING.md)** - Automatic schedule detection 📅 NEW!
- **[Runtime Configuration](docs/RUNTIME_CONFIGURATION.md)** - Pass credentials via Airflow Connections 🔐
- **[Multi-Environment Setup](docs/MULTI_ENVIRONMENT.md)** - Configure for dev/staging/prod ⚠️ IMPORTANT
- **[Migration Guide](docs/MIGRATION_GUIDE.md)** - Fix common configuration issues
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions
- **[Usage Guide](docs/USAGE.md)** - Complete reference
- **[Dynamic DAGs](docs/DYNAMIC_DAGS.md)** - Fire-and-forget mode explained
- **[Deployment Warnings](docs/DEPLOYMENT_WARNINGS.md)** - Critical production considerations
- **[Examples](examples/)** - Code examples
- **[Architecture](docs/ARCHITECTURE.md)** - Technical details

## 🔥 Why Dynamic Mode (Default)?

**Dynamic mode** auto-discovers SQLMesh models at runtime:

```python
dag_code = generator.generate_dynamic_dag()  # Default behavior!
```

**Benefits:**
- ✅ **No regeneration needed** when SQLMesh models change
- ✅ **Always in sync** - DAG updates automatically
- ✅ **Multi-environment** - Uses Airflow Variables
- ✅ **Production-ready** - Enhanced error handling

Want static mode instead? Just use `generator.generate_dag()` - see [Usage Guide](docs/USAGE.md).

## 🎯 Simple Example

The simplest possible usage - just 3 lines of code:

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/your/sqlmesh/project",
    dag_id="my_pipeline"
)

dag_code = generator.generate_dynamic_dag()
```

See [examples/simple_generate.py](examples/simple_generate.py) for a complete runnable example.

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

[Your License Here]

---

**Built with ❤️ for the data engineering community**

### Configuration File

Create a `dag_generator_config.yaml`:

```yaml
sqlmesh:
  project_path: "/path/to/sqlmesh/project"
  environment: "prod"
  gateway: "local"

airflow:
  dag_id: "sqlmesh_pipeline"
  schedule_interval: "0 0 * * *"
  default_args:
    owner: "data-team"
    retries: 3
    retry_delay_minutes: 5
  tags:
    - sqlmesh
    - analytics

generation:
  output_dir: "/path/to/airflow/dags"
  operator_type: "python"  # or "bash"
  include_tests: true
  parallel_tasks: true
```

## How It Works

1. **Load SQLMesh Project**: Reads your SQLMesh project configuration and models
2. **Extract Dependencies**: Analyzes SQL queries to build dependency graph
3. **Generate Tasks**: Creates Airflow tasks for each SQLMesh model
4. **Set Dependencies**: Connects tasks based on model dependencies
5. **Apply Schedules**: Preserves cron schedules and execution logic
6. **Output DAG**: Generates Python file ready for Airflow

## Architecture

```
SQLMesh Project
    ↓
SQLMeshDAGGenerator
    ├── Context Loader (loads SQLMesh context)
    ├── Model Parser (extracts model metadata)
    ├── Dependency Resolver (builds dependency graph)
    └── DAG Builder (generates Airflow DAG)
    ↓
Airflow DAG File
```

## Advanced Features

### Custom Operators

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator
from airflow.operators.python import PythonOperator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    custom_operator_class=PythonOperator,
    operator_kwargs={"provide_context": True}
)
```

### Model Filtering

```python
# Generate DAG for specific models only
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    include_models=["model1", "model2"],
    exclude_models=["test_*"]
)
```

### Dynamic Task Generation

```python
# Generate tasks with dynamic parallelism
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    enable_dynamic_tasks=True,
    max_parallel_tasks=10
)
```

## ⚠️ Important: Deployment Warnings

### 🔴 Distributed Airflow Requires Shared Volume

If you're using **KubernetesExecutor**, **CeleryExecutor**, or any distributed Airflow setup:

**Your SQLMesh project MUST be accessible to all workers!**

**Solutions:**
- **Option 1 (Recommended):** Mount project on shared volume (EFS/NFS/Filestore)
- **Option 2:** Bake project into Docker image (loses fire-and-forget benefit)

**See full guide:** [docs/DEPLOYMENT_WARNINGS.md](docs/DEPLOYMENT_WARNINGS.md)

### 🟡 Operator Type Limitations

- **Dynamic Mode:** Python operator only (current limitation)
- **Static Mode:** Supports Python, Bash, and Kubernetes operators

For Bash/Kubernetes in dynamic mode, use static generation for now.

### 🟢 Kubernetes Operator Support

To use `operator_type: kubernetes`:
```yaml
generation:
  operator_type: kubernetes
  docker_image: "your-registry/sqlmesh:v1.0"  # REQUIRED
  namespace: "data-pipelines"
```

**📖 Full Documentation:** [docs/DEPLOYMENT_WARNINGS.md](docs/DEPLOYMENT_WARNINGS.md)

## Requirements

- Python >= 3.8
- Apache Airflow >= 2.0
- SQLMesh >= 0.20.0

## Development

```bash
# Clone the repository
git clone https://github.com/yourusername/sqlmesh-dag-generator.git
cd sqlmesh-dag-generator

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
black .
ruff check .
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Comparison with Tobiko Cloud

| Feature | Tobiko Cloud | SQLMesh DAG Generator |
|---------|-------------|----------------------|
| Cost | Paid | **Free & Open Source** |
| Deployment | Cloud-based | **Self-hosted** |
| Customization | Limited | **Fully Customizable** |
| Privacy | External | **On-premise** |
| Dependencies | Cloud connection | **None** |

## Support

- 📖 [Documentation](https://github.com/yourusername/sqlmesh-dag-generator/docs)
- 🐛 [Issue Tracker](https://github.com/yourusername/sqlmesh-dag-generator/issues)
- 💬 [Discussions](https://github.com/yourusername/sqlmesh-dag-generator/discussions)

