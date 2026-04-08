"""
Validation utilities for sqlmesh-dag-generator

Provides dependency validation, resource checks, and model validation.
"""
import logging
from typing import Dict, List, Set, Tuple
from pathlib import Path

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
            cycle = " → ".join(path[cycle_start:] + [model])
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
            "❌ Circular dependencies detected in SQLMesh models:\n\n" +
            "\n".join(f"  • {err}" for err in unique_errors) +
            "\n\nThese must be fixed in your SQLMesh project before generating a DAG.\n"
            "Circular dependencies will cause Airflow to raise AirflowDagCycleException."
        )
        raise ValueError(error_msg)

    logger.info("✓ No circular dependencies detected")
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
            "⚠️  Missing dependencies detected:\n" +
            "\n".join(f"  • {w}" for w in warnings) +
            "\n\nThese models may be:\n"
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
    resources['memory_total_gb'] = memory.total / (1024 ** 3)
    resources['memory_available_gb'] = memory.available / (1024 ** 3)
    resources['memory_percent'] = memory.percent

    if memory.available < 2 * 1024 ** 3:  # Less than 2GB
        logger.warning(
            f"⚠️  Low memory detected: {resources['memory_available_gb']:.1f}GB available\n"
            f"   Large SQLMesh projects may fail to load or cause OOM errors.\n"
            f"   \n"
            f"   Consider:\n"
            f"   • Increasing worker/scheduler memory\n"
            f"   • Using model filtering: include_models=['critical_*']\n"
            f"   • Splitting into multiple smaller DAGs\n"
        )

    # Check disk space
    disk = psutil.disk_usage('/')
    resources['disk_free_gb'] = disk.free / (1024 ** 3)
    resources['disk_percent'] = disk.percent

    if disk.free < 5 * 1024 ** 3:  # Less than 5GB
        logger.warning(
            f"⚠️  Low disk space: {resources['disk_free_gb']:.1f}GB free\n"
            f"   May affect SQLMesh cache and Airflow logs.\n"
        )

    # Check CPU
    cpu_count = psutil.cpu_count()
    resources['cpu_count'] = cpu_count

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
        raise NotADirectoryError(
            f"SQLMesh project path is not a directory: {project_path}"
        )

    # Check for config file
    config_files = ['config.yaml', 'config.yml', 'config.py']
    has_config = any((path / cf).exists() for cf in config_files)

    if not has_config:
        logger.warning(
            f"⚠️  No config file found in {project_path}\n"
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
            f"  └── models/  ← Missing!\n"
            f"      ├── model1.sql\n"
            f"      └── model2.sql\n"
        )

    # Count models
    model_files = list(models_dir.glob("**/*.sql")) + list(models_dir.glob("**/*.py"))
    model_count = len(model_files)

    if model_count == 0:
        logger.warning(
            f"⚠️  No model files found in {models_dir}\n"
            f"   Directory exists but is empty.\n"
        )
    else:
        logger.debug(f"Found {model_count} model files in {models_dir}")

    logger.info(f"✓ SQLMesh project structure validated: {project_path}")


def estimate_dag_complexity(models: Dict[str, SQLMeshModelInfo]) -> Dict[str, any]:
    """
    Estimate complexity of the generated DAG.

    Args:
        models: Dictionary of models

    Returns:
        Dictionary with complexity metrics
    """
    complexity = {
        'total_models': len(models),
        'max_depth': 0,
        'total_dependencies': 0,
        'orphan_models': 0,  # No dependencies
        'leaf_models': 0,    # No dependents
    }

    # Calculate metrics
    all_deps = set()
    for model_info in models.values():
        deps = len(model_info.dependencies)
        complexity['total_dependencies'] += deps

        if deps == 0:
            complexity['orphan_models'] += 1

        all_deps.update(model_info.dependencies)

    # Find leaf models (not dependencies of others)
    for model_name in models.keys():
        if model_name not in all_deps:
            complexity['leaf_models'] += 1

    # Estimate max depth (simplified)
    complexity['max_depth'] = _calculate_max_depth(models)

    # Warn if complex
    if complexity['total_models'] > 500:
        logger.warning(
            f"⚠️  Large DAG detected: {complexity['total_models']} models\n"
            f"   Consider splitting into multiple DAGs for better performance.\n"
            f"   See docs/COMMON_SCENARIOS.md for guidance.\n"
        )

    if complexity['max_depth'] > 10:
        logger.warning(
            f"⚠️  Deep dependency chain: {complexity['max_depth']} levels\n"
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

        max_dep_depth = max(
            (get_depth(dep, visited.copy()) for dep in deps),
            default=0
        )
        return max_dep_depth + 1

    return max((get_depth(name, set()) for name in models), default=0)

