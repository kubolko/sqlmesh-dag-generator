# SQLMesh DAG Generator - Project Summary

## Overview

**SQLMesh DAG Generator** is an open-source Python package that generates Apache Airflow DAGs from SQLMesh projects **without requiring Tobiko Cloud**. It provides a self-hosted, customizable alternative for integrating SQLMesh with Airflow.

## Project Structure

```
SQLMeshDAGGenerator/
├── sqlmesh_dag_generator/          # Main package
│   ├── __init__.py                 # Package initialization & exports
│   ├── generator.py                # Core DAG generator class
│   ├── config.py                   # Configuration management
│   ├── models.py                   # Data models
│   ├── dag_builder.py              # Airflow DAG code builder
│   ├── cli.py                      # Command-line interface
│   └── utils.py                    # Utility functions
├── tests/                          # Test suite
│   ├── test_generator.py           # Main generator tests (17 tests)
│   ├── test_config.py              # Configuration tests
│   ├── test_models.py              # Data model tests
│   └── test_utils.py               # Utility tests
├── examples/                       # Usage examples
│   ├── simple_generate.py          # Minimal example (⭐ start here)
│   ├── 1_dynamic_dag_example.py    # Production-ready example
│   ├── 2_generate_dag_file.py      # File generation approach
│   └── 3_using_config_file.py      # Configuration-based
├── docs/                           # Documentation
│   ├── QUICKSTART.md               # Getting started guide
│   ├── USAGE.md                    # Complete usage reference
│   ├── DYNAMIC_DAGS.md             # Dynamic mode deep-dive
│   └── ARCHITECTURE.md             # Technical details
├── setup.py                        # Package setup
├── requirements.txt                # Dependencies
├── README.md                       # Main documentation
├── CONTRIBUTING.md                 # Contribution guidelines
├── LICENSE                         # MIT License
└── .gitignore                      # Git ignore rules
```

## Key Components

### 1. SQLMeshDAGGenerator (generator.py)

The main class that orchestrates DAG generation:

- **create_tasks_in_dag(dag)**: 🔥 NEW - Creates tasks directly in a DAG (recommended)
- **generate_dynamic_dag()**: Generates dynamic DAG code (fire-and-forget)
- **generate_dag()**: Generates static DAG code (alternative approach)
- **load_sqlmesh_context()**: Loads SQLMesh project using Context API
- **extract_models()**: Extracts model information and dependencies
- **build_dag_structure()**: Builds task dependency graph
- **validate()**: Validates SQLMesh project before generation

**Usage:**
```python
# Approach 1: Use in DAG (Simplest! ⭐)
with DAG(...) as dag:
    generator = SQLMeshDAGGenerator(sqlmesh_project_path="...")
    generator.create_tasks_in_dag(dag)  # Done!

# Approach 2: Generate DAG file
generator = SQLMeshDAGGenerator(...)
dag_code = generator.generate_dynamic_dag()
```

### 2. Configuration System (config.py)

Flexible configuration using dataclasses:

- **SQLMeshConfig**: SQLMesh project settings
- **AirflowConfig**: Airflow DAG configuration
- **GenerationConfig**: Code generation options
- **DAGGeneratorConfig**: Complete configuration container

Supports:
- YAML configuration files
- Dictionary-based configuration
- Direct parameter initialization

### 3. Data Models (models.py)

- **SQLMeshModelInfo**: Represents a single SQLMesh model with metadata
- **DAGStructure**: Represents the complete DAG graph
  - Topological sorting
  - Circular dependency detection
  - Root/leaf node identification

### 4. DAG Builder (dag_builder.py)

Generates Airflow Python code:

- Creates imports and configuration
- Builds task definitions (Python, Bash, or Kubernetes operators)
- Sets up task dependencies
- Formats code with proper structure

### 5. CLI (cli.py)

Command-line interface with comprehensive options:

- Project path configuration
- Environment and gateway selection
- DAG scheduling and tagging
- Model filtering
- Validation and dry-run modes

### 6. Utilities (utils.py)

Helper functions for:

- Task ID sanitization
- Cron schedule parsing
- Circular dependency detection
- Model lineage tracking
- DAG complexity estimation

## How It Works

### Workflow

```
1. Load SQLMesh Project
   ↓
2. Extract Models & Dependencies
   ↓
3. Build Dependency Graph
   ↓
4. Validate (circular deps, missing models)
   ↓
5. Generate Airflow DAG Code
   ↓
6. Write to File (or return as string)
```

### SQLMesh Integration

The generator uses SQLMesh's official Python API:

```python
from sqlmesh import Context

# Load SQLMesh project
ctx = Context(paths=project_path, gateway=gateway)

# Access models
models = ctx._models  # or ctx.models

# Each model has:
# - name: Model identifier
# - depends_on: Set of dependencies
# - kind: FULL, INCREMENTAL, etc.
# - cron: Scheduling information
# - owner, tags, description: Metadata
```

### Dependency Resolution

Uses **Kahn's Algorithm** for topological sorting:

1. Calculate in-degree for each model
2. Queue models with zero dependencies
3. Process models in dependency order
4. Detect circular dependencies if sort incomplete

## Generated DAG Structure

```python
# Generated DAG file structure:

# 1. Header with metadata
"""
Airflow DAG generated from SQLMesh project
DAG ID: my_pipeline
Generated: 2025-12-01T...
"""

# 2. Imports
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlmesh import Context

# 3. Configuration
SQLMESH_PROJECT_PATH = "/path/to/project"
SQLMESH_ENVIRONMENT = "prod"

# 4. DAG definition
dag = DAG(
    dag_id="my_pipeline",
    default_args={...},
    schedule_interval="0 0 * * *",
    ...
)

# 5. Task functions
def execute_sqlmesh_model1(**context):
    ctx = Context(paths=SQLMESH_PROJECT_PATH)
    ctx.run(
        environment=SQLMESH_ENVIRONMENT,
        select_models=["model1"],
        ...
    )

# 6. Task operators
model1_task = PythonOperator(
    task_id="sqlmesh_model1",
    python_callable=execute_sqlmesh_model1,
    dag=dag,
)

# 7. Dependencies
model1_task >> model2_task >> model3_task
```

## Features

✅ **Automatic Dependency Resolution**: Analyzes SQL to determine model dependencies

✅ **Multiple Operator Types**: Python, Bash, or Kubernetes operators

✅ **Model Filtering**: Include/exclude specific models

✅ **Schedule Preservation**: Honors SQLMesh cron schedules

✅ **Validation**: Checks for circular dependencies and missing models

✅ **Flexible Configuration**: YAML files, Python dicts, or direct parameters

✅ **CLI Support**: Full command-line interface

✅ **Type Safety**: Uses Python type hints throughout

✅ **Well-Tested**: Comprehensive test suite

## Usage Patterns

### 1. Simple Generation

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    dag_id="my_dag"
)
dag_code = generator.generate_dag()
```

### 2. With Configuration

```python
config = DAGGeneratorConfig.from_file("config.yaml")
generator = SQLMeshDAGGenerator(config=config)
dag_code = generator.generate_dag()
```

### 3. CLI

```bash
sqlmesh-dag-gen \
    --project-path /path/to/project \
    --dag-id my_dag \
    --output-dir ./dags
```

## Dependencies

- **sqlmesh** >= 0.20.0: SQLMesh framework
- **apache-airflow** >= 2.0.0: Airflow integration
- **pyyaml** >= 5.4.0: YAML configuration support

## Development

```bash
# Clone and setup
git clone <repo-url>
cd sqlmesh-dag-generator
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black .
ruff check . --fix

# Type check
mypy sqlmesh_dag_generator
```

## Testing

Comprehensive test suite covering:

- Configuration loading and validation
- Model extraction and dependency resolution
- DAG structure validation
- Topological sorting
- Circular dependency detection
- Utility functions

Run tests:
```bash
pytest
pytest --cov=sqlmesh_dag_generator  # with coverage
```

## Future Enhancements

Potential features for future versions:

1. **Smart Scheduling**: Automatic schedule inference from model dependencies
2. **Dynamic DAGs**: Runtime DAG generation in Airflow
3. **Sensor Support**: Add Airflow sensors for external dependencies
4. **Retry Logic**: Model-specific retry strategies
5. **Notifications**: Email/Slack notifications for failures
6. **Metrics**: Integration with Airflow metrics and monitoring
7. **Documentation Generation**: Auto-generate DAG documentation
8. **CI/CD Integration**: GitHub Actions, GitLab CI templates
9. **Web UI**: Browser-based configuration and preview
10. **Multi-Environment**: Support for dev/staging/prod environments

## Comparison: Tobiko Cloud vs. This Generator

| Feature | Tobiko Cloud | SQLMesh DAG Generator |
|---------|-------------|----------------------|
| **Cost** | Paid service | Free & open source |
| **Deployment** | Cloud-hosted | Self-hosted |
| **Privacy** | Data sent to cloud | Fully on-premise |
| **Customization** | Limited | Fully customizable |
| **Dependencies** | Cloud connection | None (local only) |
| **Lock-in** | Vendor lock-in | No lock-in |
| **Flexibility** | Fixed features | Extend as needed |

## Contributing

We welcome contributions! See CONTRIBUTING.md for guidelines.

## License

MIT License - see LICENSE file

## Authors

Created as an open-source alternative to proprietary SQLMesh-Airflow integrations.

## Links

- GitHub: https://github.com/kubolko/sqlmesh-dag-generator
- Documentation: See docs/ directory
- Issues: GitHub Issues
- PyPI: (to be published)

---

**Version**: 0.1.0
**Status**: Alpha
**Python**: >= 3.8

