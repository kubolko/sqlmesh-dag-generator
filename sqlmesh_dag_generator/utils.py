"""
Utility functions for SQLMesh DAG Generator
"""
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Any, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


def interval_to_cron(interval_unit: Optional[Any]) -> Optional[str]:
    """
    Convert SQLMesh interval_unit to Airflow cron expression.

    Args:
        interval_unit: SQLMesh interval_unit value (e.g., IntervalUnit.HOUR)

    Returns:
        Cron expression string or None

    Note:
        SQLMesh's core intervals (as of v0.100+):
        - YEAR, QUARTER, MONTH, WEEK, DAY (calendar-based)
        - HOUR, HALF_HOUR, QUARTER_HOUR, FIVE_MINUTE, MINUTE (time-based)

        This mapping covers all documented SQLMesh intervals. If SQLMesh adds
        new intervals in the future, they will default to "@daily" (safe fallback).
    """
    if not interval_unit:
        return None

    # Convert to string and normalize (handles both "IntervalUnit.HOUR" and "HOUR")
    unit_name = str(interval_unit).upper().replace("INTERVALUNIT.", "")

    # Comprehensive mapping of SQLMesh intervals to Airflow cron expressions
    # Ordered from longest to shortest interval for readability
    mapping = {
        # Calendar-based intervals
        "YEAR": "@yearly",                  # Once per year
        "QUARTER": "0 0 1 */3 *",          # First day of every quarter (Jan, Apr, Jul, Oct)
        "MONTH": "@monthly",                # Once per month
        "WEEK": "@weekly",                  # Once per week (Sunday)
        "DAY": "@daily",                    # Once per day (midnight)

        # Time-based intervals
        "HOUR": "@hourly",                  # Every hour
        "HALF_HOUR": "*/30 * * * *",       # Every 30 minutes
        "THIRTY_MINUTE": "*/30 * * * *",   # Alias for HALF_HOUR (if exists)
        "QUARTER_HOUR": "*/15 * * * *",    # Every 15 minutes
        "FIFTEEN_MINUTE": "*/15 * * * *",  # Alias for QUARTER_HOUR (if exists)
        "TEN_MINUTE": "*/10 * * * *",      # Every 10 minutes (if supported)
        "FIVE_MINUTE": "*/5 * * * *",      # Every 5 minutes
        "MINUTE": "* * * * *",              # Every minute
    }

    return mapping.get(unit_name, "@daily")  # Safe default if unknown interval


def get_interval_frequency_minutes(interval_unit: Optional[Any]) -> int:
    """
    Get the frequency in minutes for an interval_unit.

    Args:
        interval_unit: SQLMesh interval_unit value

    Returns:
        Number of minutes between intervals

    Note:
        For calendar-based intervals (MONTH, QUARTER, YEAR), returns approximate
        values based on average month/year lengths.
    """
    if not interval_unit:
        return 1440  # Default to daily (24 * 60)

    # Convert to string and normalize
    unit_name = str(interval_unit).upper().replace("INTERVALUNIT.", "")

    # Convert to minutes for comparison (ordered shortest to longest)
    frequency_map = {
        # Time-based intervals (exact)
        "MINUTE": 1,
        "FIVE_MINUTE": 5,
        "TEN_MINUTE": 10,
        "QUARTER_HOUR": 15,
        "FIFTEEN_MINUTE": 15,       # Alias
        "HALF_HOUR": 30,
        "THIRTY_MINUTE": 30,        # Alias
        "HOUR": 60,

        # Calendar-based intervals (approximate)
        "DAY": 1440,                # 24 * 60
        "WEEK": 10080,              # 7 * 24 * 60
        "MONTH": 43200,             # ~30 * 24 * 60 (approximate)
        "QUARTER": 129600,          # ~90 * 24 * 60 (approximate)
        "YEAR": 525600,             # ~365 * 24 * 60 (approximate)
    }

    return frequency_map.get(unit_name, 1440)  # Default to daily if unknown


def get_minimum_interval(interval_units: List[Optional[Any]]) -> Tuple[Optional[Any], str]:
    """
    Find the minimum (most frequent) interval from a list of intervals.

    Args:
        interval_units: List of SQLMesh interval_unit values

    Returns:
        Tuple of (minimum interval_unit, corresponding cron expression)
    """
    if not interval_units:
        return None, "@daily"

    # Filter out None values
    valid_intervals = [iu for iu in interval_units if iu is not None]

    if not valid_intervals:
        return None, "@daily"

    # Find interval with minimum frequency (in minutes)
    min_interval = min(valid_intervals, key=get_interval_frequency_minutes)
    cron = interval_to_cron(min_interval)

    return min_interval, cron


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
    # Airflow/SQLMesh also use aliases like @hourly / @daily (handled by croniter).
    raw = cron.strip()
    if raw.startswith("@"):
        return raw

    parts = raw.split()
    if len(parts) not in [5, 6]:
        return None

    return raw


def interval_end_matches_cron(cron_expr: str, data_interval_end: datetime) -> bool:
    """
    True when ``data_interval_end`` is an exact fire time of ``cron_expr``.

    Used for mixed-cadence DAGs: schedule is the *minimum* model interval (e.g.
    ``*/5``), but coarser models (hourly/daily) should only *work* on their own
    cron ticks. Requires ``croniter`` (shipped with Airflow).
    """
    if not cron_expr or data_interval_end is None:
        return True
    try:
        from croniter import croniter
    except ImportError:  # pragma: no cover
        logger.warning(
            "croniter is not installed; cannot evaluate cron due-ness for %r",
            cron_expr,
        )
        return True

    end = data_interval_end
    probe = end - timedelta(seconds=1)
    nxt = croniter(cron_expr, probe).get_next(type(end))
    return nxt == end


def interval_end_matches_minutes(
    interval_minutes: int, data_interval_end: datetime
) -> bool:
    """
    Fallback due-check when a model has interval_unit but no cron string.

    Aligns to wall-clock boundaries (UTC if tz-aware): every N minutes from the
    hour for N < 60, on the hour for N == 60, midnight for N >= 1440.
    """
    if not interval_minutes or data_interval_end is None:
        return True
    end = data_interval_end
    if interval_minutes >= 1440:
        return end.hour == 0 and end.minute == 0 and end.second == 0
    if interval_minutes >= 60:
        # Multi-hour: require minute=0 and hour % (N/60) == 0
        hours = max(1, interval_minutes // 60)
        return end.minute == 0 and end.second == 0 and (end.hour % hours) == 0
    return end.second == 0 and (end.minute % interval_minutes) == 0


def should_skip_model_for_tick(
    *,
    cron_expr: Optional[str] = None,
    model_interval_minutes: Optional[int] = None,
    dag_tick_minutes: Optional[int] = None,
    data_interval_end: Optional[datetime] = None,
    skip_if_not_due: bool = True,
) -> bool:
    """
    Whether a model task should no-op on this Airflow DAG tick.

    When the DAG schedule is the min model interval (auto_schedule), coarser
    models still get a task every tick. Running them loads SQLMesh ``Context``
    (~tens of seconds) even when SQLMesh would do nothing. Skip those ticks
    *before* Context load when the model is not due.
    """
    if not skip_if_not_due:
        return False
    if data_interval_end is None:
        return False
    if not model_interval_minutes or not dag_tick_minutes:
        return False
    # Same cadence as the DAG (or finer): always run on every tick.
    if model_interval_minutes <= dag_tick_minutes:
        return False

    if cron_expr:
        return not interval_end_matches_cron(cron_expr, data_interval_end)
    return not interval_end_matches_minutes(model_interval_minutes, data_interval_end)


def not_due_skip_result(model_fqn: str, cron_expr: Optional[str] = None) -> Dict[str, Any]:
    """XCom-friendly payload when a model is skipped as not due."""
    return {
        "status": "skipped",
        "reason": "not_due",
        "model": model_fqn,
        "cron": cron_expr,
    }


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

