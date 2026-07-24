"""Tests for per-model DAG trigger resolution."""

from sqlmesh_dag_generator.config import GenerationConfig, DAGGeneratorConfig
from sqlmesh_dag_generator.triggers import (
    ModelTriggerConfig,
    default_trigger_conf,
    normalize_model_triggers,
    parse_trigger_from_tags,
    resolve_model_trigger,
    trigger_task_id,
)


def test_parse_trigger_from_tags_basic():
    cfg = parse_trigger_from_tags(
        ["rt", "flink", "trigger_dag:etl_rt_fraud_da_unload"]
    )
    assert cfg is not None
    assert cfg.dag_id == "etl_rt_fraud_da_unload"
    assert cfg.conf == {}


def test_parse_trigger_conf_tags():
    cfg = parse_trigger_from_tags(
        [
            "trigger_dag:etl_rt_fraud_da_unload",
            "trigger_conf:source=sqlmesh",
            "trigger_conf:bucket=stg-carrier-quality-rt-alerts",
        ]
    )
    assert cfg is not None
    assert cfg.dag_id == "etl_rt_fraud_da_unload"
    assert cfg.conf["source"] == "sqlmesh"
    assert cfg.conf["bucket"] == "stg-carrier-quality-rt-alerts"


def test_parse_no_trigger_tag():
    assert parse_trigger_from_tags(["rt", "fraud"]) is None
    assert parse_trigger_from_tags(None) is None


def test_explicit_config_wins_over_tags():
    cfg = resolve_model_trigger(
        "dwh.rt_fraud_da_set",
        tags=["trigger_dag:from_tag"],
        model_triggers={
            "dwh.rt_fraud_da_set": {
                "dag_id": "from_config",
                "conf": {"x": 1},
            }
        },
    )
    assert cfg is not None
    assert cfg.dag_id == "from_config"
    assert cfg.conf == {"x": 1}


def test_tags_used_when_no_explicit():
    cfg = resolve_model_trigger(
        "dwh.rt_fraud_da_set",
        tags=["trigger_dag:from_tag"],
        model_triggers={},
    )
    assert cfg is not None
    assert cfg.dag_id == "from_tag"


def test_normalize_string_entry():
    n = normalize_model_triggers({"dwh.foo": "bar_dag"})
    assert n["dwh.foo"].dag_id == "bar_dag"


def test_generation_config_normalizes_model_triggers():
    gen = GenerationConfig(
        model_triggers={
            "dwh.rt_fraud_da_set": "etl_rt_fraud_da_unload",
        }
    )
    assert isinstance(gen.model_triggers["dwh.rt_fraud_da_set"], ModelTriggerConfig)
    assert gen.model_triggers["dwh.rt_fraud_da_set"].dag_id == "etl_rt_fraud_da_unload"


def test_from_dict_model_triggers():
    cfg = DAGGeneratorConfig.from_dict(
        {
            "sqlmesh": {"project_path": "/tmp/p"},
            "airflow": {"dag_id": "test"},
            "generation": {
                "model_triggers": {
                    "dwh.rt_fraud_da_set": {
                        "dag_id": "etl_rt_fraud_da_unload",
                        "conf": {"source": "sqlmesh"},
                    }
                }
            },
        }
    )
    mt = cfg.generation.model_triggers["dwh.rt_fraud_da_set"]
    assert mt.dag_id == "etl_rt_fraud_da_unload"
    assert mt.conf["source"] == "sqlmesh"


def test_default_trigger_conf_merges():
    conf = default_trigger_conf("dwh.rt_fraud_da_set", {"bucket": "b"})
    assert conf["source"] == "sqlmesh"
    assert conf["model"] == "dwh.rt_fraud_da_set"
    assert conf["bucket"] == "b"


def test_trigger_task_id_stable():
    a = trigger_task_id("etl_rt_fraud_da_unload", "sqlmesh_dwh_rt_fraud_da_set")
    b = trigger_task_id("etl_rt_fraud_da_unload", "sqlmesh_dwh_rt_fraud_da_set")
    assert a == b
    assert "etl_rt_fraud_da_unload" in a
