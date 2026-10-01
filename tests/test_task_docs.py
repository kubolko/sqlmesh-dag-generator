"""
Tests for what each task says about its table in the Airflow UI:
display names, doc cards for models and sources, and the run summary log.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.airflow_compat import supports_task_display_name
from sqlmesh_dag_generator.models import SQLMeshModelInfo
from sqlmesh_dag_generator.task_docs import (
    MAX_DOC_COLUMNS,
    display_label,
    model_doc_md,
    model_run_summary,
    source_doc_md,
)


def _orders():
    return SQLMeshModelInfo(
        name="dwh.orders",
        kind="IncrementalByTimeRangeKind<dialect: snowflake, time_column: ds>",
        time_column="ds",
        cron="@hourly",
        cron_tz="Europe/Warsaw",
        owner="data-eng",
        description="All orders, one row per order line.",
        grains=["order_id"],
        columns={"order_id": "INT", "amount": "DECIMAL(10, 2)", "note": "UNKNOWN"},
        column_descriptions={"order_id": "Primary key | from the shop"},
    )


# -- pure card rendering -------------------------------------------------------


def test_model_card_has_table_kind_lineage_and_columns():
    doc = model_doc_md(
        _orders(),
        reads_models=["dwh.stg_orders"],
        reads_sources=["RAW.SHOP.ORDERS"],
        read_by=["dwh.orders_daily"],
    )

    assert "| Table | `dwh.orders` |" in doc
    assert "`INCREMENTAL_BY_TIME_RANGE` on `ds`" in doc
    assert "`@hourly` (Europe/Warsaw)" in doc
    assert "| Grain | `order_id` |" in doc
    assert "- `dwh.stg_orders`" in doc
    assert "- `RAW.SHOP.ORDERS` (source)" in doc
    assert "#### Read by" in doc and "- `dwh.orders_daily`" in doc
    assert "#### Columns (3)" in doc
    assert "| `amount` | `DECIMAL(10, 2)` |" in doc


def test_unknown_column_types_are_left_blank():
    doc = model_doc_md(_orders())
    assert "| `note` |  |" in doc
    assert "UNKNOWN" not in doc


def test_pipes_in_descriptions_do_not_break_the_table():
    doc = model_doc_md(_orders())
    assert "Primary key \\| from the shop" in doc


def test_very_wide_tables_are_capped():
    info = SQLMeshModelInfo(
        name="dwh.wide", columns={f"c{i}": "INT" for i in range(MAX_DOC_COLUMNS + 5)}
    )
    doc = model_doc_md(info)
    assert "... and 5 more columns." in doc
    assert f"`c{MAX_DOC_COLUMNS}`" not in doc


def test_source_card_splits_the_name_and_lists_readers():
    doc = source_doc_md('"RAW"."API_ODS"."EVENT_HUB"', read_by=["dwh.events", "dwh.logs"])

    assert doc.startswith("### `RAW.API_ODS.EVENT_HUB` (source)")
    assert "| Catalog | `RAW` |" in doc
    assert "| Schema | `API_ODS` |" in doc
    assert "- `dwh.events`" in doc and "- `dwh.logs`" in doc
    assert "create_external_models" in doc


def test_display_label():
    assert display_label('"db"."dwh"."orders"') == "db.dwh.orders"
    assert display_label("API_ODS.EVENTS", source=True) == "API_ODS.EVENTS (source)"
    assert display_label("dwh.orders", prefix="snowflake") == "[snowflake] dwh.orders"


def test_run_summary_is_short():
    summary = model_run_summary(
        _orders(),
        reads_models=[f"dwh.m{i}" for i in range(8)],
        reads_sources=[],
        read_by=["dwh.orders_daily"],
    )
    assert summary.startswith("Model dwh.orders [INCREMENTAL_BY_TIME_RANGE]")
    assert "(+3 more)" in summary
    assert "reads sources: -" in summary


# -- wired into the DAG ----------------------------------------------------------


def _models():
    stg = SQLMeshModelInfo(name="dwh.stg_orders", dependencies=set())
    orders = _orders()
    orders.dependencies = {"dwh.stg_orders"}
    daily = SQLMeshModelInfo(name="dwh.orders_daily", dependencies={"dwh.orders"})
    return {m.name: m for m in (stg, orders, daily)}


def _build(**kwargs):
    with patch("sqlmesh_dag_generator.generator.Context"):
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="docs",
            auto_replan_on_change=False,
            **kwargs,
        )
        generator.models = _models()
        with DAG("docs", start_date=datetime(2024, 1, 1), schedule=None) as dag:
            tasks = generator.create_tasks_in_dag(dag)
    return generator, dag, tasks


def test_model_tasks_get_lineage_in_their_card():
    _, _, tasks = _build()
    doc = tasks["dwh.orders"].doc_md

    assert "- `dwh.stg_orders`" in doc  # reads from
    assert "- `dwh.orders_daily`" in doc  # read by


def test_tasks_are_labelled_with_the_table_name():
    _, _, tasks = _build(task_id_prefix="snowflake")
    if not supports_task_display_name():  # pragma: no cover - Airflow < 2.9
        return

    assert tasks["dwh.orders"].task_display_name == "[snowflake] dwh.orders"
    assert tasks["dwh.orders"].task_id == "snowflake__sqlmesh_dwh_orders"


def test_display_names_can_be_switched_off():
    _, _, tasks = _build(task_display_names=False)
    assert tasks["dwh.orders"].task_display_name == tasks["dwh.orders"].task_id


def test_source_tasks_get_a_card_and_a_label():
    generator, dag, _ = _build()
    with patch.object(
        SQLMeshDAGGenerator,
        "get_source_tables",
        lambda self, name: ['"RAW"."SHOP"."ORDERS"'] if name == "dwh.stg_orders" else [],
    ):
        with DAG("docs_src", start_date=datetime(2024, 1, 1), schedule=None) as dag:
            generator.create_tasks_in_dag(dag)

    source = dag.get_task("source__RAW_SHOP_ORDERS")
    assert "### `RAW.SHOP.ORDERS` (source)" in source.doc_md
    assert "- `dwh.stg_orders`" in source.doc_md
    if supports_task_display_name():
        assert source.task_display_name == "RAW.SHOP.ORDERS (source)"


def test_model_docs_off_means_no_cards_anywhere():
    generator, _, tasks = _build(model_docs=False)
    assert tasks["dwh.orders"].doc_md is None


def test_model_task_logs_what_it_builds(caplog):
    run_ctx = MagicMock()
    run_ctx.run.return_value = MagicMock(name="SUCCESS")
    _, _, tasks = _build()

    with patch("sqlmesh.Context", return_value=run_ctx), caplog.at_level("INFO"):
        tasks["dwh.orders"].python_callable(
            data_interval_start=datetime(2024, 1, 1, 0),
            data_interval_end=datetime(2024, 1, 1, 1),
        )

    assert "Model dwh.orders [INCREMENTAL_BY_TIME_RANGE]" in caplog.text
    assert "reads models : dwh.stg_orders" in caplog.text
    assert "read by      : dwh.orders_daily" in caplog.text
