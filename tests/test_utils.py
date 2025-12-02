"""
Tests for utility functions
"""
import pytest
from sqlmesh_dag_generator.utils import (
    sanitize_task_id,
    parse_cron_schedule,
    detect_circular_dependencies,
    get_model_lineage,
    estimate_dag_complexity,
)
from sqlmesh_dag_generator.models import SQLMeshModelInfo


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


def test_estimate_dag_complexity():
    """Test DAG complexity estimation"""
    assert estimate_dag_complexity(5, 5) == "simple"
    assert estimate_dag_complexity(30, 60) == "moderate"
    assert estimate_dag_complexity(100, 500) == "complex"

