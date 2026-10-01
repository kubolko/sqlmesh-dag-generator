"""
Validation utilities for sqlmesh-dag-generator

Provides dependency validation, resource checks, and model validation.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlmesh_dag_generator.config import ModelChecksConfig
from sqlmesh_dag_generator.models import SQLMeshModelInfo

logger = logging.getLogger(__name__)


def validate_no_circular_dependencies(models: Dict[str, SQLMeshModelInfo]) -> List[str]:
    """
    Validate that no circular dependencies exist in the model graph.

    Args:
        models: Dictionary of model name to SQLMeshModelInfo

    Returns:
        List of error messages (empty if no circles found)

    Raises:
        ValueError: If circular dependencies are detected
    """
    errors = []

    def find_cycle(model: str, visited: Set[str], path: List[str]) -> None:
        """DFS to find cycles"""
        if model in path:
            cycle_start = path.index(model)
            cycle = " ".join(path[cycle_start:] + [model])
            errors.append(f"Circular dependency: {cycle}")
            return

        if model in visited:
            return

        visited.add(model)
        path.append(model)

        if model in models:
            for dep in models[model].dependencies:
                find_cycle(dep, visited, path.copy())

        path.pop()

    visited_global = set()
    for model_name in models:
        if model_name not in visited_global:
            find_cycle(model_name, visited_global, [])

    if errors:
        # Deduplicate errors (same cycle may be found multiple times)
        unique_errors = list(set(errors))
        error_msg = (
            "Circular dependencies detected in SQLMesh models:\n\n"
            + "\n".join(f"  • {err}" for err in unique_errors)
            + "\n\nThese must be fixed in your SQLMesh project before generating a DAG.\n"
            "Circular dependencies will cause Airflow to raise AirflowDagCycleException."
        )
        raise ValueError(error_msg)

    logger.info("No circular dependencies detected")
    return errors


def validate_missing_dependencies(models: Dict[str, SQLMeshModelInfo]) -> List[str]:
    """
    Check for dependencies that don't exist in the model set.

    Args:
        models: Dictionary of model name to SQLMeshModelInfo

    Returns:
        List of warning messages
    """
    warnings = []
    all_model_names = set(models.keys())

    for model_name, model_info in models.items():
        missing_deps = model_info.dependencies - all_model_names

        if missing_deps:
            warnings.append(
                f"Model '{model_name}' depends on models not found in project: "
                f"{', '.join(sorted(missing_deps))}"
            )

    if warnings:
        logger.warning(
            "Missing dependencies detected:\n"
            + "\n".join(f"  • {w}" for w in warnings)
            + "\n\nThese models may be:\n"
            "  - External tables/views\n"
            "  - Filtered out by include_models/exclude_models\n"
            "  - In a different SQLMesh project\n"
        )

    return warnings


def check_resource_availability() -> Dict[str, any]:
    """
    Check system resources and warn if insufficient.

    Returns:
        Dictionary with resource information
    """
    try:
        import psutil
    except ImportError:
        logger.debug("psutil not installed, skipping resource checks")
        return {}

    resources = {}

    # Check available memory
    memory = psutil.virtual_memory()
    resources["memory_total_gb"] = memory.total / (1024**3)
    resources["memory_available_gb"] = memory.available / (1024**3)
    resources["memory_percent"] = memory.percent

    if memory.available < 2 * 1024**3:  # Less than 2GB
        logger.warning(
            f"Low memory detected: {resources['memory_available_gb']:.1f}GB available\n"
            f"   Large SQLMesh projects may fail to load or cause OOM errors.\n"
            f"   \n"
            f"   Consider:\n"
            f"   • Increasing worker/scheduler memory\n"
            f"   • Using model filtering: include_models=['critical_*']\n"
            f"   • Splitting into multiple smaller DAGs\n"
        )

    # Check disk space
    disk = psutil.disk_usage("/")
    resources["disk_free_gb"] = disk.free / (1024**3)
    resources["disk_percent"] = disk.percent

    if disk.free < 5 * 1024**3:  # Less than 5GB
        logger.warning(
            f"Low disk space: {resources['disk_free_gb']:.1f}GB free\n"
            f"   May affect SQLMesh cache and Airflow logs.\n"
        )

    # Check CPU
    cpu_count = psutil.cpu_count()
    resources["cpu_count"] = cpu_count

    logger.debug(
        f"Resource check: "
        f"{resources['memory_available_gb']:.1f}GB RAM, "
        f"{resources['disk_free_gb']:.1f}GB disk, "
        f"{cpu_count} CPUs"
    )

    return resources


def validate_project_structure(project_path: str) -> None:
    """
    Validate SQLMesh project has required structure.

    Args:
        project_path: Path to SQLMesh project

    Raises:
        FileNotFoundError: If required files/directories are missing
    """
    path = Path(project_path)

    if not path.exists():
        raise FileNotFoundError(
            f"SQLMesh project path does not exist: {project_path}\n"
            f"\n"
            f"Ensure:\n"
            f"  • Path is correct\n"
            f"  • Path is accessible from Airflow workers\n"
            f"  • If using NFS/EFS, mount is active\n"
        )

    if not path.is_dir():
        raise NotADirectoryError(f"SQLMesh project path is not a directory: {project_path}")

    # Check for config file
    config_files = ["config.yaml", "config.yml", "config.py"]
    has_config = any((path / cf).exists() for cf in config_files)

    if not has_config:
        logger.warning(
            f"No config file found in {project_path}\n"
            f"   Looking for: {', '.join(config_files)}\n"
            f"   SQLMesh may use default configuration.\n"
        )

    # Check for models directory
    models_dir = path / "models"
    if not models_dir.exists():
        raise FileNotFoundError(
            f"SQLMesh models directory not found: {models_dir}\n"
            f"\n"
            f"Expected structure:\n"
            f"  {project_path}/\n"
            f"  ├── config.yaml\n"
            f"  └── models/  Missing!\n"
            f"      ├── model1.sql\n"
            f"      └── model2.sql\n"
        )

    # Count models
    model_files = list(models_dir.glob("**/*.sql")) + list(models_dir.glob("**/*.py"))
    model_count = len(model_files)

    if model_count == 0:
        logger.warning(f"No model files found in {models_dir}\n   Directory exists but is empty.\n")
    else:
        logger.debug(f"Found {model_count} model files in {models_dir}")

    logger.info(f"SQLMesh project structure validated: {project_path}")


# Warehouses whose adapter rejects when_matched (LogicalMergeMixin, or Redshift
# unless the connection sets enable_merge). Postgres is version-dependent and
# is intentionally absent: blocking DAG parse would need a live server version.
_NO_MERGE_DIALECTS = frozenset({"mysql", "duckdb", "clickhouse", "starrocks"})
_MERGE_DIALECTS = frozenset(
    {
        "snowflake",
        "bigquery",
        "databricks",
        "spark",
        "hive",
        "mssql",
        "fabric",
        "trino",
        "athena",
    }
)
_POLICY_SKIP_KINDS = frozenset({"VIEW", "SEED", "EXTERNAL", "EMBEDDED"})
_START_PROPERTY = re.compile(r"(?im)^\s*start\b")
_PYTHON_START = re.compile(r"(?m)^\s*start\s*=")


_EXTERNAL_MODEL_FILE_NAMES = ("external_models.yaml", "external_models.yml")


def check_external_models_layout(project_path: str) -> List[str]:
    """
    Find external model declarations SQLMesh will never read.

    SQLMesh loads external models only from ``<project>/external_models.yaml`` and
    ``<project>/external_models/*.yaml``. A file anywhere else - ``models/`` is the
    usual spot - is ignored without an error, so the declarations, their columns
    and their types silently do nothing. Returns one message per problem.
    """
    import yaml

    root = Path(project_path)
    loaded_dir = root / "external_models"
    problems: List[str] = []

    for path in sorted(root.rglob("external_models.y*ml")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue  # .cache, .venv and friends
        if path.name not in _EXTERNAL_MODEL_FILE_NAMES:
            continue
        if path.parent == root or path.parent == loaded_dir:
            continue

        relative = path.relative_to(root)
        message = (
            f"SQLMesh ignores {relative}: external models are read only from "
            "external_models.yaml in the project root or external_models/*.yaml"
        )
        try:
            entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except Exception:  # noqa: BLE001 - a broken file is still worth reporting
            entries = []
        if isinstance(entries, list):
            listed = [
                str(entry.get("name"))
                for entry in entries
                if isinstance(entry, dict) and isinstance(entry.get("columns"), list)
            ]
            message += f" ({len(entries)} declaration(s) unused)"
            if listed:
                message += (
                    f". {len(listed)} of them list columns as name/type entries; "
                    "SQLMesh expects a mapping (column: type) and fails to load that "
                    "format once the file is moved"
                )
        problems.append(message)
    return problems


def connection_dialect(connection: Any) -> Optional[str]:
    """Warehouse type from a SQLMesh gateway connection, without opening it."""
    if connection is None:
        return None
    if isinstance(connection, dict):
        raw = connection.get("type") or connection.get("dialect")
    else:
        raw = (
            getattr(connection, "type_", None)
            or getattr(connection, "type", None)
            or getattr(connection, "DIALECT", None)
        )
    if raw is None:
        return None
    return str(getattr(raw, "value", raw)).strip().lower() or None


def engine_runs_merge(connection: Any) -> Optional[bool]:
    """
    Whether ``when_matched`` can run on this connection.

    ``None`` means the dialect is unknown or version-dependent. Callers leave
    those models alone so DAG parse does not fail on a guess.
    """
    dialect = connection_dialect(connection)
    if dialect in {None, "postgres", "postgresql", "risingwave"}:
        return None
    if dialect == "redshift":
        if isinstance(connection, dict):
            return bool(connection.get("enable_merge"))
        return bool(getattr(connection, "enable_merge", False))
    if dialect in _NO_MERGE_DIALECTS:
        return False
    if dialect in _MERGE_DIALECTS:
        return True
    return None


def validate_loaded_models(
    context: Any,
    *,
    gateway: Optional[str],
    checks: ModelChecksConfig,
) -> None:
    """
    Raise when a loaded project breaks the publish contract.

    ``when_matched`` is checked against the gateway connection. The start and
    FULL-cron checks run only when ``checks`` turns them on. VIEW, SEED and
    external models are skipped for those two.
    """
    models = getattr(context, "models", None) or getattr(context, "_models", None) or {}
    errors: List[str] = []
    try:
        items = list(models.items())
    except Exception:
        items = []
    for name, model in items:
        connection = _connection_for_model(context, gateway, model)
        errors.extend(model_contract_errors(str(name), model, connection, checks))
    if errors:
        raise ValueError("SQLMesh model checks failed:\n" + "\n".join(f"- {err}" for err in errors))


def model_contract_errors(
    name: str,
    model: Any,
    connection: Any,
    checks: ModelChecksConfig,
) -> List[str]:
    """Sentences for one model. Empty when the model can be published."""
    errors: List[str] = []
    when_matched = getattr(model, "when_matched", None)
    if when_matched and engine_runs_merge(connection) is False:
        errors.append(f"This engine does not run MERGE. Remove `when_matched` from `{name}`.")

    if _skips_policy_checks(model):
        return errors

    if checks.full_min_interval and _is_full(model):
        unit = _interval_name(model)
        if unit is not None and _finer_than(unit, checks.full_min_interval):
            errors.append(
                "FULL rebuilds the whole table on every interval. "
                f"Set cron to `{checks.full_min_interval}` or coarser on `{name}`."
            )

    if checks.require_explicit_start and not _model_declares_start(model):
        errors.append(
            f"Set `start` on `{name}`. Without it, backfill begins at the project default."
        )
    return errors


def _connection_for_model(context: Any, gateway: Optional[str], model: Any) -> Any:
    config = getattr(context, "config", None)
    gateways = getattr(config, "gateways", None) if config is not None else None
    if not hasattr(gateways, "get"):
        return None
    model_gateway = getattr(model, "gateway", None) or None
    name = model_gateway or gateway or getattr(config, "default_gateway", None)
    chosen = gateways.get(name) if name else None
    if chosen is None and gateway:
        chosen = gateways.get(gateway)
    if chosen is None:
        return None
    return getattr(chosen, "connection", None)


def _kind_name(model: Any) -> str:
    kind = getattr(model, "kind", None)
    if kind is None:
        return str(getattr(model, "kind_name", "") or "").upper()
    raw = getattr(kind, "model_kind_name", None)
    if raw is None:
        raw = getattr(kind, "name", "")
    return str(getattr(raw, "value", raw) or "").upper()


def _skips_policy_checks(model: Any) -> bool:
    kind = getattr(model, "kind", None)
    if kind is not None and any(
        getattr(kind, attr, False)
        for attr in ("is_view", "is_seed", "is_external", "is_symbolic", "is_embedded")
    ):
        return True
    return _kind_name(model) in _POLICY_SKIP_KINDS


def _is_full(model: Any) -> bool:
    kind = getattr(model, "kind", None)
    if kind is not None and getattr(kind, "is_full", False):
        return True
    return _kind_name(model) == "FULL"


def _interval_name(model: Any) -> Optional[str]:
    from sqlmesh_dag_generator.config import _INTERVAL_UNITS

    unit = getattr(model, "interval_unit", None)
    if unit is None:
        return None
    name = str(getattr(unit, "value", unit)).strip().lower()
    if name not in _INTERVAL_UNITS:
        return None
    return name


def _finer_than(unit: str, minimum: str) -> bool:
    from sqlmesh_dag_generator.config import _INTERVAL_UNITS

    return _INTERVAL_UNITS.index(unit) < _INTERVAL_UNITS.index(minimum)


def _model_declares_start(model: Any) -> bool:
    """True when the model's own file contains ``start``, not an inherited default."""
    path = getattr(model, "_path", None) or getattr(model, "path", None)
    if not path:
        return False
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return False
    block = _extract_model_block(text)
    if block is not None:
        return _START_PROPERTY.search(_strip_sql_comments(block)) is not None
    return _PYTHON_START.search(text) is not None


def _strip_sql_comments(text: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", without_block)


def _extract_model_block(text: str) -> Optional[str]:
    match = re.search(r"(?i)\bMODEL\s*\(", text)
    if match is None:
        return None
    depth = 1
    index = match.end()
    quote: Optional[str] = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == quote and text[index - 1] != "\\":
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if text.startswith("--", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[match.end() : index]
        index += 1
    return text[match.end() :]


def estimate_dag_complexity(models: Dict[str, SQLMeshModelInfo]) -> Dict[str, any]:
    """
    Estimate complexity of the generated DAG.

    Args:
        models: Dictionary of models

    Returns:
        Dictionary with complexity metrics
    """
    complexity = {
        "total_models": len(models),
        "max_depth": 0,
        "total_dependencies": 0,
        "orphan_models": 0,  # No dependencies
        "leaf_models": 0,  # No dependents
    }

    # Calculate metrics
    all_deps = set()
    for model_info in models.values():
        deps = len(model_info.dependencies)
        complexity["total_dependencies"] += deps

        if deps == 0:
            complexity["orphan_models"] += 1

        all_deps.update(model_info.dependencies)

    # Find leaf models (not dependencies of others)
    for model_name in models.keys():
        if model_name not in all_deps:
            complexity["leaf_models"] += 1

    # Estimate max depth (simplified)
    complexity["max_depth"] = _calculate_max_depth(models)

    # Warn if complex
    if complexity["total_models"] > 500:
        logger.warning(
            f"Large DAG detected: {complexity['total_models']} models\n"
            f"   Consider splitting into multiple DAGs for better performance.\n"
            f"   See docs/COMMON_SCENARIOS.md for guidance.\n"
        )

    if complexity["max_depth"] > 10:
        logger.warning(
            f"Deep dependency chain: {complexity['max_depth']} levels\n"
            f"   Long chains may cause scheduling delays.\n"
        )

    return complexity


def _calculate_max_depth(models: Dict[str, SQLMeshModelInfo]) -> int:
    """Calculate maximum dependency depth"""

    def get_depth(model_name: str, visited: Set[str]) -> int:
        if model_name in visited:
            return 0  # Avoid infinite recursion

        if model_name not in models:
            return 0

        visited.add(model_name)

        deps = models[model_name].dependencies
        if not deps:
            return 1

        max_dep_depth = max((get_depth(dep, visited.copy()) for dep in deps), default=0)
        return max_dep_depth + 1

    return max((get_depth(name, set()) for name in models), default=0)
