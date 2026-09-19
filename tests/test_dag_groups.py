"""
Tests for splitting one SQLMesh project into several Airflow DAGs.
"""

from unittest.mock import patch

import pytest

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig
from sqlmesh_dag_generator.dag_groups import (
    build_dag_groups,
    describe_dag_groups,
    plan_dag_groups,
)
from sqlmesh_dag_generator.models import SQLMeshModelInfo


def _models():
    """raw.events -> stg.events -> marts.finance_daily / marts.marketing_daily"""
    return {
        "raw.events": SQLMeshModelInfo(
            name="raw.events",
            dependencies=set(),
            tags=["bronze"],
            interval_unit="IntervalUnit.HOUR",
        ),
        "stg.events": SQLMeshModelInfo(
            name="stg.events",
            dependencies={"raw.events"},
            tags=["silver", "finance"],
            interval_unit="IntervalUnit.HOUR",
        ),
        "marts.finance_daily": SQLMeshModelInfo(
            name="marts.finance_daily",
            dependencies={"stg.events"},
            tags=["finance"],
            interval_unit="IntervalUnit.DAY",
        ),
        "marts.marketing_daily": SQLMeshModelInfo(
            name="marts.marketing_daily",
            dependencies={"stg.events"},
            tags=["marketing"],
            interval_unit="IntervalUnit.DAY",
        ),
    }


def _config(**group_overrides):
    finance_group = {
        "dag_id": "dwh_finance",
        "select": ["tag:finance"],
        "schedule": "@hourly",
    }
    marketing_group = {
        "dag_id": "dwh_marketing",
        "select": ["tag:marketing"],
    }
    marketing_group.update(group_overrides)
    return DAGGeneratorConfig.from_dict(
        {
            "sqlmesh": {"project_path": "/tmp/project"},
            "airflow": {"dag_id": "dwh", "start_date": "2024-01-01"},
            "generation": {"auto_replan_on_change": False, "include_source_tables": False},
            "dag_groups": [finance_group, marketing_group],
        }
    )


@pytest.fixture
def generator():
    with patch("sqlmesh_dag_generator.generator.Context"):
        gen = SQLMeshDAGGenerator(config=_config())
        gen.models = _models()
        yield gen


def test_plan_assigns_models_to_groups(generator):
    plans = plan_dag_groups(generator.config, generator.models)

    assert [p.dag_id for p in plans] == ["dwh_finance", "dwh_marketing"]
    assert plans[0].model_names == ["marts.finance_daily", "stg.events"]
    assert plans[1].model_names == ["marts.marketing_daily"]


def test_cross_group_dependencies_are_detected(generator):
    plans = plan_dag_groups(generator.config, generator.models)

    # marketing_daily reads stg.events, which belongs to the finance group
    assert plans[1].external_upstreams == {"stg.events": "dwh_finance"}
    assert plans[0].external_upstreams == {}


def test_strict_mode_rejects_models_claimed_twice(generator):
    config = generator.config
    config.dag_groups[1].select = ["tag:finance"]

    with pytest.raises(ValueError, match="selected by both"):
        plan_dag_groups(config, generator.models, strict=True)


def test_uncovered_models_are_reported(generator, caplog):
    config = generator.config
    config.dag_groups[1].select = ["tag:nothing_matches_this"]

    with caplog.at_level("WARNING"):
        plan_dag_groups(config, generator.models)

    assert "not part of any DAG group" in caplog.text


def test_build_dag_groups_creates_one_dag_per_group(generator):
    dags = build_dag_groups(generator.config, generator=generator)

    assert sorted(dags) == ["dwh_finance", "dwh_marketing"]
    finance_tasks = set(dags["dwh_finance"].task_dict)
    assert {"sqlmesh_stg_events", "sqlmesh_marts_finance_daily"} <= finance_tasks
    assert "sqlmesh_marts_marketing_daily" not in finance_tasks


def test_group_schedule_falls_back_to_shortest_model_interval(generator):
    # The marketing group has no explicit schedule and only daily models, but it
    # depends on the finance group, so datasets drive it instead of a cron.
    described = describe_dag_groups(generator.config, generator.models)
    assert described[0]["schedule"] == "@hourly"
    assert described[1]["schedule"] == "@daily"
    assert described[1]["external_upstreams"] == {"stg.events": "dwh_finance"}


def _scheduling_dataset_uris(dag):
    """Dataset URIs a DAG is scheduled on (Airflow 2.9+ / 3 shapes)."""
    condition = getattr(dag.timetable, "dataset_condition", None) or getattr(
        dag.timetable, "asset_condition", None
    )
    if condition is None:
        return []
    return sorted(obj.uri for obj in condition.objects)


def test_dataset_mode_schedules_downstream_dag_on_upstream_models(generator):
    dags = build_dag_groups(generator.config, generator=generator)

    uris = _scheduling_dataset_uris(dags["dwh_marketing"])
    assert uris == ["sqlmesh://models/stg.events"]

    # ... and the producing task in the other DAG publishes exactly that dataset
    producer = dags["dwh_finance"].task_dict["sqlmesh_stg_events"]
    assert sorted(d.uri for d in producer.outlets) == uris


def test_sensor_mode_adds_external_task_sensors():
    config = _config(wait_for_upstream="sensor")
    with patch("sqlmesh_dag_generator.generator.Context"):
        gen = SQLMeshDAGGenerator(config=config)
        gen.models = _models()
        dags = build_dag_groups(config, generator=gen)

    marketing = dags["dwh_marketing"]
    sensor = marketing.task_dict["wait_for__stg_events"]
    assert sensor.external_dag_id == "dwh_finance"
    assert sensor.external_task_id == "sqlmesh_stg_events"
    assert "sqlmesh_marts_marketing_daily" in sensor.downstream_task_ids
    # sensor mode does not publish datasets
    assert not dags["dwh_finance"].task_dict["sqlmesh_stg_events"].outlets


def test_generation_overrides_per_group():
    config = _config(generation_overrides={"skip_if_not_due": False})
    with patch("sqlmesh_dag_generator.generator.Context"):
        gen = SQLMeshDAGGenerator(config=config)
        gen.models = _models()
        build_dag_groups(config, generator=gen)

    # the base generator keeps its own settings
    assert gen.config.generation.skip_if_not_due is True


def test_unknown_generation_override_is_rejected():
    config = _config(generation_overrides={"not_a_setting": 1})
    with patch("sqlmesh_dag_generator.generator.Context"):
        gen = SQLMeshDAGGenerator(config=config)
        gen.models = _models()
        with pytest.raises(ValueError, match="Unknown generation override"):
            build_dag_groups(config, generator=gen)
