# SQLMesh DAG Generator

Run your SQLMesh project from Airflow, with one Airflow task per SQLMesh model and
the real lineage between them. No Tobiko Cloud, no cloud dependency, no vendor lock-in.

```python
from airflow import DAG
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/opt/airflow/sqlmesh_project",
    gateway="prod",
)

with DAG("dwh_sqlmesh", schedule=generator.get_recommended_schedule(), ...) as dag:
    generator.create_tasks_in_dag(dag)
```

```
[raw_orders] -> [stg_orders] -> [orders_summary]
```

Every model becomes a task, model dependencies become task dependencies, and the
DAG schedule defaults to the shortest model interval in the project.

## Why

SQLMesh knows what needs to run and when. Airflow knows how to run things, retry
them, alert on them and show them to whoever is on call. The gap between the two is
usually a single `sqlmesh run` BashOperator - which works right up to the moment
someone asks "which model failed?" or "why did the finance table not refresh?".

This package closes that gap without giving up either side: SQLMesh still owns state,
intervals and correctness; Airflow gets a graph it can actually show you.

## Installation

```bash
pip install sqlmesh-dag-generator
```

Requires Python 3.9+, SQLMesh 0.228+ (CI runs 0.236.2) and Airflow 2.4+ (Airflow 3 is
supported through the compatibility layer in `sqlmesh_dag_generator.airflow_compat`).

## Gateways, not environments

SQLMesh "environments" are virtual environments for testing changes. They are *not*
how you switch between dev, staging and prod - that is what gateways are for:

```python
SQLMeshDAGGenerator(sqlmesh_project_path=..., gateway="prod")   # correct
SQLMeshDAGGenerator(sqlmesh_project_path=..., environment="prod")  # creates a virtual env
```

See [docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md) for the full explanation.

## Selecting models (dbt-style)

Instead of listing model names, describe the selection - the same way you would in
`dbt ls --select`:

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/opt/airflow/sqlmesh_project",
    select=["tag:finance+"],        # finance models and everything downstream
    exclude=["tag:deprecated"],
)
```

`tag:`, `path:`, `kind:`, `owner:`, `interval:`, `project:`, wildcards, `+`/`@` graph
operators, unions and intersections are all supported, and named selectors can live in
the config file. Full reference: [docs/SELECTION.md](docs/SELECTION.md).

Check a selection before deploying it:

```bash
sqlmesh-dag-gen -p /opt/airflow/sqlmesh_project --select "tag:finance+" --list-models
```

## One project, several DAGs

Finance runs every 15 minutes and pages the on-call. Marketing runs nightly. Same
SQLMesh project, different operational reality - so give them different DAGs:

```yaml
dag_groups:
  - dag_id: dwh_finance
    select: ["tag:finance+"]
    schedule: "*/15 * * * *"
  - dag_id: dwh_marketing
    select: ["tag:marketing+"]
    wait_for_upstream: dataset   # scheduled by the finance models it reads
```

```python
from sqlmesh_dag_generator import DAGGeneratorConfig, build_dag_groups

for dag_id, dag in build_dag_groups(DAGGeneratorConfig.from_file("config.yaml")).items():
    globals()[dag_id] = dag
```

Cross-group edges become Airflow Datasets (or `ExternalTaskSensor`s), so lineage
survives the split. Details: [docs/DAG_GROUPS.md](docs/DAG_GROUPS.md).

## Deploy path vs interval path

For large warehouses, do not run plan/apply on the DAG that runs intervals.

| DAG role | Setting | Task API |
|----------|---------|----------|
| Hot path (intervals only) | `auto_replan_on_change=False` | `create_tasks_in_dag(dag)` |
| Deploy path (model changes) | manual/triggered schedule | `create_plan_apply_task(dag)` |

```python
# Interval DAG - never blocks on a multi-hour backfill
generator = SQLMeshDAGGenerator(..., auto_replan_on_change=False)
with DAG("dwh_sqlmesh", ...) as dag:
    generator.create_tasks_in_dag(dag)

# Deploy DAG - plan + apply, gated by unit tests and the linter
with DAG("dwh_sqlmesh_deploy", schedule=None, ...) as dag:
    tests = generator.create_unit_test_task(dag)
    lint = generator.create_lint_task(dag)
    deploy = generator.create_plan_apply_task(dag)
    [tests, lint] >> deploy
```

`create_plan_apply_task` accepts `dag_run.conf` overrides: `plan_only`, `skip_backfill`.

## Maintenance tasks

| Task | What it runs |
|------|--------------|
| `create_unit_test_task` | `sqlmesh test` - unit tests before a deploy |
| `create_lint_task` | the SQLMesh linter |
| `create_audit_task` | `sqlmesh audit` for the DAG's interval |
| `create_janitor_task` | `sqlmesh janitor` - expired environments and orphaned tables |
| `create_restate_task` | restate a window of models (the `--full-refresh` equivalent) |
| `create_manual_backfill_task` | replay a historical window on demand |

See [docs/MAINTENANCE_TASKS.md](docs/MAINTENANCE_TASKS.md).

## What ends up in the Airflow UI

Each model task carries the model's owner, description, kind, cron (with `cron_tz`),
tags and audits as `doc_md`, so the task page answers "what is this?" without opening
the repository. Turn it off with `model_docs=False`.

Per-selection task settings replace copy-pasted operator kwargs:

```yaml
generation:
  task_overrides:
    - select: ["tag:heavy"]
      pool: heavy_pool
      execution_timeout_minutes: 120
      retries: 1
```

## Upstream handling

Every model already has its own Airflow task, so SQLMesh does not need to pull
upstream models in again:

```yaml
generation:
  no_auto_upstream: true    # recommended; will become the default in 0.11.0
```

It is off by default in 0.10.0 so existing DAGs keep their current behaviour.

## Recovery and completeness

The package forwards Airflow's `data_interval_start` / `data_interval_end` into
`ctx.run(start=..., end=...)`. It runs the interval Airflow gives it - it does not
invent missed runs. With sub-hourly incremental models and `catchup=False`, an outage
leaves gaps unless you replay them, so there is an explicit policy:

- `recovery_mode="disabled"` - nothing is added.
- `recovery_mode="warn"` - a guard task detects and logs missing intervals.
- `recovery_mode="bounded_auto"` (default) - the guard plus a bounded replay task that
  catches up when the gap is within `recovery_max_intervals`.

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/opt/airflow/sqlmesh_project",
    recovery_mode="bounded_auto",
    recovery_max_intervals=6,
)
```

For anything larger, use `create_manual_backfill_task` in a separate unscheduled DAG;
it takes `start`, `end` and `models` from `dag_run.conf`.

## Mixed cadences

When a project mixes 5-minute and hourly models, the DAG ticks every 5 minutes and the
hourly tasks would otherwise pay the full SQLMesh context load just to do nothing. With
`skip_if_not_due` (default), a model that is not due returns
`{"status": "skipped", "reason": "not_due"}` before loading the context. Models with a
`cron_tz` are evaluated in their own timezone.

## Downstream DAG triggers

A model can trigger another DAG when it finishes - useful for unload or notification
pipelines. Either from the model's own SQLMesh tags:

```sql
MODEL (
  name dwh.fraud_scores,
  tags (rt, 'trigger_dag:etl_fraud_unload', 'trigger_conf:source=sqlmesh')
);
```

or from configuration (`generation.model_triggers`), which wins over tags.

## Orchestration manifest

```bash
sqlmesh-dag-gen --config config.yaml --manifest target/orchestration.json
```

The manifest lists every model with its task id, schedule, lineage and dataset URI.
`diff_manifests(old, new)` tells CI which Airflow tasks a pull request adds, removes or
reschedules (a renamed task means Airflow loses that task's history).

## Distributed Airflow

With KubernetesExecutor, CeleryExecutor or any distributed setup, the SQLMesh project
must be readable by every worker: mount it on a shared volume (EFS/NFS/Filestore), or
bake it into the image and regenerate on deploy.

## Documentation

- [Quick start](docs/QUICKSTART.md)
- [Quick reference](docs/QUICK_REFERENCE.md)
- [Model selection](docs/SELECTION.md)
- [DAG groups](docs/DAG_GROUPS.md)
- [Maintenance tasks](docs/MAINTENANCE_TASKS.md)
- [Auto-scheduling](docs/AUTO_SCHEDULING.md)
- [Environments and gateways](docs/ENVIRONMENTS.md)
- [Usage reference](docs/USAGE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap and ideas](docs/ROADMAP.md)
- [Examples](examples/)

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check sqlmesh_dag_generator tests
black --check sqlmesh_dag_generator tests
```

## Contributing

Bug reports and pull requests are welcome - see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE).
