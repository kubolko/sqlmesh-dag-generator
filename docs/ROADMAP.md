# Roadmap and ideas

Notes on what this package could adopt next, from SQLMesh releases and from dbt.
Nothing here is a promise; it is the shortlist that keeps coming up, with an honest
note on what each one costs.

Checked against SQLMesh 0.236.2 (September 2026) and dbt Core 1.11.

## Recently adopted (0.10.0)

| Idea | Where it came from |
|------|--------------------|
| Selection syntax with `tag:`, `path:`, `+`/`@`, unions and intersections | dbt node selection, `sqlmesh plan --select-model` |
| Named selectors in the config file | dbt `selectors.yml` |
| Per-selection task settings | dbt `models:` config tree |
| Several DAGs from one project, wired by Datasets | dbt Mesh / cross-project refs |
| Audits as their own tasks, gating children | `dbt build` |
| Unit test, lint, janitor, restate tasks | `sqlmesh test` / `lint` / `janitor` / restatement plans |
| `cron_tz`-aware due checks | SQLMesh 0.235.4 |
| `no_auto_upstream` on model runs | SQLMesh 0.230+ |
| Orchestration manifest and diff | dbt `manifest.json` |

## Decided, waiting for the next release

**`no_auto_upstream` becomes the default in 0.11.0.** One Airflow task per model is
the whole point of this package; SQLMesh re-resolving upstream inside each task is
duplicated work at best and two writers on one table at worst. It ships opt-in in
0.10.0 only so that a regression in this release is attributable to one change.

## From SQLMesh

**Per-model gateways.** SQLMesh models carry a `gateway` field, so one project can
write to two warehouses. The generator currently builds every task against one
gateway. Fix: group the task's context kwargs by `model.gateway`. Small change, real
value for multi-warehouse setups.

**Signals as sensors.** SQLMesh signals decide whether an interval is ready to run.
SQLMesh evaluates them inside `run`, so correctness is already handled - but a task
that blocks on an unready signal looks like a slow task in Airflow, not a waiting one.
Mapping signals onto deferrable sensors would make the waiting visible. Needs care:
signal evaluation is a Python call into the project.

**`exit_on_env_update`.** `Context.run(exit_on_env_update=...)` makes a long run stop
when someone promotes a new plan mid-run. On a hot-path DAG that is the difference
between "this run is now writing with stale code" and a clean retry.

**More plan flags on the deploy task.** `min_intervals`, `forward_only`,
`allow_destructive_models`, `empty_backfill`, `enable_preview`, `effective_from`. The
kwargs already get filtered per SQLMesh version, so exposing them is mostly config
plumbing plus documentation about what each one does to production.

**`table_diff` as a CI task.** `Context.table_diff` compares the same model across two
environments. As a PR check ("what does this change do to the data?") it is far more
convincing than a plan summary.

**`create_external_models`.** Refreshing external model schemas is a maintenance
chore that belongs next to the janitor task.

**A `blueprint:` selector.** Blueprint models expand into many models that share a
template; selecting "all instances of this blueprint" is currently a wildcard on the
name, which is fragile.

**dbt-project interop.** SQLMesh can run a dbt project, and those models keep dbt
metadata (`dbt_node_info`). A `dbt:` selector method, or mapping dbt tags and groups
onto our selections, would help teams mid-migration.

## From dbt

**`state:modified`.** The manifest this package writes already contains everything a
comparison needs, so `state:modified` against a previous manifest is implementable:
"build only what changed since main". Note that SQLMesh's plan already knows what
changed - the value is in *selecting Airflow tasks*, not in deciding backfills. SQLMesh
also ships `git:uncommitted`, which covers the local-development case.

**Source freshness.** dbt checks source freshness before building on top of it. The
SQLMesh equivalent would be a pre-flight check per external table (a max(timestamp)
query, or a signal), failing loudly instead of silently producing an empty increment.

**Exposures.** Per-model triggers already fire downstream DAGs. Declaring consumers in
one place (an `exposures` block in the config), rather than as tags on models, would
make "who breaks if this model breaks" answerable from the manifest.

**Auto-grouping.** `group_by: tag | owner | schema | interval` would generate DAG
groups without listing them, which suits projects where tags are already the
organising principle. Risk: DAG ids that change when a tag changes.

**Fail fast.** Airflow 2.7+ has `fail_fast` on the DAG; for a deploy DAG that is
usually what you want, and it is one config key away.

**A lineage page.** The manifest plus a small static HTML page would give the
"where does this number come from" answer to people who do not open Airflow.

## Deliberately not planned

- **Reimplementing SQLMesh state or scheduling.** SQLMesh owns intervals and
  snapshots. Every attempt to second-guess it ends in drift.
- **A cloud service.** The point of this package is that there isn't one.
- **dbt-style `--full-refresh` as a default.** Restatement is destructive; it stays an
  explicit, separately triggered task.
