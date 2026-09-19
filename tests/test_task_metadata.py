"""
Tests for what the generator puts on the Airflow tasks themselves:
model documentation, per-selection overrides, datasets, audit tasks.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.models import SQLMeshModelInfo


def _models():
    return {
        "dwh.orders": SQLMeshModelInfo(
            name="dwh.orders",
            dependencies=set(),
            tags=["core", "heavy"],
            kind="INCREMENTAL_BY_TIME_RANGE",
            owner="data-eng",
            description="All orders, one row per order line.",
            cron="@hourly",
            cron_tz="Europe/Warsaw",
            path="models/marts/orders.sql",
            audits=["not_null", "unique_values"],
        ),
        "dwh.orders_summary": SQLMeshModelInfo(
            name="dwh.orders_summary",
            dependencies={"dwh.orders"},
            tags=["core"],
        ),
    }


def _generator(**kwargs):
    with patch("sqlmesh_dag_generator.generator.Context"):
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="meta",
            auto_replan_on_change=False,
            include_source_tables=False,
            **kwargs,
        )
        generator.models = _models()
        return generator


def _build(generator):
    with DAG("meta", start_date=datetime(2024, 1, 1), schedule=None) as dag:
        return dag, generator.create_tasks_in_dag(dag)


def test_model_metadata_lands_on_the_task():
    _, tasks = _build(_generator())
    task = tasks["dwh.orders"]

    assert task.owner == "data-eng"
    assert "All orders, one row per order line." in task.doc_md
    assert "`INCREMENTAL_BY_TIME_RANGE`" in task.doc_md
    assert "Europe/Warsaw" in task.doc_md
    assert "not_null, unique_values" in task.doc_md
    assert "models/marts/orders.sql" in task.doc_md


def test_model_docs_can_be_switched_off():
    _, tasks = _build(_generator(model_docs=False))
    assert tasks["dwh.orders"].doc_md is None


def test_task_overrides_apply_to_the_selected_models():
    generator = _generator(
        task_overrides=[
            {
                "select": ["tag:heavy"],
                "pool": "heavy_pool",
                "retries": 5,
                "execution_timeout_minutes": 90,
                "queue": "big",
            }
        ]
    )
    _, tasks = _build(generator)

    heavy = tasks["dwh.orders"]
    light = tasks["dwh.orders_summary"]

    assert heavy.pool == "heavy_pool"
    assert heavy.retries == 5
    assert heavy.execution_timeout == timedelta(minutes=90)
    assert heavy.queue == "big"
    assert light.pool == "default_pool"
    assert light.retries != 5


def test_later_task_overrides_win():
    generator = _generator(
        task_overrides=[
            {"select": ["tag:core"], "pool": "core_pool"},
            {"select": ["tag:heavy"], "pool": "heavy_pool"},
        ]
    )
    _, tasks = _build(generator)

    assert tasks["dwh.orders"].pool == "heavy_pool"
    assert tasks["dwh.orders_summary"].pool == "core_pool"


def test_datasets_are_emitted_per_model():
    _, tasks = _build(_generator(emit_datasets=True))

    assert [d.uri for d in tasks["dwh.orders"].outlets] == ["sqlmesh://models/dwh.orders"]


def test_datasets_are_off_by_default():
    _, tasks = _build(_generator())
    assert not tasks["dwh.orders"].outlets


def test_audit_tasks_gate_downstream_models():
    _, tasks = _build(_generator(audit_tasks=True))

    audit = tasks["dwh.orders__audit"]
    assert audit.task_id == "sqlmesh_dwh_orders__audit"
    assert "sqlmesh_dwh_orders" in audit.upstream_task_ids
    # the child waits for the audit, not for the model task directly
    assert "sqlmesh_dwh_orders_summary" in audit.downstream_task_ids
    assert tasks["dwh.orders_summary"].upstream_task_ids == {"sqlmesh_dwh_orders__audit"}


def test_models_without_audits_get_no_audit_task():
    _, tasks = _build(_generator(audit_tasks=True))
    assert "dwh.orders_summary__audit" not in tasks


def _callbacks(task):
    """Airflow 2 stores a single callback, Airflow 3 stores a list of them."""
    callbacks = task.on_failure_callback
    if callbacks is None:
        return []
    return list(callbacks) if isinstance(callbacks, (list, tuple)) else [callbacks]


def test_failure_callback_is_imported_from_a_dotted_path():
    generator = _generator(on_failure_callback="json.dumps")
    _, tasks = _build(generator)

    import json

    assert _callbacks(tasks["dwh.orders"]) == [json.dumps]


def test_unimportable_callback_is_ignored(caplog):
    with caplog.at_level("WARNING"):
        generator = _generator(on_failure_callback="not_a_module.nope")
        _, tasks = _build(generator)

    assert _callbacks(tasks["dwh.orders"]) == []
    assert "Could not import callback" in caplog.text


def test_datasets_move_to_the_audit_task_when_audits_gate_the_model():
    _, tasks = _build(_generator(emit_datasets=True, audit_tasks=True))

    assert not tasks["dwh.orders"].outlets
    assert [d.uri for d in tasks["dwh.orders__audit"].outlets] == ["sqlmesh://models/dwh.orders"]
    # a model without audits keeps its own outlet
    assert [d.uri for d in tasks["dwh.orders_summary"].outlets] == [
        "sqlmesh://models/dwh.orders_summary"
    ]
