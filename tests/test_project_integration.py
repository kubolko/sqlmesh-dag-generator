"""
End-to-end checks against a real (tiny) SQLMesh project.

These load an actual SQLMesh Context backed by in-memory DuckDB, so they catch
the things mocks never do: how SQLMesh spells model kinds, where it keeps the
model file path, what ``depends_on`` contains.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig
from sqlmesh_dag_generator.manifest import build_manifest, diff_manifests

CONFIG_YAML = """
gateways:
  local:
    connection:
      type: duckdb
      database: ':memory:'
default_gateway: local
model_defaults:
  dialect: duckdb
  start: 2024-01-01
"""

RAW_ORDERS = """
MODEL (
  name demo.raw_orders,
  kind FULL,
  owner 'data_eng',
  tags (bronze, finance),
  cron '@daily',
  cron_tz 'Europe/Warsaw',
  description 'Raw orders landing table'
);

SELECT 1 AS id, 10.0 AS amount, CAST('2024-01-01' AS DATE) AS ds
"""

STG_ORDERS = """
MODEL (
  name demo.stg_orders,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column ds
  ),
  owner 'analytics',
  tags (silver, finance),
  cron '@hourly',
  audits (
    not_null(columns := (id))
  )
);

SELECT id, amount, ds FROM demo.raw_orders WHERE ds BETWEEN @start_ds AND @end_ds
"""

MARKETING_DAILY = """
MODEL (
  name demo.marketing_daily,
  kind FULL,
  owner 'marketing',
  tags (gold, marketing),
  cron '@daily'
);

SELECT ds, COUNT(*) AS orders FROM demo.stg_orders GROUP BY ds
"""


@pytest.fixture(scope="module")
def project():
    path = Path(tempfile.mkdtemp(prefix="sqlmesh_selection_"))
    (path / "config.yaml").write_text(CONFIG_YAML)
    (path / "models").mkdir()
    (path / "models" / "raw_orders.sql").write_text(RAW_ORDERS)
    (path / "models" / "stg_orders.sql").write_text(STG_ORDERS)
    (path / "models" / "marts").mkdir()
    (path / "models" / "marts" / "marketing_daily.sql").write_text(MARKETING_DAILY)
    yield str(path)
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="module")
def generator(project):
    generator = SQLMeshDAGGenerator(sqlmesh_project_path=project, dag_id="demo")
    generator.extract_models()
    return generator


def _by_name(generator, name):
    return next(i for i in generator.models.values() if i.display_name == name)


def test_metadata_is_extracted_from_real_models(generator):
    raw = _by_name(generator, "demo.raw_orders")
    stg = _by_name(generator, "demo.stg_orders")

    assert raw.cron_tz == "Europe/Warsaw"
    assert raw.description == "Raw orders landing table"
    assert raw.path == "models/raw_orders.sql"
    assert sorted(raw.tags) == ["bronze", "finance"]

    assert stg.audits == ["not_null"]
    assert stg.path == "models/stg_orders.sql"
    assert stg.is_incremental()


def test_selection_against_a_real_project(project):
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=project,
        dag_id="demo_finance",
        select=["tag:finance+"],
        exclude=["tag:marketing"],
    )
    generator.extract_models()

    assert sorted(i.display_name for i in generator.models.values()) == [
        "demo.raw_orders",
        "demo.stg_orders",
    ]


def test_path_selection_against_a_real_project(project):
    generator = SQLMeshDAGGenerator(
        sqlmesh_project_path=project,
        dag_id="demo_marts",
        select=["path:models/marts"],
    )
    generator.extract_models()

    assert [i.display_name for i in generator.models.values()] == ["demo.marketing_daily"]


def test_dag_groups_over_a_real_project(project):
    config = DAGGeneratorConfig.from_dict(
        {
            "sqlmesh": {"project_path": project},
            "airflow": {"dag_id": "demo", "start_date": "2024-01-01"},
            "generation": {"auto_replan_on_change": False},
            "dag_groups": [
                {"dag_id": "demo_core", "select": ["tag:finance"], "schedule": "@hourly"},
                {"dag_id": "demo_marketing", "select": ["tag:marketing"]},
            ],
        }
    )
    from sqlmesh_dag_generator.dag_groups import build_dag_groups

    dags = build_dag_groups(config)

    assert sorted(dags) == ["demo_core", "demo_marketing"]
    assert "sqlmesh_memory_demo_stg_orders" in dags["demo_core"].task_dict
    assert "sqlmesh_memory_demo_marketing_daily" in dags["demo_marketing"].task_dict

    # A model owned by another group is not a raw source table, so it must not
    # get a placeholder "source__" task in the consuming DAG.
    assert not [t for t in dags["demo_marketing"].task_dict if t.startswith("source__")]


def test_manifest_round_trip_and_diff(generator):
    manifest = build_manifest(generator)

    assert manifest["schedule"] == "@hourly"  # shortest model interval in the project
    entry = manifest["models"]["demo.stg_orders"]
    assert entry["task_id"] == "sqlmesh_memory_demo_stg_orders"
    assert entry["dataset_uri"] == "sqlmesh://models/demo.stg_orders"
    assert entry["depends_on"] == ["memory.demo.raw_orders"]

    changed = {**manifest, "models": dict(manifest["models"])}
    changed["models"]["demo.stg_orders"] = {**entry, "cron": "*/15 * * * *"}
    changed["models"].pop("demo.marketing_daily")
    changed["models"]["demo.new_model"] = {"task_id": "sqlmesh_new"}

    assert diff_manifests(manifest, changed) == {
        "added": ["demo.new_model"],
        "removed": ["demo.marketing_daily"],
        "changed": ["demo.stg_orders"],
    }
