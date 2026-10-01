"""
Constructor hygiene and connections resolved inside the task.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.models import SQLMeshModelInfo

# -- unknown keyword arguments -------------------------------------------------------


def test_unknown_argument_is_an_error_with_a_suggestion():
    with pytest.raises(TypeError, match=r"backfil_scope \(did you mean backfill_scope\?\)"):
        SQLMeshDAGGenerator(sqlmesh_project_path="/tmp/p", backfil_scope="changed")


def test_error_names_the_installed_version():
    import sqlmesh_dag_generator

    with pytest.raises(TypeError, match=sqlmesh_dag_generator.__version__):
        SQLMeshDAGGenerator(sqlmesh_project_path="/tmp/p", option_from_the_future=True)


def test_every_config_field_is_a_valid_argument():
    """Fields that used to be silently dropped by the constructor."""
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path="/tmp/p",
        dry_run=True,
        mode="static",
        docker_image="registry/sqlmesh:1",
        namespace="dwh",
        max_parallel_tasks=4,
        start_date="2024-01-01",
        description="nightly",
        env_vars={"A": "1"},
        config_path="/tmp/p/config.yaml",
    )
    generation = generator.config.generation
    assert generation.dry_run is True
    assert generation.mode == "static"
    assert generation.docker_image == "registry/sqlmesh:1"
    assert generation.namespace == "dwh"
    assert generation.max_parallel_tasks == 4
    assert generator.config.airflow.start_date == "2024-01-01"
    assert generator.config.airflow.description == "nightly"
    assert generator.config.airflow.env_vars == {"A": "1"}
    assert generator.config.sqlmesh.config_path == "/tmp/p/config.yaml"


# -- resolve_connections="task" ----------------------------------------------------------


def test_parse_mode_resolves_at_construction():
    with patch("sqlmesh_dag_generator.airflow_utils.resolve_credentials") as resolve:
        resolve.return_value = {"type": "duckdb"}
        SQLMeshDAGGenerator(sqlmesh_project_path="/tmp/p", connection="WAREHOUSE")
    resolve.assert_called_once()


def test_task_mode_does_not_touch_connections_while_parsing():
    factory = MagicMock(side_effect=AssertionError("resolved during parse"))

    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path="/tmp/p",
        connection=factory,
        state_connection=factory,
        resolve_connections="task",
    )

    factory.assert_not_called()
    assert generator.config.sqlmesh.connection_config is None
    assert generator.config.sqlmesh.resolve_connections == "task"


def test_task_mode_uses_parse_connection_while_parsing():
    placeholder = {"type": "snowflake", "account": "x", "user": "x", "password": "x"}

    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path="/tmp/p",
        connection=MagicMock(side_effect=AssertionError("resolved during parse")),
        parse_connection=placeholder,
        resolve_connections="task",
    )

    assert generator.config.sqlmesh.connection_config == placeholder


def test_unknown_resolution_mode_is_rejected():
    with pytest.raises(ValueError, match="resolve_connections"):
        SQLMeshDAGGenerator(sqlmesh_project_path="/tmp/p", resolve_connections="lazy")


def _task_mode_generator(factory, **kwargs):
    with patch("sqlmesh_dag_generator.generator.Context"):
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="conn",
            gateway="warehouse",
            connection=factory,
            resolve_connections="task",
            auto_replan_on_change=False,
            **kwargs,
        )
        generator.models = {
            "dwh.orders": SQLMeshModelInfo(name="dwh.orders", dependencies=set()),
        }
        with DAG("conn", start_date=datetime(2024, 1, 1), schedule=None) as dag:
            tasks = generator.create_tasks_in_dag(dag)
    return generator, tasks


def test_model_task_resolves_the_connection_once_and_loads_one_context():
    calls = []

    def factory():
        calls.append(1)
        return {"type": "duckdb", "database": "/tmp/warehouse.duckdb"}

    _, tasks = _task_mode_generator(factory)
    assert not calls  # building the DAG did not resolve it

    contexts = []

    def fake_context(**kwargs):
        contexts.append(kwargs)
        ctx = MagicMock()
        ctx.run.return_value = MagicMock(name="SUCCESS")
        return ctx

    with patch("sqlmesh.Context", side_effect=fake_context):
        for hour in (1, 2):
            tasks["dwh.orders"].python_callable(
                data_interval_start=datetime(2024, 1, 1, hour - 1),
                data_interval_end=datetime(2024, 1, 1, hour),
            )

    assert len(calls) == 1  # once per process, not once per run
    assert len(contexts) == 2  # one Context per run, not two
    config = contexts[0]["config"]
    assert contexts[0]["gateway"] == "warehouse"
    assert config.gateways["warehouse"].connection.database == "/tmp/warehouse.duckdb"
