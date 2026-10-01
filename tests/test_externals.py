"""
External models (external_models.yaml): source nodes, not tasks that run nothing.
"""

from datetime import datetime
from unittest.mock import patch

from airflow import DAG

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig
from sqlmesh_dag_generator.dag_groups import plan_dag_groups
from sqlmesh_dag_generator.manifest import build_manifest
from sqlmesh_dag_generator.models import SQLMeshModelInfo
from sqlmesh_dag_generator.validation import check_external_models_layout

RAW = '"wh"."raw"."events"'
STG = '"wh"."dwh"."stg_events"'


def _models():
    return {
        RAW: SQLMeshModelInfo(
            name=RAW,
            kind="ExternalKind<>",
            interval_unit="IntervalUnit.FIVE_MINUTE",  # must not drive the schedule
            description="Events landed from Event Hub",
            columns={"event_id": "INT", "received_at": "TIMESTAMP"},
        ),
        STG: SQLMeshModelInfo(
            name=STG,
            dependencies={RAW},
            kind="IncrementalByTimeRangeKind<>",
            interval_unit="IntervalUnit.HOUR",
            tags=["finance"],
        ),
    }


def _generator(**kwargs):
    with patch("sqlmesh_dag_generator.generator.Context"):
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="ext",
            auto_replan_on_change=False,
            **kwargs,
        )
    generator.models = _models()
    return generator


def _dag(generator):
    with DAG("ext", start_date=datetime(2024, 1, 1), schedule=None) as dag:
        generator.create_tasks_in_dag(dag)
    return dag


def test_external_model_is_a_source_node_not_a_task_that_runs():
    dag = _dag(_generator())

    assert "sqlmesh_wh_raw_events" not in dag.task_dict
    source = dag.get_task("source__wh_raw_events")
    assert source.task_type == "EmptyOperator"
    assert "sqlmesh_wh_dwh_stg_events" in source.downstream_task_ids


def test_external_source_card_has_its_declared_columns():
    source = _dag(_generator()).get_task("source__wh_raw_events")

    assert source.doc_md.startswith("### `wh.raw.events` (source)")
    assert "Events landed from Event Hub" in source.doc_md
    assert "| `received_at` | `TIMESTAMP` |" in source.doc_md
    assert "create_external_models" not in source.doc_md  # it is already declared


def test_model_card_lists_the_external_as_a_source():
    stg = _dag(_generator()).get_task("sqlmesh_wh_dwh_stg_events")
    assert "- `wh.raw.events` (source)" in stg.doc_md


def test_externals_do_not_set_the_schedule():
    generator = _generator()
    assert generator.get_expected_interval_minutes() == 60
    assert generator.get_recommended_schedule() == "@hourly"


def test_manifest_reports_the_source_node_id():
    generator = _generator(task_id_prefix="snowflake")
    manifest = build_manifest(generator, include_groups=False)

    assert manifest["models"]["wh.raw.events"]["task_id"] == "snowflake__source__wh_raw_events"
    assert (
        manifest["models"]["wh.dwh.stg_events"]["task_id"] == "snowflake__sqlmesh_wh_dwh_stg_events"
    )


def test_dag_groups_neither_own_nor_wait_for_externals(caplog):
    config = DAGGeneratorConfig.from_dict(
        {
            "sqlmesh": {"project_path": "/tmp/project"},
            "airflow": {"dag_id": "ext"},
            "dag_groups": [{"dag_id": "finance", "select": ["+tag:finance"]}],
        }
    )
    with caplog.at_level("WARNING"):
        (plan,) = plan_dag_groups(config, _models())

    assert plan.external_upstreams == {}
    assert "not part of any DAG group" not in caplog.text


# -- external_models.yaml in a place SQLMesh does not read ---------------------------------


def test_misplaced_external_models_file_is_reported(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "external_models.yaml").write_text(
        "- name: raw.events\n"
        "  columns:\n"
        "    - name: event_id\n"
        "      type: INT\n"
        "- name: raw.users\n"
        "  columns:\n"
        "    user_id: INT\n"
    )

    (problem,) = check_external_models_layout(str(tmp_path))

    assert "SQLMesh ignores models/external_models.yaml" in problem
    assert "2 declaration(s) unused" in problem
    assert "1 of them list columns as name/type entries" in problem


def test_files_sqlmesh_reads_are_not_reported(tmp_path):
    (tmp_path / "external_models.yaml").write_text("- name: raw.events\n")
    (tmp_path / "external_models").mkdir()
    (tmp_path / "external_models" / "external_models.yaml").write_text("- name: raw.users\n")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "external_models.yaml").write_text("- name: cached\n")

    assert check_external_models_layout(str(tmp_path)) == []
