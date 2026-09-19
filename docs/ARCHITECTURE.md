# Project Architecture

## Project Structure

```
SQLMeshDAGGenerator/
├── sqlmesh_dag_generator/       # Main package
│   ├── __init__.py              # Package exports
│   ├── config.py                # Configuration models
│   ├── models.py                # Data models
│   ├── generator.py             # Main generator class
│   ├── dag_builder.py           # DAG code builder
│   ├── cli.py                   # CLI interface
│   └── utils.py                 # Utilities
├── examples/                     # Usage examples
│   ├── simple_generate.py       # Minimal example
│   ├── complete_example.py      # All patterns
│   └── *.yaml                   # Config templates
├── tests/                        # Test suite
├── docs/                         # Documentation
│   ├── QUICKSTART.md            # Getting started
│   ├── USAGE.md                 # Usage guide
│   └── SELECTION.md            # Model selection syntax
├── README.md                     # Package overview
└── CONTRIBUTING.md               # Contribution guide
```

## Core Components

### 1. SQLMeshDAGGenerator (`generator.py`)

Main entry point for the package.

**Key Methods:**
- `generate_dynamic_dag()` - Generate dynamic DAG (default, fire & forget)
- `generate_dag()` - Generate static DAG (full control)
- `extract_models()` - Extract SQLMesh models and dependencies
- `build_dag_structure()` - Build DAG structure from models

### 2. AirflowDAGBuilder (`dag_builder.py`)

Builds Airflow DAG Python code.

**Key Methods:**
- `build_dynamic()` - Generate dynamic DAG code with runtime discovery
- `build()` - Generate static DAG code with pre-defined tasks

### 3. Configuration (`config.py`)

Data classes for configuration:
- `DAGGeneratorConfig` - Main configuration
- `SQLMeshConfig` - SQLMesh project settings
- `AirflowConfig` - Airflow DAG settings
- `GenerationConfig` - Generation options

### 4. Models (`models.py`)

Data models:
- `SQLMeshModelInfo` - Represents a SQLMesh model
- `DAGStructure` - Represents the complete DAG structure

## Generation Flow

### Dynamic Mode (Default)

```
1. User creates generator
   └─> SQLMeshDAGGenerator(project_path, dag_id)

2. User calls generate_dynamic_dag()
   └─> Loads SQLMesh context
   └─> Extracts models and dependencies
   └─> Builds DAG structure
   └─> AirflowDAGBuilder.build_dynamic()
       └─> Generates Python code that:
           - Loads SQLMesh context at DAG parse time
           - Discovers models dynamically
           - Creates tasks for each model
           - Sets up dependencies

3. Generated DAG runs in Airflow
   └─> Airflow parses DAG
   └─> DAG discovers SQLMesh models at runtime
   └─> Creates tasks dynamically
   └─> Executes tasks using SQLMesh
```

### Static Mode

```
1. User creates generator
   └─> SQLMeshDAGGenerator(project_path, dag_id)

2. User calls generate_dag()
   └─> Loads SQLMesh context
   └─> Extracts models and dependencies
   └─> Builds DAG structure
   └─> AirflowDAGBuilder.build()
       └─> Generates Python code with:
           - Pre-defined tasks for each model
           - Hardcoded dependencies
           - Static configuration

3. Generated DAG runs in Airflow
   └─> Airflow parses DAG
   └─> DAG has all tasks pre-defined
   └─> Executes tasks using SQLMesh
```

## Key Design Decisions

### 1. Dynamic Mode as Default

**Rationale:** Most users want "fire and forget" - place DAG once, it auto-updates.

**Implementation:** DAG code includes SQLMesh context loading and model discovery.

### 2. Airflow Variables for Configuration

**Rationale:** Multi-environment support without code changes.

**Implementation:** Generated DAGs use `Variable.get()` with fallback defaults.

### 3. One Task Per Model

**Rationale:** Full lineage visibility in Airflow UI.

**Implementation:** Each SQLMesh model becomes a separate `PythonOperator`.

### 4. Proper Incremental Handling

**Rationale:** Incremental models need correct time ranges.

**Implementation:** Use `data_interval_start/end` (Airflow 2.2+) instead of deprecated `execution_date`.

## Extension Points

### Custom Operators

Modify `dag_builder.py` to use different operators:
```python
if self.config.generation.operator_type == "custom":
    return self._build_custom_task(model_info, task_id)
```

### Model Filtering

Extend `GenerationConfig`:
```python
include_models: Optional[List[str]] = None
exclude_models: Optional[List[str]] = None
```

### Task Grouping

Future enhancement - group models into fewer tasks:
```python
task_grouping: str = "model"  # "model" | "domain" | "custom"
```

## Dependencies

### Core:
- `sqlmesh` - SQLMesh integration
- `pyyaml` - Configuration files
- `dataclasses` - Data models (Python 3.7+)

### Optional:
- `apache-airflow` - For running generated DAGs (not required for generation)

## Testing Strategy

- Unit tests for each component
- Integration tests for full generation flow
- Validation tests for generated DAG syntax

See `tests/` directory for test suite.

## Performance Considerations

### DAG Parse Time

Dynamic mode adds ~0.5-1s to DAG parse time for loading SQLMesh context.

**Optimization:** Context caching (future enhancement)

### Large Projects

For 100+ models, consider:
- Task grouping (reduce total tasks)
- Multiple DAGs (split by domain/tag)
- Static mode (faster parse time)

## Code Style

- PEP 8 compliance
- Type hints throughout
- Docstrings for all public methods
- Logging for debugging

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

