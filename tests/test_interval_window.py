"""
interval_window: who decides which intervals a model task processes.

``airflow`` passes the DAG run's data interval to SQLMesh. ``sqlmesh`` passes only
the end of it and lets SQLMesh fill whatever its state says is missing, which
makes the integrity guard and the bounded recovery task unnecessary.
"""

import ast
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig, GenerationConfig
from sqlmesh_dag_generator.models import SQLMeshModelInfo

# -- configuration ---------------------------------------------------------------


def test_default_is_the_airflow_window():
    assert GenerationConfig().interval_window == "airflow"


def test_value_is_normalised_and_validated():
    assert GenerationConfig(interval_window=" SQLMesh ").interval_window == "sqlmesh"
    with pytest.raises(ValueError, match="interval_window"):
        GenerationConfig(interval_window="wall_clock")


def test_round_trips_through_yaml_dict():
    config = DAGGeneratorConfig.from_dict(
        {
            "sqlmesh": {"project_path": "/tmp/p"},
            "airflow": {"dag_id": "d"},
            "generation": {"interval_window": "sqlmesh"},
        }
    )
    assert config.to_dict()["generation"]["interval_window"] == "sqlmesh"


# -- runtime tasks (create_tasks_in_dag) -----------------------------------------


def _models():
    return {
        "dwh.events_5m": SQLMeshModelInfo(
            name="dwh.events_5m",
            dependencies=set(),
            interval_unit="FIVE_MINUTE",
            kind="INCREMENTAL_BY_TIME_RANGE",
        ),
        "dwh.events_hourly": SQLMeshModelInfo(
            name="dwh.events_hourly",
            dependencies={"dwh.events_5m"},
            interval_unit="HOUR",
            kind="INCREMENTAL_BY_TIME_RANGE",
        ),
    }


def _build(window, **kwargs):
    kwargs.setdefault("recovery_mode", "bounded_auto")
    with patch("sqlmesh_dag_generator.generator.Context"):
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="win",
            auto_replan_on_change=False,
            interval_window=window,
            **kwargs,
        )
        generator.models = _models()
        with DAG("win", start_date=datetime(2024, 1, 1), schedule=None) as dag:
            tasks = generator.create_tasks_in_dag(dag)
    return generator, dag, tasks


def _run(task, **context):
    run_ctx = MagicMock()
    run_ctx.run.return_value = MagicMock(name="SUCCESS")
    with patch("sqlmesh.Context", return_value=run_ctx):
        task.python_callable(**context)
    run_ctx.run.assert_called_once()
    return run_ctx.run.call_args.kwargs


def test_sqlmesh_window_passes_only_the_end():
    _, _, tasks = _build("sqlmesh")

    kwargs = _run(
        tasks["dwh.events_5m"],
        data_interval_start=datetime(2024, 1, 6, 12, 0),
        data_interval_end=datetime(2024, 1, 6, 12, 5),
    )

    assert "start" not in kwargs
    assert kwargs["end"] == datetime(2024, 1, 6, 12, 5)
    assert kwargs["select_models"] == ["dwh.events_5m"]


def test_coarser_models_also_stop_at_the_run_end_not_at_now():
    _, _, tasks = _build("sqlmesh")

    kwargs = _run(
        tasks["dwh.events_hourly"],
        data_interval_start=datetime(2024, 1, 6, 12, 55),
        data_interval_end=datetime(2024, 1, 6, 13, 0),
    )

    assert "start" not in kwargs
    assert kwargs["end"] == datetime(2024, 1, 6, 13, 0)


def test_manual_run_without_a_data_interval_runs_up_to_now():
    """Airflow 3 can trigger a run with no logical date, so no data interval."""
    _, _, tasks = _build("sqlmesh")

    kwargs = _run(tasks["dwh.events_5m"])

    assert "start" not in kwargs and "end" not in kwargs


def test_airflow_window_is_unchanged():
    _, _, tasks = _build("airflow")

    kwargs = _run(
        tasks["dwh.events_5m"],
        data_interval_start=datetime(2024, 1, 6, 12, 0),
        data_interval_end=datetime(2024, 1, 6, 12, 5),
    )

    assert kwargs["start"] == datetime(2024, 1, 6, 12, 0)
    assert kwargs["end"] == datetime(2024, 1, 6, 12, 5)


def test_sqlmesh_window_adds_no_recovery_tasks():
    _, dag, _ = _build("sqlmesh")

    assert "sqlmesh_integrity_guard" not in dag.task_dict
    assert "sqlmesh_recovery_backfill" not in dag.task_dict
    # the hot-path model is a root again, so a gate placed on roots can find it
    roots = {t.task_id for t in dag.tasks if not t.upstream_task_ids}
    assert "sqlmesh_dwh_events_5m" in roots


def test_airflow_window_still_adds_recovery_tasks():
    _, dag, _ = _build("airflow")
    assert "sqlmesh_integrity_guard" in dag.task_dict


def test_no_catchup_warning_when_sqlmesh_fills_the_gaps():
    generator, _, _ = _build("sqlmesh", recovery_mode="disabled")
    assert generator._integrity_warning_message() is None


# -- generated DAG files --------------------------------------------------------------


@pytest.fixture(scope="module")
def project():
    path = Path(tempfile.mkdtemp(prefix="sqlmesh_window_"))
    (path / "config.yaml").write_text(
        "gateways:\n  local:\n    connection:\n      type: duckdb\n      database: ':memory:'\n"
        "default_gateway: local\nmodel_defaults:\n  dialect: duckdb\n  start: 2024-01-01\n"
    )
    (path / "models").mkdir()
    (path / "models" / "events.sql").write_text(
        "MODEL (name demo.events, kind INCREMENTAL_BY_TIME_RANGE (time_column ts), cron '@hourly');\n\n"
        "SELECT CAST(@start_ts AS TIMESTAMP) AS ts\n"
    )
    yield str(path)
    shutil.rmtree(path, ignore_errors=True)


def _generated(project, operator_type="python", window="sqlmesh", dynamic=False):
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=project,
        dag_id="gen",
        dry_run=True,
        operator_type=operator_type,
        interval_window=window,
    )
    generator.config.generation.docker_image = "registry/sqlmesh:1"
    code = generator.generate_dynamic_dag() if dynamic else generator.generate_dag()
    ast.parse(code, feature_version=(3, 9))
    return code


@pytest.mark.parametrize("operator_type", ["python", "bash", "kubernetes"])
@pytest.mark.parametrize("window", ["airflow", "sqlmesh"])
def test_generated_files_are_valid_python_39(project, operator_type, window):
    _generated(project, operator_type, window)


def test_generated_python_task_uses_the_window_constant(project):
    code = _generated(project)
    assert 'INTERVAL_WINDOW = "sqlmesh"' in code
    assert '{"end": end} if INTERVAL_WINDOW == "sqlmesh"' in code


def _bash_commands(code):
    """The model `sqlmesh run` commands as Airflow will see them, read from the AST."""
    commands = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "BashOperator":
            for keyword in node.keywords:
                if keyword.arg == "bash_command":
                    commands.append(ast.literal_eval(keyword.value))
    # the janitor is a BashOperator too; only model runs matter here
    return [command for command in commands if "sqlmesh run" in command]


def test_generated_bash_task_passes_the_end(project):
    (command,) = _bash_commands(_generated(project, operator_type="bash"))
    assert command.endswith("--end '{{ data_interval_end or dag_run.run_after }}'")


def test_generated_bash_task_survives_quoted_model_names(project):
    """SQLMesh model keys are quoted FQNs; 0.12.0 wrote them into a broken string."""
    (command,) = _bash_commands(_generated(project, operator_type="bash", window="airflow"))
    assert """--select-models '"memory"."demo"."events"'""" in command


def test_generated_kubernetes_task_drops_the_start(project):
    sqlmesh_code = _generated(project, operator_type="kubernetes")
    airflow_code = _generated(project, operator_type="kubernetes", window="airflow")
    assert "--start" not in sqlmesh_code
    assert "--start" in airflow_code


def test_generated_dynamic_dag_skips_recovery(project):
    code = _generated(project, dynamic=True)
    assert 'INTERVAL_WINDOW = "sqlmesh"' in code
    assert 'if INTERVAL_WINDOW == "airflow" and RECOVERY_MODE != "disabled"' in code


# -- end to end: does the gap actually close? ---------------------------------------


def _gap_project(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "gateways:\n  local:\n    connection:\n      type: duckdb\n"
        f"      database: '{tmp_path / 'warehouse.duckdb'}'\n"
        "default_gateway: local\nmodel_defaults:\n  dialect: duckdb\n"
    )
    (tmp_path / "models").mkdir()
    # One row per processed batch, stamped with the batch start.
    (tmp_path / "models" / "hourly.sql").write_text(
        "MODEL (\n  name demo.hourly,\n"
        "  kind INCREMENTAL_BY_TIME_RANGE (time_column ts, batch_size 1),\n"
        "  start '2024-01-01',\n  cron '@hourly'\n);\n\n"
        "SELECT CAST(@start_ts AS TIMESTAMP) AS ts\n"
    )
    from sqlmesh import Context

    # Publish without filling anything, like the deploy DAG before the first tick.
    Context(paths=str(tmp_path)).plan("prod", no_prompts=True, auto_apply=True, skip_backfill=True)


def _filled_hours(tmp_path):
    from sqlmesh import Context

    rows = Context(paths=str(tmp_path)).engine_adapter.fetchall(
        "SELECT ts FROM demo.hourly ORDER BY ts"
    )
    return [row[0].strftime("%H:%M") for row in rows]


def _tick(task, start_hour, end_hour):
    task.python_callable(
        data_interval_start=datetime(2024, 1, 1, start_hour),
        data_interval_end=datetime(2024, 1, 1, end_hour),
    )


@pytest.mark.parametrize(
    "window, expected",
    [
        # the 03:00-06:00 outage stays a hole: that is what the integrity guard patched
        ("airflow", ["00:00", "01:00", "02:00", "06:00"]),
        # the first run after the outage fills it from SQLMesh state
        ("sqlmesh", ["00:00", "01:00", "02:00", "03:00", "04:00", "05:00", "06:00"]),
    ],
)
def test_outage_gap_after_restart(tmp_path, window, expected):
    _gap_project(tmp_path)
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=str(tmp_path),
        dag_id="gap",
        auto_replan_on_change=False,
        recovery_mode="disabled",
        interval_window=window,
    )
    with DAG("gap", start_date=datetime(2024, 1, 1), schedule=None) as dag:
        tasks = generator.create_tasks_in_dag(dag)
    task = next(t for name, t in tasks.items() if name.endswith('"hourly"'))

    _tick(task, 0, 3)  # three hours of normal ticks
    _tick(task, 6, 7)  # scheduler was down 03:00-06:00; next run covers 06:00-07:00

    assert _filled_hours(tmp_path) == expected
