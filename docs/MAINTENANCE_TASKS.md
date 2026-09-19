# Maintenance tasks

`sqlmesh run` is only part of operating a project. These helpers wrap the other SQLMesh
commands as Airflow tasks, with the same runtime connection handling and
`dag_run.conf` overrides as the rest of the package. Each returns a plain
`PythonOperator`.

## A deploy DAG

```python
from datetime import datetime, timedelta
from airflow import DAG
from sqlmesh_dag_generator import SQLMeshDAGGenerator

generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/opt/airflow/sqlmesh_project",
    gateway="prod",
    auto_replan_on_change=False,
)

with DAG("dwh_sqlmesh_deploy", schedule=None, start_date=datetime(2024, 1, 1)) as dag:
    tests = generator.create_unit_test_task(dag)
    lint = generator.create_lint_task(dag)
    deploy = generator.create_plan_apply_task(dag, execution_timeout=timedelta(hours=6))

    [tests, lint] >> deploy
```

## Unit tests - `create_unit_test_task`

Runs `Context.test()` (the project's `tests/` fixtures). Fails the task when any test
fails or errors, so it can gate a deploy. `match_patterns=[...]` narrows the run.

## Linter - `create_lint_task`

Runs the SQLMesh linter. Only error-level violations fail the task; warnings are
logged. On SQLMesh versions without a linter the task logs and succeeds, so the same
DAG file keeps working while a fleet upgrades. `raise_on_error=False` makes it
advisory.

## Audits - `create_audit_task`

Runs `Context.audit(start, end)` for the DAG's data interval. `models=[...]` limits the
scope, `blocking=False` downgrades a failure to a warning (the equivalent of a
warn-severity dbt test). `dag_run.conf` accepts `models`, `start`, `end`.

Per-model audit tasks are also available:

```yaml
generation:
  audit_tasks: true
```

Each model with audits then gets a `<model>__audit` task, and its **children wait for
the audit**, not just for the model - the SQLMesh equivalent of `dbt build`. Models
without audits get no extra task. With `emit_datasets` on, the dataset moves to the
audit task too: "this model is ready" should mean "and it passed its audits".

## Janitor - `create_janitor_task`

Runs `Context.run_janitor()`: drops expired environments and the physical tables behind
them. Worth a nightly DAG of its own on busy projects, where development environments
otherwise pile up. `environment="dev_jane"` (or `dag_run.conf["environment"]`) scopes
the cleanup; `ignore_ttl=True` ignores the configured TTL.

## Restatement - `create_restate_task`

Tells SQLMesh to forget what it has for a window and rebuild it, cascading downstream -
the closest thing to `dbt --full-refresh`, and different from a backfill, which only
fills intervals SQLMesh considers missing.

```python
with DAG("dwh_sqlmesh_restate", schedule=None, start_date=datetime(2024, 1, 1)) as dag:
    generator.create_restate_task(dag, default_start="2024-01-01")
```

Trigger it with `{"models": ["dwh.orders"], "start": "2024-05-01", "end": "2024-05-08"}`.

## Manual backfill - `create_manual_backfill_task`

Replays a historical window without restating anything. Takes `start`, `end` and
`models` from `dag_run.conf`; `end` defaults to now.

## Version tolerance

Every helper filters its keyword arguments against the installed SQLMesh signature
(`sqlmesh_dag_generator.ops_tasks.supported_kwargs`), and logs what it dropped. A DAG
file written against SQLMesh 0.236 keeps working on an older worker instead of failing
with `unexpected keyword argument`.
