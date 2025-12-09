# Auto-Scheduling Guide

## 📅 Automatic Schedule Detection

SQLMesh DAG Generator can **automatically detect** the optimal Airflow DAG schedule based on your SQLMesh model intervals. No manual configuration needed!

## 🚀 Quick Start

### Default Behavior (Auto-Schedule Enabled)

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    # auto_schedule=True  # This is the default!
)

# Get the recommended schedule
recommended = generator.get_recommended_schedule()

# Use in your DAG
with DAG(
    "my_dag",
    schedule=recommended,  # Automatically matches your models!
    ...
) as dag:
    generator.create_tasks_in_dag(dag)
```

### Simplest Example

```python
# The generator does all the work!
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
)

recommended_schedule = generator.get_recommended_schedule()
# Returns: "*/5 * * * *" if you have 5-minute models
#          "@hourly" if hourly is your shortest interval
#          "@daily" if all models are daily or longer
```

## 🎯 How It Works

### 1. SQLMesh Models Define Intervals

In your SQLMesh models, you specify `interval_unit`:

```sql
-- models/frequent_updates.sql
MODEL (
  name my_db.frequent_updates,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column created_at
  ),
  interval_unit FIVE_MINUTE  -- Runs every 5 minutes
);

SELECT * FROM source_table;
```

```sql
-- models/hourly_aggregates.sql
MODEL (
  name my_db.hourly_aggregates,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column event_time
  ),
  interval_unit HOUR  -- Runs every hour
);

SELECT * FROM events;
```

```sql
-- models/daily_summary.sql
MODEL (
  name my_db.daily_summary,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column date
  ),
  interval_unit DAY  -- Runs daily
);

SELECT * FROM orders;
```

### 2. Generator Analyzes All Models

The generator inspects all models and finds the **shortest interval**:

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    auto_schedule=True,
)

# Internally analyzes:
# - frequent_updates: FIVE_MINUTE (5 minutes)
# - hourly_aggregates: HOUR (60 minutes)
# - daily_summary: DAY (1440 minutes)
# 
# Minimum: FIVE_MINUTE → Recommends "*/5 * * * *"
```

### 3. SQLMesh Handles the Rest

The DAG runs at the shortest interval (`*/5 * * * *`), but SQLMesh's planner is smart:

- **Every 5 minutes**: `frequent_updates` processes new data
- **Every hour (on the hour)**: `hourly_aggregates` processes when due
- **Every day (at midnight)**: `daily_summary` processes when due

**You don't need separate DAGs for different intervals!** SQLMesh tracks each model's last processed interval and only runs what's needed.

## 📊 Supported Intervals

| SQLMesh Interval | Airflow Cron | Frequency |
|-----------------|--------------|-----------|
| `MINUTE` | `* * * * *` | Every minute |
| `FIVE_MINUTE` | `*/5 * * * *` | Every 5 minutes |
| `TEN_MINUTE` | `*/10 * * * *` | Every 10 minutes |
| `QUARTER_HOUR` | `*/15 * * * *` | Every 15 minutes |
| `FIFTEEN_MINUTE` | `*/15 * * * *` | Alias for QUARTER_HOUR |
| `HALF_HOUR` | `*/30 * * * *` | Every 30 minutes |
| `THIRTY_MINUTE` | `*/30 * * * *` | Alias for HALF_HOUR |
| `HOUR` | `@hourly` | Every hour |
| `DAY` | `@daily` | Daily |
| `WEEK` | `@weekly` | Weekly |
| `MONTH` | `@monthly` | Monthly |
| `QUARTER` | `0 0 1 */3 *` | Quarterly |
| `YEAR` | `@yearly` | Yearly |

**Note:** If SQLMesh introduces new intervals in future versions, they will safely default to `@daily` until explicitly mapped.

## 🔍 Inspecting Your Schedule

### Get Model Intervals Summary

See which models run at which intervals:

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
)

summary = generator.get_model_intervals_summary()

print(summary)
# Output:
# {
#     'FIVE_MINUTE': ['frequent_updates', 'real_time_metrics'],
#     'HOUR': ['hourly_aggregates', 'user_sessions'],
#     'DAY': ['daily_summary', 'monthly_report']
# }
```

### Get Recommended Schedule

```python
recommended = generator.get_recommended_schedule()
print(f"Recommended schedule: {recommended}")
# Output: Recommended schedule: */5 * * * *
```

## ⚙️ Configuration Options

### Option 1: Full Auto (Default)

Let the generator decide everything:

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    # auto_schedule=True is default
)

with DAG(
    "auto_dag",
    schedule=generator.get_recommended_schedule(),
    ...
) as dag:
    generator.create_tasks_in_dag(dag)
```

### Option 2: Manual Override

Disable auto-scheduling and set your own:

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    schedule_interval="@hourly",  # This disables auto_schedule
)

# OR explicitly disable:
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    auto_schedule=False,
    schedule_interval="@daily",
)
```

### Option 3: Inspect Then Decide

Check the recommendation, then override if needed:

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
)

recommended = generator.get_recommended_schedule()
intervals = generator.get_model_intervals_summary()

print(f"Recommended: {recommended}")
print(f"Intervals: {intervals}")

# Decide based on your needs
if recommended == "*/5 * * * *":
    # Too frequent for production, throttle it
    final_schedule = "*/15 * * * *"
else:
    final_schedule = recommended

with DAG(
    "smart_dag",
    schedule=final_schedule,
    ...
) as dag:
    generator.create_tasks_in_dag(dag)
```

## 🎛️ Advanced: Throttling

If auto-detection suggests a schedule that's too frequent:

```python
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
)

recommended = generator.get_recommended_schedule()

# Define minimum acceptable interval (in minutes)
MINIMUM_INTERVAL_MINUTES = 15

# Mapping for comparison
schedule_to_minutes = {
    "* * * * *": 1,
    "*/5 * * * *": 5,
    "*/10 * * * *": 10,
    "*/15 * * * *": 15,
    "*/30 * * * *": 30,
    "@hourly": 60,
    "@daily": 1440,
}

recommended_minutes = schedule_to_minutes.get(recommended, 1440)

if recommended_minutes < MINIMUM_INTERVAL_MINUTES:
    # Throttle to minimum
    final_schedule = "*/15 * * * *"
    print(f"⚠️  Throttling {recommended} to {final_schedule}")
else:
    final_schedule = recommended

# Use final_schedule in your DAG
```

See [examples/5_custom_schedule.py](../examples/5_custom_schedule.py) for complete examples.

## 🌍 Multi-Environment Considerations

Auto-scheduling works seamlessly with multi-environment setups:

```python
# Development: Might run less frequently to save costs
dev_generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="dev",
    schedule_interval="@hourly",  # Override in dev
)

# Production: Use auto-detection for optimal performance
prod_generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    gateway="prod",
    auto_schedule=True,  # Let it optimize
)
```

## 📝 Dynamic DAG Mode

Auto-scheduling works in both static and dynamic modes:

### Static Mode

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    auto_schedule=True,
)

dag_code = generator.generate_dag()  # Static generation
# The generated code includes the detected schedule
```

### Dynamic Mode (Recommended)

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/path/to/project",
    auto_schedule=True,
)

dag_code = generator.generate_dynamic_dag()
# The generated DAG will detect schedule at runtime
# Automatically adapts if you add faster models later!
```

In dynamic mode, the schedule detection happens **every time Airflow parses the DAG**, so it automatically adapts to model changes!

## ⚠️ Important Notes

### 1. No Interval Specified

If models don't have `interval_unit` specified, the generator defaults to `@daily`:

```python
# Models without interval_unit
recommended = generator.get_recommended_schedule()
# Returns: "@daily"
```

### 2. Mixed Intervals

The generator always picks the **most frequent** (shortest) interval:

- If you have 1 model at `FIVE_MINUTE` and 99 models at `DAY`
- Recommended schedule: `*/5 * * * *`
- SQLMesh only processes the daily models when their interval is due

### 3. Cost Considerations

Running every minute/5 minutes can be expensive:

- **Development**: Override with less frequent schedule
- **Production**: Use auto-detection but monitor costs
- **Consider**: Throttling logic shown above

### 4. Airflow Scheduler Load

Very frequent DAG runs (every minute) can stress the Airflow scheduler:

- Monitor scheduler performance
- Consider throttling to 5-15 minute minimum
- Use task groups if you have 100+ models

## 🎯 Best Practices

### ✅ DO

- Use auto-scheduling in production for optimal data freshness
- Inspect the recommendation before deploying
- Throttle if necessary for cost/performance
- Use dynamic mode for automatic adaptation

### ❌ DON'T

- Don't blindly accept minute-level schedules without cost analysis
- Don't create separate DAGs for each interval (SQLMesh handles it!)
- Don't hardcode schedules when auto-detection works

## 🔗 Related Documentation

- [Simple Example](../examples/simple_generate.py)
- [Custom Schedule Example](../examples/5_custom_schedule.py)
- [Multi-Environment Guide](MULTI_ENVIRONMENT.md)
- [Dynamic DAGs Guide](DYNAMIC_DAGS.md)
- [Usage Guide](USAGE.md)

## 📊 Example Output

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/my/project",
)

print("📅 Recommended schedule:", generator.get_recommended_schedule())
print("📊 Model intervals:")
for interval, models in generator.get_model_intervals_summary().items():
    print(f"  {interval}: {len(models)} models")
    for model in models[:3]:  # Show first 3
        print(f"    - {model}")
    if len(models) > 3:
        print(f"    ... and {len(models) - 3} more")

# Output:
# 📅 Recommended schedule: */5 * * * *
# 📊 Model intervals:
#   FIVE_MINUTE: 2 models
#     - real_time_metrics
#     - live_dashboard
#   HOUR: 5 models
#     - hourly_aggregates
#     - user_sessions
#     - event_rollups
#     ... and 2 more
#   DAY: 12 models
#     - daily_summary
#     - monthly_report
#     - customer_segments
#     ... and 9 more
```

---

**Next Steps:**
- Try the [Simple Example](../examples/simple_generate.py)
- Explore [Custom Schedule Example](../examples/5_custom_schedule.py)
- Learn about [Dynamic DAGs](DYNAMIC_DAGS.md)

