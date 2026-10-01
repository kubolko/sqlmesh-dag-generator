"""Two SQLMesh projects drawn into one Airflow DAG."""

from datetime import datetime

import pytest
from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import (
    AirflowConfig,
    DAGGeneratorConfig,
    GenerationConfig,
    SQLMeshConfig,
)
from sqlmesh_dag_generator.dag_builder import AirflowDAGBuilder
from sqlmesh_dag_generator.models import DAGStructure, SQLMeshModelInfo


def _generator(prefix, tick, model_name, interval_unit, cron):
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path="/tmp/project",
        dag_id="test_shared",
        auto_replan_on_change=False,
        include_source_tables=False,
        task_id_prefix=prefix,
        dag_tick_minutes=tick,
    )
    generator.models = {
        model_name: SQLMeshModelInfo(
            name=model_name,
            dependencies=set(),
            interval_unit=interval_unit,
            cron=cron,
            kind="FULL",
        )
    }
    return generator


def test_two_projects_in_one_dag_do_not_share_task_ids():
    redshift = _generator(None, None, "dwh.raw_5m", "FIVE_MINUTE", "*/5 * * * *")
    snowflake = _generator("snowflake", 5, "api_quality_team.hlr", "DAY", "0 0 * * *")

    with DAG("test_shared", start_date=datetime(2024, 1, 1)) as dag:
        redshift_tasks = redshift.create_tasks_in_dag(dag)
        snowflake_tasks = snowflake.create_tasks_in_dag(dag)

    redshift_ids = {task.task_id for task in redshift_tasks.values()}
    snowflake_ids = {task.task_id for task in snowflake_tasks.values()}
    assert redshift_ids.isdisjoint(snowflake_ids)
    assert "sqlmesh_janitor" in redshift_ids
    assert "snowflake__sqlmesh_janitor" in snowflake_ids
    assert "snowflake__sqlmesh_api_quality_team_hlr" in snowflake_ids


def test_dag_tick_skips_a_daily_model_on_a_five_minute_dag():
    snowflake = _generator("snowflake", 5, "api_quality_team.hlr", "DAY", "0 0 * * *")

    with DAG("test_tick", start_date=datetime(2024, 1, 1)) as dag:
        tasks = snowflake.create_tasks_in_dag(dag)

    model_task = tasks["api_quality_team.hlr"]
    skipped = model_task.python_callable(
        data_interval_start=datetime(2024, 6, 1, 12, 0),
        data_interval_end=datetime(2024, 6, 1, 12, 5),
    )
    assert skipped["status"] == "skipped"
    assert skipped["reason"] == "not_due"


def test_prefix_is_normalized_and_tick_must_be_positive():
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path="/tmp/project",
        dag_id="test",
        task_id_prefix="finance-mart",
        dag_tick_minutes=15,
    )
    assert generator.config.generation.task_id_prefix == "finance_mart"
    with pytest.raises(ValueError):
        GenerationConfig(dag_tick_minutes=0)


def test_prefix_covers_sources_and_the_default_replan_task():
    class _Source:
        source_tables = ["raw.orders"]

    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path="/tmp/project",
        dag_id="test",
        task_id_prefix="finance",
        include_source_tables=True,
    )
    generator.models = {
        "mart.orders": SQLMeshModelInfo(
            name="mart.orders",
            dependencies=set(),
            interval_unit="HOUR",
            cron="0 * * * *",
            kind="FULL",
            model=_Source(),
        )
    }

    with DAG("test_prefix_ops", start_date=datetime(2024, 1, 1)) as dag:
        generator.create_tasks_in_dag(dag)

    ids = set(dag.task_dict)
    assert "finance__source__raw_orders" in ids
    assert "finance__sqlmesh_plan_apply" in ids
    assert "sqlmesh_plan_apply" not in ids
    assert "sqlmesh_janitor" not in ids


def test_generated_file_uses_the_same_prefix_and_tick():
    config = DAGGeneratorConfig(
        sqlmesh=SQLMeshConfig(project_path="/tmp/project"),
        airflow=AirflowConfig(dag_id="warehouse"),
        generation=GenerationConfig(
            task_id_prefix="finance",
            dag_tick_minutes=15,
            operator_type="python",
            auto_replan_on_change=False,
        ),
    )
    structure = DAGStructure(
        dag_id="warehouse",
        models={
            "mart.orders": SQLMeshModelInfo(
                name="mart.orders",
                dependencies=set(),
                interval_unit="DAY",
                kind="FULL",
            )
        },
    )
    code = AirflowDAGBuilder(config, structure).build()
    assert 'task_id="finance__sqlmesh_janitor"' in code
    assert "finance__sqlmesh_mart_orders" in code
    assert "EXPECTED_INTERVAL_MINUTES = 15" in code
