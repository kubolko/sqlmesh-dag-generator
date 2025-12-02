# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-12-02

### Added
- **Kubernetes Operator Support**: Full implementation of KubernetesPodOperator
  - New `docker_image` config field (required for kubernetes)
  - New `namespace` config field (defaults to "default")
  - Proper error handling with helpful messages
  - Example Dockerfile and K8s configuration in docs
- **Configurable Start Date**: 
  - New `start_date` field in AirflowConfig
  - Supports ISO format ("2024-01-01") or days_ago syntax
  - Defaults to yesterday instead of hardcoded 2024-01-01
- **Environment Variables Support**:
  - New `env_vars` field in AirflowConfig
  - Supports Airflow Variable templating
  - Per-DAG environment variable injection
- **Comprehensive Deployment Guide**: New `docs/DEPLOYMENT_WARNINGS.md`
  - Shared volume requirements for distributed Airflow
  - Kubernetes-specific setup guide
  - Database credential injection patterns
  - Pre-flight checklist and troubleshooting

### Fixed
- **Critical: Kubernetes Operator Fallthrough Bug**
  - Previously, selecting `operator_type: kubernetes` silently fell back to PythonOperator
  - Now properly validates and generates KubernetesPodOperator
  - Raises clear error if `docker_image` not provided
- **Hardcoded Start Date**: 
  - Removed hardcoded `datetime(2024, 1, 1)` from both static and dynamic DAGs
  - Now configurable via config or defaults to yesterday
- **Operator Type Validation**:
  - Now raises `ValueError` for unsupported operator types
  - Clear error messages guide users to fix configuration

### Changed
- **Improved Kubernetes Imports**: Added proper V1EnvVar and k8s models imports
- **Better Error Messages**: More specific validation errors with actionable guidance

### Documented
- **Operator Type Limitations**: Dynamic mode currently supports Python only
  - Documented workaround: use static mode for bash/kubernetes
  - Roadmap item for v0.3.0: full operator support in dynamic mode
- **Distributed Airflow Requirements**: Clear warning about shared volume needs
- **Database Credential Patterns**: Best practices for credential injection

## [0.1.0] - 2025-01-XX

### Added
- Initial release
- Dynamic DAG generation (fire-and-forget deployment)
- Static DAG generation (full control)
- SQLMesh model discovery and dependency resolution
- Proper incremental model handling (data_interval_start/end)
- Multi-environment support via Airflow Variables
- Comprehensive test suite (36 tests)
- CLI tool (`sqlmesh-dag-gen`)
- Examples and documentation
- Python 3.9-3.12 support

### Features
- Automatic task creation from SQLMesh models
- Dependency graph from SQLMesh lineage
- PythonOperator and BashOperator support
- Error handling with SQLMesh-specific exceptions
- Configuration via Python API or YAML files
- `create_tasks_in_dag()` method for inline DAG creation

---

## Release Notes

### v0.2.0 Highlights

This release fixes critical bugs and adds production-ready features:

1. **Kubernetes Support Actually Works Now** 🎉
   - Previously broken, now fully implemented
   - Clear error messages if misconfigured

2. **No More Hardcoded Dates** ✅
   - Configurable start_date
   - Defaults to yesterday (best practice)

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

