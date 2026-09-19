"""
Tests for utility functions
"""

from sqlmesh_dag_generator.models import SQLMeshModelInfo
from sqlmesh_dag_generator.utils import (
    detect_circular_dependencies,
    get_model_lineage,
    localize_to_cron_tz,
    parse_cron_schedule,
    sanitize_task_id,
)


def test_sanitize_task_id():
    """Test task ID sanitization"""
    assert sanitize_task_id("my.model.name") == "my_model_name"
    assert sanitize_task_id("model-with-dashes") == "model_with_dashes"
    assert sanitize_task_id("model__multiple___underscores") == "model_multiple_underscores"
    assert sanitize_task_id("___leading_trailing___") == "leading_trailing"


def test_parse_cron_schedule():
    """Test cron schedule parsing"""
    assert parse_cron_schedule("0 0 * * *") == "0 0 * * *"
    assert parse_cron_schedule("0 2 * * MON") == "0 2 * * MON"
    assert parse_cron_schedule("invalid") is None
    assert parse_cron_schedule(None) is None


def test_detect_circular_dependencies():
    """Test circular dependency detection"""
    # No cycle
    deps = {
        "a": {"b"},
        "b": {"c"},
        "c": set(),
    }
    assert detect_circular_dependencies(deps) is None

    # Simple cycle
    deps_cycle = {
        "a": {"b"},
        "b": {"a"},
    }
    cycle = detect_circular_dependencies(deps_cycle)
    assert cycle is not None
    assert "a" in cycle and "b" in cycle


def test_get_model_lineage():
    """Test model lineage extraction"""
    models = {
        "model1": SQLMeshModelInfo(name="model1", dependencies=set()),
        "model2": SQLMeshModelInfo(name="model2", dependencies={"model1"}),
        "model3": SQLMeshModelInfo(name="model3", dependencies={"model2"}),
    }

    lineage = get_model_lineage("model2", models)

    assert "model1" in lineage["upstream"]
    assert "model3" in lineage["downstream"]


def test_localize_to_cron_tz():
    """Naive timestamps are assumed to be UTC before converting."""
    from datetime import datetime, timezone

    naive = datetime(2024, 7, 1, 22, 0)
    localized = localize_to_cron_tz(naive, "Europe/Warsaw")
    assert localized.hour == 0 and localized.day == 2

    aware = datetime(2024, 7, 1, 22, 0, tzinfo=timezone.utc)
    assert localize_to_cron_tz(aware, "Europe/Warsaw").hour == 0
    assert localize_to_cron_tz(aware, None) is aware
