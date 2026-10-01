# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.13.0] - 2026-10-01

### Added
- Tasks are labelled with the table they stand for. Model tasks show
  `dwh.orders`, source tasks `API_ODS.EVENTS (source)`, and with
  `task_id_prefix` the project goes first: `[snowflake] dwh.orders`. This is
  `task_display_name`; task ids are unchanged, so task history is kept.
  Airflow 2.9+ and 3.x. `generation.task_display_names: false` turns it off.
- Source tasks get a `doc_md` card: the table, its catalog and schema, and the
  models in the DAG that read it.
- Model cards list what the model reads (models and sources), what reads it,
  its grain, the time column of an incremental model, and its columns with
  types and comments. Types SQLMesh cannot infer are left blank instead of
  `UNKNOWN`. Wide tables are capped at 200 columns.
- Each model run logs the same lineage in three lines before loading SQLMesh,
  so the task instance log says what the run builds.
- `sqlmesh_dag_generator.task_docs` with the card builders, and
  `SQLMeshModelInfo.columns`, `column_descriptions`, `time_column`, `grains`.
- `generation.interval_window: sqlmesh`. A model task passes only the end of
  its run's data interval, `ctx.run(end=data_interval_end)`, and SQLMesh fills
  every interval its state says is missing up to that point. An outage or a
  failed run is caught up by the next run of the model, with no limit on the
  gap. `sqlmesh_integrity_guard` and `sqlmesh_recovery_backfill` are not
  created and `recovery_mode` is ignored. An Airflow 3 manual run with no
  logical date has no interval; it runs up to now. Generated Python, dynamic,
  Bash (`--end`) and Kubernetes (no `--start`) DAGs follow the same rule.
  Default stays `airflow`.

- `resolve_connections: task` with `parse_connection`. The warehouse and state
  connections are resolved inside each task, once per process, right before
  SQLMesh opens a session, instead of on every DAG parse. `connection` and
  `state_connection` also accept a function returning a connection id or dict.
  The project is loaded at parse time with `parse_connection` (same type and
  database, placeholder secrets) or, without it, with config.yaml as it is.
- `generator.select_tasks(selection, exclude=None)` returns the tasks
  `create_tasks_in_dag` made for a selection: `refresh >> generator.select_tasks(
  "interval:FIVE_MINUTE")`.
- A warning at load when an `external_models.yaml` sits where SQLMesh does not
  read it (anything but the project root and `external_models/`), with the
  number of unused declarations and of entries whose `columns` are a list.

### Changed
- **Unknown arguments to `SQLMeshDAGGenerator(...)` raise `TypeError`** with the
  closest valid name and the installed version. They used to be dropped, so a
  DAG written for a newer release ran on an older one with options missing.
- Every config field can now be passed to the constructor. `dry_run`, `mode`,
  `docker_image`, `namespace`, `max_parallel_tasks`, `start_date`,
  `description`, `env_vars` and `config_path` were silently ignored before;
  `dry_run=True` still wrote the DAG file.
- **External models are source nodes.** A table in `external_models.yaml` gets
  an `EmptyOperator` with id `source__<table>` - the id an undeclared source
  table already had - and a card with its description and columns. It used to
  get a `sqlmesh_<table>` task that loaded SQLMesh and ran nothing. External
  models no longer count for the auto-detected schedule, are not owned by a DAG
  group, and are not reported as unscheduled.
- `no_auto_upstream` stays off by default; the 0.11.0 plan to turn it on is
  dropped. With it, SQLMesh processes a model's intervals while its upstream has
  no data for them yet and marks them done. When enabled, it now applies only to
  models whose upstream models are all tasks in the same DAG.
- The manifest's `task_id` is the id in the DAG, including `task_id_prefix` and
  `source__` for external models.

### Fixed
- `resolve_credentials(dict, resolver_type="env")` returned the dict of variable
  names unchanged, so `credential_resolver="env"` never read the environment.
  A dict is now passed through only when no resolver is named; with one, the
  resolver runs. A ready-made connection dict with no `credential_resolver`
  behaves as before.
- Generated Bash DAGs were invalid Python for any real project: the quoted
  model FQN (`"db"."schema"."table"`) closed the `bash_command` string. The
  command is now written with `repr()` and the model and project path are
  shell-quoted.

### Notes
- Airflow 3 shows `doc_md` on the task page (`/dags/<dag>/tasks/<task>`, the
  task name in the Grid view), not on a task instance inside a run.
- Task labels and cards cover `create_tasks_in_dag` and DAG groups. Generated
  static and dynamic DAG files do not carry them.

## [0.12.0] - 2026-10-01

### Added
- `generation.task_id_prefix`. Set it on every project after the first when
  several SQLMesh projects are drawn into one Airflow DAG. Janitor, health
  check, integrity, recovery, the automatic replan task, downstream triggers,
  source nodes and model tasks all take the prefix. The same prefix is written
  into a generated DAG file. Unset, the ids stay `sqlmesh_janitor`, `source__*`
  and `sqlmesh_<model>`.
- `generation.dag_tick_minutes`. `skip_if_not_due` uses this as the Airflow
  timetable. Unset, the tick stays the shortest model in this project. Set it
  on a slower project that shares a DAG with a faster one. A generated DAG
  file embeds the same value as `EXPECTED_INTERVAL_MINUTES`.
- `create_plan_apply_task` still uses the `task_id` you pass. Two publish
  tasks in one DAG need two ids. The automatic replan inside
  `create_tasks_in_dag` prefixes its own id when `task_id_prefix` is set.

## [0.11.0] - 2026-09-30

### Changed
- **Publish backfills changed models.** `create_plan_apply_task` defaults to
  `generation.backfill_scope: changed`. It plans once, then applies a second plan
  whose `backfill_models` are the models added or directly modified in that diff.
  Interval gaps on every other model stay for the interval DAG. Projects that
  want the old behaviour (one `plan()`, backfill every gap) set
  `generation.backfill_scope: all`.
- A diff that only removes or updates metadata is applied with `skip_backfill`,
  so the environment still updates and unrelated gaps are left alone.
  `backfill_models: []` is never sent: SQLMesh reads an empty selection as
  "backfill everything".

### Added
- `generation.model_checks.require_explicit_start` (default `false`). When on, a
  materialized model must contain its own `start` line in the `MODEL` block.
  A `start` inherited from `model_defaults` does not count. `VIEW`, `SEED` and
  external models are skipped.
- `generation.model_checks.full_min_interval` (default off). When set, a `FULL`
  model whose cron is finer than that unit fails at load. `day` rejects a
  10-minute `FULL`.
- `when_matched` is rejected at load when the gateway cannot run `MERGE`
  (Redshift unless `enable_merge` is set; MySQL, DuckDB, ClickHouse, StarRocks).
  Snowflake and the other native-`MERGE` warehouses pass. Postgres is left
  alone: support depends on the server version, and DAG parse does not connect
  to find it.
- `create_plan_apply_task(..., task_display_name=)` is forwarded to
  `PythonOperator` on Airflow 2.9+ and 3.x, and omitted on older 2.x.

## [0.10.1] - 2026-09-23

### Fixed
- Model tasks pass `skip_janitor=True` to `Context.run()`. On `prod`, SQLMesh
  runs `compact_intervals()` at the start of every `run()`, and parallel Airflow
  tasks deadlock on `DELETE` from the state table `_intervals`
  (`deadlock detected` / `ShareLock on transaction`).
- `create_tasks_in_dag` adds one `sqlmesh_janitor` task after the leaf models
  (`trigger_rule=all_done`). It is not a root, so a streaming-MV refresh gate
  that keys off tasks with no upstream still sees the model roots.
- Generated Python, Bash (`--skip-janitor`) and Kubernetes runs follow the same
  rule. Python and Bash DAGs get one janitor after the leaves.

## [0.10.0] - 2026-09-19

### Added
- **dbt-style model selection** (`sqlmesh_dag_generator.selectors`). `select` /
  `exclude` accept expressions evaluated against the model graph: `tag:finance+`,
  `+path:models/marts`, `kind:INCREMENTAL*`, `owner:`, `project:`, `interval:`,
  `cron:`, wildcards, `@`, depth-limited `2+model`, unions (whitespace) and
  intersections (comma). See `docs/SELECTION.md`.
- **Named selectors** in the config file (`selectors:`), the dbt `selectors.yml` idea,
  referenced as `selector:<name>`.
- **DAG groups**: one SQLMesh project, several Airflow DAGs
  (`dag_groups:` + `build_dag_groups()`). Cross-group lineage is wired with Airflow
  Datasets/Assets or `ExternalTaskSensor`s. See `docs/DAG_GROUPS.md`.
- **Per-selection task settings** (`generation.task_overrides`): pool, queue, retries,
  timeout, priority weight, SLA and trigger rule for everything a selection matches.
- **Airflow Datasets/Assets per model** (`generation.emit_datasets`), so other DAGs can
  be scheduled on model completion instead of a clock.
- **Model metadata on the tasks** (`generation.model_docs`, on by default): owner,
  description, kind, cron (with timezone), tags and audits as `doc_md`.
- **Maintenance tasks**: `create_unit_test_task`, `create_lint_task`,
  `create_audit_task`, `create_janitor_task`, `create_restate_task`
  (`docs/MAINTENANCE_TASKS.md`), plus `generation.audit_tasks` for per-model audit
  tasks that gate downstream models, the way `dbt build` does.
- **Orchestration manifest** (`build_manifest`, `write_manifest`, `diff_manifests`,
  `--manifest`): every model with its task id, schedule, lineage and dataset URI, so
  CI can diff what a change does to Airflow.
- **CLI**: `--select`, `--exclude`, `--list-models`, `--list-groups`, `--manifest`.
- Runtime `on_failure_callback` / `on_success_callback` are now applied to tasks
  created by `create_tasks_in_dag` (previously only in generated DAG files).

### Changed
- **`cron_tz` is respected** when deciding whether a model is due
  (SQLMesh 0.235.4+). A daily model with `cron_tz 'Europe/Warsaw'` is due at local
  midnight, not UTC midnight - previously it could be skipped on the wrong tick.
- `SQLMeshModelInfo` gained `display_name`, `path`, `cron_tz`, `project` and `audits`.
- SQLMesh keyword arguments are filtered against the installed version's signature
  (`ops_tasks.supported_kwargs`) instead of ad-hoc `inspect` checks.
- Packaging moved to PEP 621 (`pyproject.toml`, `setup.py` removed), with an accurate
  `requires-python = ">=3.9"` (SQLMesh has not supported 3.8 since 0.228).
- CLI `--environment` now defaults to `""` (no virtual environment), matching the
  library default and the documented gateway-based workflow.
- Documentation rewritten; `scripts/` holds the release and config-validation helpers.

### Added (opt-in)
- `generation.no_auto_upstream` passes `no_auto_upstream=True` to `Context.run`
  (SQLMesh 0.230+). Airflow already schedules every upstream model as its own task,
  so letting SQLMesh chase upstream again duplicates work and can put two tasks on
  the same table. It stays **off** in this release - changing run semantics in the
  same version that reworks selection and task wiring would make any regression hard
  to attribute. **Planned to default to `true` in 0.11.0**; turn it on now with
  `generation.no_auto_upstream: true` and keep the old behaviour later by setting it
  to `false` explicitly.

### Fixed
- **Generated dynamic DAGs no longer require Python 3.12.** The template emitted a
  task-id expression as an f-string with nested double quotes (PEP 701), so a DAG
  generated on a 3.12 machine failed to import on an Airflow worker running 3.9-3.11
  with `SyntaxError: f-string: unterminated string`. Task ids now come from the shared
  `sqlmesh_dag_generator.models.model_task_id`, which is also what runtime mode uses,
  so the two can no longer drift.
- `utils.localize_to_cron_tz` handles naive timestamps (the previous code path had no
  `timezone` import in scope).
- Removed two dead helpers in `utils.py` that shadowed the real implementations in
  `validation.py` with different signatures.
- A stale test asserted that an hourly model runs on a 12:30 tick; with
  `skip_if_not_due` (0.9.15) it is correctly skipped there.

## [0.9.15] - 2026-08-10

### Added
- **`generation.skip_if_not_due` (default `True`)** for mixed-cadence DAGs:
  when the DAG schedule is the minimum model interval (e.g. `*/5`) but the project
  also has hourly/daily models, coarser model tasks **return early** with
  `{"status": "skipped", "reason": "not_due"}` **before** loading SQLMesh
  `Context` (Context alone often costs 30–50s per task on a no-op tick).
- Helpers in `sqlmesh_dag_generator.utils` (also re-exported from package root):
  `should_skip_model_for_tick`, `interval_end_matches_cron`, `not_due_skip_result`.
- Wired in `create_tasks_in_dag` (runtime), static Python tasks, and dynamic DAG
  generation. Depends on `croniter` (already common via Airflow).

### Why
Auto-schedule correctly picks the shortest interval, but every tick still scheduled
*all* model tasks. Coarser models then either froze state (old bug, fixed by
omitting start/end) or paid full Context cost for NOTHING_TO_DO. Early skip keeps
the 5-minute wall-clock budget for models that are actually due.

### Config
```yaml
generation:
  skip_if_not_due: true   # default; set false only for break-glass debugging
```

## [0.9.14] - 2026-07-24

### Added
- **Per-model downstream DAG triggers** for clean separation of concerns:
  - Config: `generation.model_triggers` map (`model FQN` dag id / dict / `ModelTriggerConfig`)
  - SQLMesh-native tags on the model:
    - `trigger_dag:<dag_id>`
    - `trigger_conf:<key>=<value>` (optional, repeatable)
  - Wired in `create_tasks_in_dag` (runtime / COWM style) and static `dag_builder`
  - Explicit config wins over tags; pipeline-level `trigger_dag_id` still works after leaves
- Module `sqlmesh_dag_generator.triggers` with `ModelTriggerConfig`, `resolve_model_trigger`, etc.

## [0.9.13] - 2026-07-23

### Added
- `SQLMeshDAGGenerator.create_plan_apply_task(...)` for a standalone deploy-path
  plan+apply Airflow task (no model run graph). Supports `dag_run.conf` overrides:
  `plan_only`, `skip_backfill`.

### Changed
- Internal replan wiring in `create_tasks_in_dag` now reuses `create_plan_apply_task`.
- Documented split: interval/run DAGs should set `auto_replan_on_change=False`;
  plan/apply belongs on a separate deploy DAG for large / alert-critical warehouses.

## [0.9.12] - 2026-07-20

### Fixed
- `config_to_dict()` now uses `exclude_defaults=True, by_alias=True` so runtime
  config merge re-validates cleanly on SQLMesh 0.236+. Plain `model_dump()`
  emitted `type_` (not `type`) for `default_scheduler`, which caused
  `ConfigError: Missing scheduler type` during `sqlmesh_plan_apply` / context load.

## [0.9.11] - 2026-07-20

### Added
- `sqlmesh_compat` helpers for modern SQLMesh (0.228–0.236+):
  - `load_sqlmesh_config()` — replaces removed `Config.load`
  - `config_to_dict()` — Pydantic v1/v2 dump
  - `normalize_depends_on()` — string or object dependency names

### Fixed
- Runtime connection merge no longer silently skips base `config.yaml` on
  SQLMesh versions without `Config.load` (was always falling into except)

### Changed
- Declared dependency floor `sqlmesh>=0.228.0` (tested through 0.236.0)
- Airflow floor `>=2.4.0` (required for `schedule=` dual-compat)

## [0.9.10] - 2026-07-20

### Added
- **Airflow 2 + 3 dual compatibility** via `sqlmesh_dag_generator.airflow_compat`:
  - Operators: prefer `airflow.providers.standard.*`, fall back to classic AF2 paths
  - `BaseHook` / `Variable`: prefer Airflow 3 Task SDK, fall back to AF2
  - `dag_schedule_kwargs()` helper; generated DAGs emit `schedule=` (AF3-safe, AF2.4+)
- Re-exports of compat symbols from package root for consumers

### Changed
- `generator.py` and `airflow_utils.py` import operators/hooks through `airflow_compat`
- Static and dynamic `dag_builder` output uses `schedule=` and compat imports
  (config YAML key `schedule_interval` unchanged for backward compatibility)

## [0.9.9] - 2026-07-06

### Fixed
- Fixed silent state-freeze of incremental models whose interval is coarser than the DAG tick. On a project mixing sub-hourly and hourly (or daily) incremental models, `auto_schedule` sets the DAG cadence to the global minimum interval (e.g. 5 minutes). `execute_model` then passed that narrow tick window (`data_interval_start`/`data_interval_end`) as `start`/`end` to *every* model. For a coarser model the window spans no full model interval, so SQLMesh returns `NOTHING_TO_DO` and the model never advances — while the Airflow task still reports success. `execute_model` now detects when a model's own interval is coarser than the scheduler tick and omits `start`/`end`, letting SQLMesh select the due interval(s) from the model's cron. Sub-hourly/matching models keep the explicit window unchanged.
- Added a module-level `import inspect` so `run_manual_backfill` no longer raises `NameError: name 'inspect' is not defined` on Airflow builds where the local import path is not exercised.

## [0.9.8] - 2026-04-16

### Changed
- Kept the package default `replan_timeout_hours=6` while allowing DAG consumers to override the timeout explicitly, including disabling it by passing `None`.
- Bumped package version metadata to `0.9.8`.

### Added
- Added `SQLMeshDAGGenerator.create_manual_backfill_task(...)` so manual historical replay can be defined as a package-managed Airflow task instead of custom DAG-local logic.

### Changed
- Made `recovery_mode="bounded_auto"` the package default for sub-hourly incremental DAGs, so bounded outage replay is opt-out instead of opt-in.
- Bumped package version metadata to `0.9.6`.

### Fixed
- Repaired the corrupted recovery test section in `tests/test_generator.py` and added coverage for package-managed manual backfill execution.

## [0.9.5] - 2026-04-08

### Fixed
- Restored the package source in GitHub from the newer published artifact instead of the stale `0.4.0` repo snapshot.
- Added explicit recovery configuration for missed Airflow intervals: `disabled`, `warn`, and `bounded_auto`.
- Added `sqlmesh_integrity_guard` and `sqlmesh_recovery_backfill` helper tasks for sub-hourly incremental projects.
- Corrected bounded recovery replay windows so replay starts at the previous successful interval boundary and does not skip the first missed bucket.

### Added
- Added `security.py` for credential scrubbing and connection safety checks.
- Added `validation.py` for project structure, dependency, and resource validation.

### Changed
- Bumped package version metadata to `0.9.5`.
- Extended configuration serialization to include advanced generation settings and nested recovery config.
- Generated dynamic DAGs now emit recovery controls and integrity warnings for `catchup=False` sub-hourly deployments.

## [0.4.0] - 2025-12-09

### Enhanced
- **Enhanced Auto-Scheduling Interval Support**
  - Expanded interval mapping from 10 to 13 supported intervals
  - Added defensive alias support: `THIRTY_MINUTE`, `FIFTEEN_MINUTE`
  - Added `TEN_MINUTE` interval support (`*/10 * * * *`)
  - Comprehensive documentation of SQLMesh interval capabilities
  - Safe fallback to `@daily` for unknown future intervals
  - See [Interval Mapping Analysis](docs/INTERVAL_MAPPING_ANALYSIS.md) for details

### Documentation
- **NEW**: `docs/INTERVAL_MAPPING_ANALYSIS.md` - Complete interval support analysis
- **NEW**: `docs/AUTO_SCHEDULING_IMPLEMENTATION.md` - Implementation details
- **NEW**: `docs/QUICK_REFERENCE.md` - One-page cheat sheet
- **UPDATED**: `docs/AUTO_SCHEDULING.md` - Updated supported intervals table
- **UPDATED**: All documentation references to reflect v0.4.0

### Testing
- All 83 tests passing
- Enhanced interval conversion tests
- Verified dynamic DAG generation with expanded intervals

## [0.3.0] - 2025-12-09

### Added
- **Auto-Scheduling**
  - NEW: `auto_schedule` parameter (enabled by default)
  - NEW: `get_recommended_schedule()` - Analyzes SQLMesh models and returns optimal Airflow schedule
  - NEW: `get_model_intervals_summary()` - See which models run at which intervals
  - Automatic detection of minimum interval across all SQLMesh models
  - Support for all SQLMesh interval units (MINUTE, FIVE_MINUTE, HOUR, DAY, etc.)
  - Intelligent conversion from SQLMesh intervals to Airflow cron expressions
  - Works in both static and dynamic DAG generation modes
  - See [Auto-Scheduling Guide](docs/AUTO_SCHEDULING.md) for details

- **Plugin-Based Credential Resolver Architecture**
  - NEW: `resolve_credentials()` - Universal credential resolution function
  - NEW: `CredentialResolver` - Base class for custom credential resolvers
  - NEW: `register_credential_resolver()` - Register custom resolvers
  - Built-in resolvers:
    - `AirflowConnectionResolver` - Direct Connection object or ID support
    - `AWSSecretsManagerResolver` - AWS Secrets Manager integration
    - `EnvironmentVariableResolver` - Environment variable support
    - `CallableResolver` - Custom function support
  - Auto-detection of credential source type
  - Extensible plugin architecture for any credential source
  
### Changed
- **BREAKING**: Simplified API (clean slate - no users yet)
  - `SQLMeshDAGGenerator` now accepts `connection` parameter directly
  - Pass Airflow Connection objects, IDs, or dicts directly - no conversion needed!
  - Support for separate `state_connection` parameter
  - Runtime config merging with existing config.yaml files
  - Removed deprecated conversion functions for cleaner codebase
  
### Documentation
- **NEW**: `docs/ARCHITECTURE_DECISION.md` - Design rationale for plugin architecture
- **NEW**: `examples/7_recommended_approach.py` - Clean API examples (6 patterns)
- **UPDATED**: README with new credential resolver approach
- **UPDATED**: Test configuration with warning filters for clean output

### Removed
- Deprecated functions removed (clean slate):
  - `airflow_connection_to_sqlmesh_config()` - Use `resolve_credentials()` instead
  - `get_connection_from_variable()` - Use `resolve_credentials()` instead
  - `build_runtime_config()` - Pass `connection` directly to generator instead

## [0.2.1] - 2025-12-08

### Added
- **Multi-Environment Configuration Guide** (`docs/MULTI_ENVIRONMENT.md`)
  - Complete guide for dev/staging/prod setup
  - Gateway vs environment parameter clarification
  - Environment variable management
  - State connection strategies
  - Airflow Variables integration
- **Comprehensive Troubleshooting Guide** (`docs/TROUBLESHOOTING.md`)
  - Common issues and solutions
  - Debugging tips and techniques
  - Pre-deployment checklist
  - Quick diagnostics procedures
- **Configuration Validator** (`validate_config.py`)
  - Automated validation of SQLMesh + Airflow configuration
  - Gateway existence checks
  - Model discovery verification
  - Environment variable detection
  - Worker access verification guidance
- **Multi-Environment Example** (`examples/4_multi_environment.py`)
  - Production-ready DAG example
  - Proper Airflow Variables usage
  - Gateway-based environment switching
  - Comprehensive inline documentation
- **Example SQLMesh Config** (`examples/config_multi_env.yaml`)
  - Multi-environment gateway setup
  - docker_local, dev, staging, prod gateways
  - Environment variable templating
  - State connection best practices
- **Configuration Fixes Summary** (`docs/CONFIGURATION_FIXES.md`)
  - Documents all resolved compatibility issues
  - Migration guide for existing users

### Fixed
- **Critical: Gateway vs Environment Confusion**
  - Added deprecation warning for `environment` parameter in SQLMeshConfig
  - Updated all documentation to emphasize `gateway` usage
  - All examples now use `gateway` instead of `environment`
- **Missing docker_local Gateway Documentation**
  - Added docker_local gateway to example configs
  - Documented gateway naming conventions
  - Updated defaults to use docker_local
- **Undocumented Shared Volume Requirement**
  - Enhanced Deployment Warnings with detailed shared volume section
  - Documented three solutions: shared volume, Docker image, git-sync
  - Added worker access verification steps
- **Hardcoded Credentials in Examples**
  - All examples now use environment variable templating
  - Added security best practices guide
  - Validator warns about hardcoded credentials
- **State Connection Conflicts**
  - Documented shared vs isolated state strategies
  - Provided examples for both approaches
  - Added validation for state configuration

### Changed
- **Enhanced README**
  - Prominent warning about gateway vs environment
  - Link to Multi-Environment Configuration Guide
  - Updated feature list for multi-environment support
- **Updated docs/README.md**
  - Added Configuration section with new guides
  - Added important notes about gateway and distributed Airflow
  - Better navigation for production deployments
- **Updated simple_generate.py Example**
  - Now uses Airflow Variables
  - Demonstrates gateway usage
  - More production-ready pattern
- **Enhanced SQLMeshConfig**
  - Added detailed docstring with examples
  - Added `__post_init__` validation
  - Deprecation warning for environment parameter

### Documentation
- **NEW**: Multi-Environment Configuration (comprehensive guide)
- **NEW**: Troubleshooting Guide (common issues)
- **NEW**: Configuration Validator (automated checks)
- **ENHANCED**: Deployment Warnings (shared volume, credentials, etc.)
- **ENHANCED**: README (gateway warning, better navigation)
- **ENHANCED**: Examples (production-ready patterns)


3. **Environment Variable Injection**
   - Secure credential handling
   - Per-DAG configuration

4. **Production Deployment Guide**
   - Everything you need to know for distributed Airflow
   - Kubernetes best practices
   - Troubleshooting guide

### Migration from v0.1.0

**No breaking changes!** All existing configs work as-is.

**To use new features:**

```yaml
# Configurable start date
airflow:
  start_date: "2025-01-01"  # or days_ago(1)
  
  # Environment variables
  env_vars:
    DB_PASSWORD: "{{ var.value.db_password }}"

# Kubernetes operator (now works!)
generation:
  operator_type: kubernetes
  docker_image: "my-sqlmesh:v1.0"
  namespace: "data-pipelines"
```

---

[Unreleased]: https://github.com/kubolko/sqlmesh-dag-generator/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/kubolko/sqlmesh-dag-generator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/kubolko/sqlmesh-dag-generator/releases/tag/v0.1.0

