# Model selection

Describing which models belong in a DAG as a list of fully qualified names does not
survive contact with a growing project. This package borrows the selection syntax from
`dbt ls --select` (and `sqlmesh plan --select-model`) and evaluates it against the
SQLMesh model graph.

```python
generator = SQLMeshDAGGenerator(
    sqlmesh_project_path="/opt/airflow/sqlmesh_project",
    select=["tag:finance+", "path:models/marts"],
    exclude=["tag:deprecated"],
)
```

```yaml
generation:
  select: ["tag:finance+"]
  exclude: ["tag:deprecated"]
```

Selection happens against the **full** model graph, so `tag:finance+` can walk through
models that `include_models` / `exclude_models` (the older, simpler filters) removed.
The two are then intersected, which keeps existing configuration working.

## Methods

| Method | Matches | Example |
|--------|---------|---------|
| *(none)* | model name, FQN or the last name part | `dwh.orders`, `orders` |
| `tag:` | a SQLMesh model tag | `tag:finance` |
| `path:` | the model file, relative to the project root | `path:models/marts` |
| `fqn:` / `name:` | same as no method, written explicitly | `fqn:dwh.*` |
| `kind:` | model kind | `kind:INCREMENTAL_BY_TIME_RANGE`, `kind:FULL` |
| `owner:` | the model owner | `owner:finance-team` |
| `project:` | the SQLMesh `project` field (multi-repo projects) | `project:core` |
| `interval:` | interval unit | `interval:FIVE_MINUTE` |
| `cron:` | the model cron string | `cron:"*/5 * * * *"` |
| `selector:` | a named selector from the config | `selector:nightly_core` |

Values support shell-style wildcards: `*`, `?`, `[abc]`. Matching is case-insensitive.
Model kinds can be written the way SQLMesh prints them (`IncrementalByTimeRangeKind`)
or the way they appear in a MODEL block (`INCREMENTAL_BY_TIME_RANGE`).

## Graph operators

| Operator | Meaning |
|----------|---------|
| `+model` | the model and all of its ancestors |
| `model+` | the model and all of its descendants |
| `2+model`, `model+2` | the same, limited to N levels |
| `@model` | the model, its descendants, and everything those descendants need |

Operators apply to whatever the atom matched, so `+tag:reporting*` is "everything
needed to build the reporting models".

## Combining selections

- **Whitespace, or several list entries, is a union**: `select: ["tag:a", "tag:b"]`
  and `select: ["tag:a tag:b"]` both mean "a or b".
- **A comma is an intersection**: `tag:gold,owner:finance` means "gold *and* owned by
  finance".
- **`exclude` subtracts** from whatever `select` produced.

Values containing spaces or commas have to be quoted, because whitespace and commas are
operators: `cron:"0 1,13 * * *"`.

## Named selectors

The dbt `selectors.yml` idea, kept in the same configuration file:

```yaml
selectors:
  nightly_core:
    description: Core marts and their upstreams, minus anything deprecated
    union:
      - "+tag:core"
      - "path:models/marts"
    exclude:
      - "tag:deprecated"
  gold_finance:
    intersection: ["tag:gold", "tag:finance"]
  # a plain string or list works too
  bronze: "tag:bronze"

generation:
  select: ["selector:nightly_core"]
```

Named selectors can reference each other; a cycle raises `SelectionError` rather than
hanging.

## Per-selection task settings

The same expressions configure Airflow task settings, which is the analogue of dbt's
`models:` config tree. Later entries win:

```yaml
generation:
  task_overrides:
    - select: ["tag:core"]
      pool: core_pool
    - select: ["tag:heavy"]
      pool: heavy_pool
      execution_timeout_minutes: 120
      retries: 1
      queue: big_workers
```

Supported keys: `pool`, `pool_slots`, `queue`, `retries`, `retry_delay_minutes`,
`execution_timeout_minutes`, `priority_weight`, `max_active_tis_per_dag`,
`sla_minutes`, `trigger_rule`.

## Checking a selection

```bash
sqlmesh-dag-gen -p /path/to/project --select "tag:finance+" --list-models
```

```python
from sqlmesh_dag_generator import explain_selection

explain_selection(generator.models, ["tag:finance+"], exclude=["tag:deprecated"])
```

## Differences from dbt

- There are no `state:`, `result:` or `source_status:` methods: SQLMesh keeps that
  state in the warehouse, and `sqlmesh plan` already computes what changed.
- `kind:` replaces `config.materialized:`, `owner:` covers what dbt calls `group:`.
- Tests are model audits in SQLMesh, so there is no `test_type:` selector; audits run
  with their model, or in their own task with `audit_tasks: true`.
