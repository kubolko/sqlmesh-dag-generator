# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- **Enhanced Auto-Scheduling Interval Support** 📅
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
- **Auto-Scheduling** 📅
  - NEW: `auto_schedule` parameter (enabled by default)
  - NEW: `get_recommended_schedule()` - Analyzes SQLMesh models and returns optimal Airflow schedule
  - NEW: `get_model_intervals_summary()` - See which models run at which intervals
  - Automatic detection of minimum interval across all SQLMesh models
  - Support for all SQLMesh interval units (MINUTE, FIVE_MINUTE, HOUR, DAY, etc.)
  - Intelligent conversion from SQLMesh intervals to Airflow cron expressions
  - Works in both static and dynamic DAG generation modes
  - See [Auto-Scheduling Guide](docs/AUTO_SCHEDULING.md) for details

- **Plugin-Based Credential Resolver Architecture** 🔐
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


3. **Environment Variable Injection** 🔐
   - Secure credential handling
   - Per-DAG configuration

4. **Production Deployment Guide** 📚
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

