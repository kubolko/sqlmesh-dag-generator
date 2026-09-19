# One SQLMesh project, several Airflow DAGs

A SQLMesh project is one model graph. It is rarely one pipeline. Finance models run
every fifteen minutes and page whoever is on call; marketing models run nightly and
can wait until morning. Putting them in one DAG means one schedule, one alerting
policy and one failure blast radius for both.

A **DAG group** is a selection plus DAG settings:

```yaml
# config.yaml
sqlmesh:
  project_path: /opt/airflow/sqlmesh_project
  gateway: prod

airflow:
  dag_id: dwh            # fallback settings for every group
  start_date: "2024-01-01"
  default_args:
    owner: data-platform
    retries: 2

generation:
  auto_replan_on_change: false   # deploys live on their own DAG

dag_groups:
  - dag_id: dwh_finance
    select: ["tag:finance+"]
    schedule: "*/15 * * * *"
    tags: [sqlmesh, finance, oncall]

  - dag_id: dwh_marketing
    select: ["tag:marketing+"]
    exclude: ["tag:deprecated"]
    wait_for_upstream: dataset
    default_args:
      owner: marketing-analytics
      retries: 0
```

```python
# dags/dwh_sqlmesh.py
from sqlmesh_dag_generator import DAGGeneratorConfig, build_dag_groups

config = DAGGeneratorConfig.from_file("/opt/airflow/config/dag_generator_config.yaml")

for dag_id, dag in build_dag_groups(config).items():
    globals()[dag_id] = dag
```

The SQLMesh project is parsed **once** for all groups, which matters: loading a large
context is the expensive part of DAG parsing.

## Group settings

| Key | Default | Meaning |
|-----|---------|---------|
| `dag_id` | required | Airflow DAG id |
| `select` / `exclude` | all models | selection, see [SELECTION.md](SELECTION.md) |
| `schedule` | shortest interval among the group's models | cron or preset |
| `description`, `tags`, `catchup`, `max_active_runs`, `start_date`, `default_args` | from `airflow:` | per-group DAG settings |
| `wait_for_upstream` | `dataset` | how to depend on models owned by another group |
| `sensor_timeout_minutes`, `sensor_poke_interval_seconds` | 60 / 60 | sensor mode tuning |
| `generation_overrides` | `{}` | override any `generation:` setting for this group |

## Cross-group dependencies

If `dwh_marketing` reads a model that belongs to `dwh_finance`, the lineage crosses a
DAG boundary. Three options:

**`wait_for_upstream: dataset` (default).** The producing task publishes an Airflow
Dataset (Asset on Airflow 3) named `sqlmesh://models/<model>`, and the consuming DAG is
scheduled on those datasets instead of a clock - it runs when its inputs are actually
fresh. If the group also sets an explicit `schedule`, the cron wins and the datasets are
published but not used for scheduling (Airflow 2.4-2.8 cannot combine the two).

**`wait_for_upstream: sensor`.** The consuming DAG gets an `ExternalTaskSensor`
(`wait_for__<model>`, in reschedule mode) per upstream model. Sensors compare logical
dates, so this only works when the two DAGs share a schedule.

**`wait_for_upstream: none`.** The cross-group edges are only logged. Use it when the
groups are genuinely independent in time and you accept reading slightly stale data.

## Before you deploy

```bash
sqlmesh-dag-gen --config config.yaml --list-groups
```

```
dwh_finance  (schedule: */15 * * * *)
  select : tag:finance+
  models : 12
    - dwh.raw_orders
    ...
dwh_marketing  (schedule: @daily)
  select : tag:marketing+
  models : 4
  waits for (dataset):
    - dwh.stg_orders (from dwh_finance)
```

The planner warns about two things worth fixing:

- **models selected by more than one group** - they will run in both DAGs;
- **models in no group at all** - they will never run.

Pass `strict=True` to `build_dag_groups` to turn both warnings into errors, which is
the right setting for a CI check.

## Patterns that work

- **By tag** (`tag:finance+`) when ownership is already expressed in model tags.
- **By cadence** (`interval:FIVE_MINUTE`, `interval:DAY`) when the split is really
  about how often things run; the hot DAG stays small and its schedule stays honest.
- **By layer** (`path:models/staging`, `path:models/marts`) for a bronze/silver/gold
  warehouse where each layer has a different SLA.
- **By project** (`project:core`) in multi-repo SQLMesh setups, where `project` is
  already set on every model.
