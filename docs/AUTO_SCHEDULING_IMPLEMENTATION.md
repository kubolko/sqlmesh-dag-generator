# Auto-Scheduling Feature Implementation Summary

## 🎯 Feature Overview

Implemented automatic DAG schedule detection based on SQLMesh model `interval_unit` values. The package now intelligently determines the optimal Airflow DAG schedule by analyzing all SQLMesh models and selecting the shortest (most frequent) interval.

## ✨ What Was Added

### 1. Core Functionality

#### `sqlmesh_dag_generator/utils.py`
- **`interval_to_cron(interval_unit)`**: Converts SQLMesh IntervalUnit to Airflow cron expressions
- **`get_interval_frequency_minutes(interval_unit)`**: Returns frequency in minutes for comparison
- **`get_minimum_interval(interval_units)`**: Finds the most frequent interval from a list

#### `sqlmesh_dag_generator/generator.py`
- **`get_recommended_schedule()`**: Analyzes all models and returns optimal schedule
- **`get_model_intervals_summary()`**: Groups models by their interval_unit for inspection
- **`auto_schedule` parameter**: New initialization parameter (default: True)

#### `sqlmesh_dag_generator/config.py`
- **`AirflowConfig.auto_schedule`**: Boolean flag to enable/disable auto-scheduling (default: True)

#### `sqlmesh_dag_generator/dag_builder.py`
- Updated dynamic DAG generation to support auto-scheduling
- Generates runtime schedule detection code when `auto_schedule=True`
- Properly references `RECOMMENDED_SCHEDULE` variable in generated DAGs

### 2. Examples

#### `examples/simple_generate.py`
- Updated to demonstrate auto-scheduling
- Shows how to use `get_recommended_schedule()`
- Displays model intervals summary

#### `examples/5_custom_schedule.py` (NEW)
- Shows 3 different approaches:
  - Full auto (inspect and use recommended)
  - Manual override (disable auto-scheduling)
  - Smart scheduling (inspect then decide with throttling)

### 3. Documentation

#### `docs/AUTO_SCHEDULING.md` (NEW)
- Complete guide to auto-scheduling feature
- How it works explanation
- Configuration options
- Best practices
- Examples and use cases

#### Updated Files
- `README.md`: Added auto-scheduling to key features
- `CHANGELOG.md`: Documented v0.4.0 with auto-scheduling feature

### 4. Tests

#### `tests/test_auto_schedule.py` (NEW)
- 16 comprehensive tests covering:
  - Interval to cron conversion
  - Frequency calculations
  - Minimum interval detection
  - Auto-schedule configuration
  - Integration workflows

## 📊 Supported Intervals

| SQLMesh Interval | Airflow Cron | Frequency |
|-----------------|--------------|-----------|
| MINUTE | `* * * * *` | Every minute |
| FIVE_MINUTE | `*/5 * * * *` | Every 5 minutes |
| QUARTER_HOUR | `*/15 * * * *` | Every 15 minutes |
| HALF_HOUR | `*/30 * * * *` | Every 30 minutes |
| HOUR | `@hourly` | Every hour |
| DAY | `@daily` | Daily |
| WEEK | `@weekly` | Weekly |
| MONTH | `@monthly` | Monthly |
| QUARTER | `0 0 1 */3 *` | Quarterly |
| YEAR | `@yearly` | Yearly |

## 🚀 Usage

### Basic Usage (Auto-Schedule Enabled by Default)

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    # auto_schedule=True  # Default!
)

# Get recommended schedule
recommended = generator.get_recommended_schedule()

# Use in DAG
with DAG(
    "my_dag",
    schedule=recommended,
    ...
) as dag:
    generator.create_tasks_in_dag(dag)
```

### Disable Auto-Scheduling

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    schedule_interval="@hourly",  # This disables auto_schedule
)
```

### Inspect Before Using

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
)

# Check what's recommended
print(f"Recommended: {generator.get_recommended_schedule()}")

# See interval distribution
summary = generator.get_model_intervals_summary()
for interval, models in summary.items():
    print(f"{interval}: {len(models)} models")
```

## 🎯 How It Works

1. **Model Analysis**: Generator loads SQLMesh context and inspects all models
2. **Interval Collection**: Extracts `interval_unit` from each model
3. **Minimum Detection**: Finds the shortest interval (most frequent)
4. **Cron Conversion**: Converts SQLMesh interval to Airflow cron expression
5. **Schedule Application**: Uses the detected schedule in the DAG

### Example Scenario

**Your Models:**
- `frequent_updates`: `interval_unit=FIVE_MINUTE` (5 minutes)
- `hourly_aggregates`: `interval_unit=HOUR` (60 minutes)
- `daily_summary`: `interval_unit=DAY` (1440 minutes)

**Result:**
- Recommended schedule: `*/5 * * * *` (every 5 minutes)
- DAG runs every 5 minutes
- SQLMesh's planner intelligently processes:
  - `frequent_updates`: Every 5 minutes
  - `hourly_aggregates`: Only when due (every hour)
  - `daily_summary`: Only when due (once per day)

**No separate DAGs needed!** SQLMesh handles the scheduling logic.

## ✅ Testing

All tests pass (83 total):
- 16 new tests for auto-scheduling functionality
- All existing tests continue to pass
- Integration tests verify end-to-end functionality

Run tests:
```bash
pytest tests/test_auto_schedule.py -v  # Auto-scheduling tests
pytest tests/ -v                        # All tests
```

## 📝 Configuration Options

### In `__init__`

```python
SQLMeshDAGGenerator(
    sqlmesh_project_path="/path",
    auto_schedule=True,           # Enable auto-detection
    schedule_interval=None,        # Override (disables auto_schedule)
    ...
)
```

### In Config File

```yaml
airflow:
  dag_id: "my_dag"
  auto_schedule: true             # Enable auto-detection
  schedule_interval: null         # Or override with specific schedule
```

## 🎨 Benefits

1. **Zero Configuration**: Works out of the box
2. **Self-Optimizing**: Adapts to your model intervals
3. **Dynamic Mode Compatible**: Schedule updates when models change
4. **Flexible**: Can override when needed
5. **Transparent**: Inspect recommendations before applying
6. **Production-Ready**: Thoroughly tested

## 🔄 Migration Path

### Existing Users

No breaking changes! If you're already setting `schedule_interval`, it continues to work:

```python
# This still works exactly as before
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path",
    schedule_interval="@daily"  # Your existing code
)
```

### New Users

Simply omit `schedule_interval` and auto-detection kicks in:

```python
# New recommended approach
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path",
    gateway="prod",
    # That's it! Schedule auto-detected
)
```

## 📚 Documentation

- **Main Guide**: `docs/AUTO_SCHEDULING.md`
- **Examples**: `examples/simple_generate.py`, `examples/5_custom_schedule.py`
- **API Reference**: See docstrings in `generator.py`

## 🎉 Version

Released in: **v0.4.0**

## 🔗 Related Features

Works seamlessly with:
- Dynamic DAG generation
- Multi-environment setup (gateways)
- Runtime credential parametrization
- All operator types (Python, Bash, Kubernetes)

---

**Next Steps:**
- Try the updated `examples/simple_generate.py`
- Read the full guide in `docs/AUTO_SCHEDULING.md`
- Test with your SQLMesh project!

