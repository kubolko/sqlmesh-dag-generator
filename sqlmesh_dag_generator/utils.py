"""
Utility functions for SQLMesh DAG Generator
"""
import re
from typing import Set, List, Optional
from pathlib import Path


def sanitize_task_id(name: str) -> str:
    """
    Sanitize a name to be a valid Airflow task ID.

    Args:
        name: Original name

    Returns:
        Sanitized task ID
    """
    # Replace dots, dashes, and other special chars with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Replace multiple underscores with single
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized


def parse_cron_schedule(cron: Optional[str]) -> Optional[str]:
    """
    Parse and validate cron expression.

    Args:
        cron: Cron expression

    Returns:
        Validated cron expression or None
    """
    if not cron:
        return None

    # Basic validation - cron should have 5 or 6 parts
    parts = cron.strip().split()
    if len(parts) not in [5, 6]:
        return None

    return cron


def detect_circular_dependencies(dependencies: dict) -> Optional[List[str]]:
    """
    Detect circular dependencies in a dependency graph.

    Args:
        dependencies: Dict mapping node -> set of dependencies

    Returns:
        List of nodes in cycle if found, None otherwise
    """
    def dfs(node, visited, rec_stack, path):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        if node in dependencies:
            for neighbor in dependencies[node]:
                if neighbor not in visited:
                    cycle = dfs(neighbor, visited, rec_stack, path[:])
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]

        rec_stack.remove(node)
        return None

    visited = set()

    for node in dependencies:
        if node not in visited:
            rec_stack = set()
            cycle = dfs(node, visited, rec_stack, [])
            if cycle:
                return cycle

    return None


def get_model_lineage(model_name: str, all_models: dict) -> dict:
    """
    Get complete lineage (upstream and downstream) for a model.

    Args:
        model_name: Name of the model
        all_models: Dict of all models with their dependencies

    Returns:
        Dict with 'upstream' and 'downstream' lists
    """
    upstream = set()
    downstream = set()

    # Get upstream (dependencies)
    def get_upstream(name):
        if name in all_models:
            for dep in all_models[name].dependencies:
                if dep not in upstream:
                    upstream.add(dep)
                    get_upstream(dep)

    get_upstream(model_name)

    # Get downstream (dependents)
    for name, model_info in all_models.items():
        if model_name in model_info.dependencies:
            downstream.add(name)

    return {
        'upstream': sorted(upstream),
        'downstream': sorted(downstream)
    }


def validate_project_structure(project_path: Path) -> bool:
    """
    Validate that a path contains a valid SQLMesh project.

    Args:
        project_path: Path to SQLMesh project

    Returns:
        True if valid, False otherwise
    """
    if not project_path.exists():
        return False

    if not project_path.is_dir():
        return False

    # Check for common SQLMesh project indicators
    indicators = [
        project_path / "config.yaml",
        project_path / "config.yml",
        project_path / "models",
    ]

    return any(indicator.exists() for indicator in indicators)


def estimate_dag_complexity(num_models: int, num_dependencies: int) -> str:
    """
    Estimate DAG complexity based on model count and dependencies.

    Args:
        num_models: Number of models
        num_dependencies: Total number of dependencies

    Returns:
        Complexity level: 'simple', 'moderate', 'complex'
    """
    avg_deps = num_dependencies / num_models if num_models > 0 else 0

    if num_models < 10 and avg_deps < 2:
        return 'simple'
    elif num_models < 50 and avg_deps < 5:
        return 'moderate'
    else:
        return 'complex'

