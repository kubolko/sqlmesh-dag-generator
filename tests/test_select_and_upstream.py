"""
select_tasks, and when it is safe to tell SQLMesh not to chase upstream models.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.models import SQLMeshModelInfo


def _models():
    return {
        "dwh.events_5m": SQLMeshModelInfo(
            name="dwh.events_5m", dependencies=set(), interval_unit="FIVE_MINUTE"
        ),
        "dwh.alerts_5m": SQLMeshModelInfo(
            name="dwh.alerts_5m", dependencies={"dwh.events_5m"}, interval_unit="FIVE_MINUTE"
        ),
        "dwh.report_daily": SQLMeshModelInfo(
            name="dwh.report_daily", dependencies={"dwh.events_5m"}, interval_unit="DAY"
        ),
    }


def _build(models=None, **kwargs):
    with patch("sqlmesh_dag_generator.generator.Context"):
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="sel",
            auto_replan_on_change=False,
            recovery_mode="disabled",
            **kwargs,
        )
        generator.models = _models()
        with DAG("sel", start_date=datetime(2024, 1, 1), schedule=None) as dag:
            tasks = generator.create_tasks_in_dag(dag, models=models)
    return generator, tasks


# -- select_tasks ----------------------------------------------------------------------


def test_select_tasks_returns_the_tasks_of_a_selection():
    generator, _ = _build()

    hot = generator.select_tasks("interval:FIVE_MINUTE")

    assert [t.task_id for t in hot] == ["sqlmesh_dwh_alerts_5m", "sqlmesh_dwh_events_5m"]


def test_select_tasks_supports_exclude_and_graph_operators():
    generator, _ = _build()

    tasks = generator.select_tasks(["dwh.events_5m+"], exclude="dwh.report_daily")

    assert [t.task_id for t in tasks] == ["sqlmesh_dwh_alerts_5m", "sqlmesh_dwh_events_5m"]


def test_select_tasks_before_building_the_dag_is_an_error():
    with patch("sqlmesh_dag_generator.generator.Context"):
        generator = SQLMeshDAGGenerator(sqlmesh_project_path="/tmp/project")
    with pytest.raises(RuntimeError, match="create_tasks_in_dag"):
        generator.select_tasks("tag:x")


# -- no_auto_upstream ---------------------------------------------------------------------


def _run_kwargs(task):
    run_ctx = MagicMock()
    run_ctx.run.return_value = MagicMock(name="SUCCESS")
    with patch("sqlmesh.Context", return_value=run_ctx):
        task.python_callable(
            data_interval_start=datetime(2024, 1, 1, 23, 55),
            data_interval_end=datetime(2024, 1, 2, 0, 0),
        )
    return run_ctx.run.call_args.kwargs


def test_no_auto_upstream_stays_off_by_default():
    _, tasks = _build()
    assert "no_auto_upstream" not in _run_kwargs(tasks["dwh.alerts_5m"])


def test_no_auto_upstream_when_every_parent_is_in_the_dag():
    _, tasks = _build(no_auto_upstream=True)
    assert _run_kwargs(tasks["dwh.alerts_5m"])["no_auto_upstream"] is True


def test_no_auto_upstream_is_withheld_when_a_parent_is_not_in_the_dag():
    # a partial DAG: events_5m is not a task here, so Airflow cannot have run it
    _, tasks = _build(models=["dwh.alerts_5m"], no_auto_upstream=True)
    assert "no_auto_upstream" not in _run_kwargs(tasks["dwh.alerts_5m"])


def test_why_no_auto_upstream_is_not_the_default(tmp_path):
    """
    Characterises SQLMesh itself: with no_auto_upstream, a child's intervals are
    processed and marked done even when its parent has no data for them yet.
    If a SQLMesh release changes this, the default can be revisited.
    """
    from sqlmesh import Context

    (tmp_path / "config.yaml").write_text(
        "gateways:\n  local:\n    connection:\n      type: duckdb\n"
        f"      database: '{tmp_path / 'wh.duckdb'}'\n"
        "default_gateway: local\nmodel_defaults:\n  dialect: duckdb\n"
    )
    (tmp_path / "models").mkdir()
    header = "kind INCREMENTAL_BY_TIME_RANGE (time_column ts, batch_size 1), start '2024-01-01', cron '@hourly'"
    (tmp_path / "models" / "parent.sql").write_text(
        f"MODEL (name demo.parent, {header});\nSELECT CAST(@start_ts AS TIMESTAMP) AS ts\n"
    )
    (tmp_path / "models" / "child.sql").write_text(
        f"MODEL (name demo.child, {header});\n"
        "SELECT ts FROM demo.parent WHERE ts BETWEEN @start_ts AND @end_ts\n"
    )

    ctx = Context(paths=str(tmp_path))
    ctx.plan("prod", no_prompts=True, auto_apply=True, skip_backfill=True)
    ctx.run(end="2024-01-01 01:00", select_models=["demo.parent"])
    ctx.run(end="2024-01-01 03:00", select_models=["demo.child"], no_auto_upstream=True)

    # SQLMesh keeps its state in the same DuckDB file here
    done = dict(
        ctx.engine_adapter.fetchall(
            "SELECT name, COUNT(*) FROM sqlmesh._intervals WHERE NOT is_removed GROUP BY name"
        )
    )
    parent = next(v for k, v in done.items() if k.endswith('"parent"'))
    child = next(v for k, v in done.items() if k.endswith('"child"'))
    assert (parent, child) == (1, 3)  # child marked 01:00-03:00 done without parent data
