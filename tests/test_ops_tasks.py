"""
Tests for the SQLMesh maintenance tasks (audit / test / lint / janitor / restate).
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from airflow import DAG
from airflow.exceptions import AirflowException

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.models import SQLMeshModelInfo
from sqlmesh_dag_generator.ops_tasks import supported_kwargs


@pytest.fixture
def generator():
    with patch("sqlmesh_dag_generator.generator.Context"):
        gen = SQLMeshDAGGenerator(sqlmesh_project_path="/tmp/project", dag_id="ops")
        gen.models = {
            "dwh.orders": SQLMeshModelInfo(
                name="dwh.orders", dependencies=set(), audits=["not_null"]
            )
        }
        gen.merged_config = object()  # pretend the context was already loaded
        yield gen


def _dag():
    return DAG("ops_test", start_date=datetime(2024, 1, 1), schedule=None)


def test_supported_kwargs_drops_unknown_arguments(caplog):
    def plan(environment=None, restate_models=None):
        return None

    with caplog.at_level("WARNING"):
        kwargs = supported_kwargs(plan, {"environment": "", "min_intervals": 3})

    assert kwargs == {"environment": ""}
    assert "min_intervals" in caplog.text


def test_supported_kwargs_passes_everything_to_var_keyword_callables():
    def run(**kwargs):
        return None

    assert supported_kwargs(run, {"anything": 1}) == {"anything": 1}


def test_audit_task_runs_audits_for_the_data_interval(generator):
    run_ctx = MagicMock()
    run_ctx.audit.return_value = True

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_audit_task(dag)
        result = task.python_callable(
            data_interval_start=datetime(2024, 5, 1),
            data_interval_end=datetime(2024, 5, 2),
        )

    _, kwargs = run_ctx.audit.call_args
    assert kwargs["models"] == ["dwh.orders"]
    assert kwargs["start"] == datetime(2024, 5, 1)
    assert result["status"] == "passed"


def test_audit_task_fails_the_task_when_an_audit_fails(generator):
    run_ctx = MagicMock()
    run_ctx.audit.return_value = False

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_audit_task(dag)
        with pytest.raises(AirflowException, match="audits failed"):
            task.python_callable(
                data_interval_start=datetime(2024, 5, 1),
                data_interval_end=datetime(2024, 5, 2),
            )


def test_non_blocking_audit_task_only_warns(generator):
    run_ctx = MagicMock()
    run_ctx.audit.return_value = False

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_audit_task(dag, blocking=False)
        result = task.python_callable(
            data_interval_start=datetime(2024, 5, 1),
            data_interval_end=datetime(2024, 5, 2),
        )

    assert result["status"] == "failed"


def test_unit_test_task_raises_on_failures(generator):
    run_ctx = MagicMock()
    result = MagicMock()
    result.failures = [("test_orders", "AssertionError")]
    result.errors = []
    result.testsRun = 4
    run_ctx.test.return_value = result

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_unit_test_task(dag)
        with pytest.raises(AirflowException, match="unit tests failed"):
            task.python_callable()


def test_unit_test_task_passes(generator):
    run_ctx = MagicMock()
    result = MagicMock()
    result.failures = []
    result.errors = []
    result.testsRun = 4
    run_ctx.test.return_value = result

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_unit_test_task(dag)
        assert task.python_callable() == {"status": "passed", "tests_run": 4}


def test_lint_task_raises_on_error_violations(generator):
    violation = MagicMock()
    violation.violation_type = "error"
    run_ctx = MagicMock()
    run_ctx.lint_models.return_value = [violation]

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_lint_task(dag)
        with pytest.raises(AirflowException, match="error-level violation"):
            task.python_callable()


def test_lint_task_ignores_warning_violations(generator):
    violation = MagicMock()
    violation.violation_type = "warning"
    run_ctx = MagicMock()
    run_ctx.lint_models.return_value = [violation]

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_lint_task(dag)
        result = task.python_callable()

    assert result == {"status": "passed", "violations": 1, "errors": 0}


def test_lint_task_skips_on_sqlmesh_without_linter(generator):
    run_ctx = MagicMock(spec=["run", "plan", "audit"])  # no lint_models

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_lint_task(dag)
        assert task.python_callable()["status"] == "skipped"


def test_janitor_task_passes_environment_from_conf(generator):
    run_ctx = MagicMock()
    dag_run = MagicMock()
    dag_run.conf = {"environment": "dev_jane"}

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_janitor_task(dag)
        result = task.python_callable(dag_run=dag_run)

    _, kwargs = run_ctx.run_janitor.call_args
    assert kwargs["environment"] == "dev_jane"
    assert result["status"] == "completed"


def test_restate_task_requires_models(generator):
    run_ctx = MagicMock()

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_restate_task(dag)
        with pytest.raises(AirflowException, match="needs models"):
            task.python_callable(dag_run=MagicMock(conf={"start": "2024-01-01"}))


def test_restate_task_plans_with_restate_models(generator):
    run_ctx = MagicMock()
    dag_run = MagicMock()
    dag_run.conf = {"models": "dwh.orders", "start": "2024-01-01", "end": "2024-01-08"}

    with patch("sqlmesh.Context", return_value=run_ctx):
        with _dag() as dag:
            task = generator.create_restate_task(dag)
        result = task.python_callable(dag_run=dag_run)

    _, kwargs = run_ctx.plan.call_args
    assert kwargs["restate_models"] == ["dwh.orders"]
    assert kwargs["auto_apply"] is True
    assert result["models"] == ["dwh.orders"]
