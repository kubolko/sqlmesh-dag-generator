"""
Tests for configuration module
"""
import pytest
import tempfile
from pathlib import Path

from sqlmesh_dag_generator.config import (
    SQLMeshConfig,
    AirflowConfig,
    GenerationConfig,
    DAGGeneratorConfig,
)


def test_sqlmesh_config_creation():
    """Test SQLMeshConfig creation"""
    config = SQLMeshConfig(
        project_path="/test/path",
        environment="dev",
        gateway="test_gateway",
    )

    assert config.project_path == "/test/path"
    assert config.environment == "dev"
    assert config.gateway == "test_gateway"


def test_airflow_config_creation():
    """Test AirflowConfig creation"""
    config = AirflowConfig(
        dag_id="test_dag",
        schedule_interval="0 0 * * *",
        tags=["test"],
    )

    assert config.dag_id == "test_dag"
    assert config.schedule_interval == "0 0 * * *"
    assert "test" in config.tags


def test_generation_config_defaults():
    """Test GenerationConfig default values"""
    config = GenerationConfig()

    assert config.output_dir == "./dags"
    assert config.operator_type == "python"
    assert config.include_tests is False
    assert config.parallel_tasks is True


def test_dag_generator_config_from_dict():
    """Test creating config from dictionary"""
    config_dict = {
        "sqlmesh": {
            "project_path": "/test",
            "environment": "prod",
        },
        "airflow": {
            "dag_id": "test_dag",
            "schedule_interval": "@daily",
        },
        "generation": {
            "output_dir": "./output",
        },
    }

    config = DAGGeneratorConfig.from_dict(config_dict)

    assert config.sqlmesh.project_path == "/test"
    assert config.airflow.dag_id == "test_dag"
    assert config.generation.output_dir == "./output"


def test_dag_generator_config_to_dict():
    """Test converting config to dictionary"""
    config = DAGGeneratorConfig(
        sqlmesh=SQLMeshConfig(project_path="/test"),
        airflow=AirflowConfig(dag_id="test_dag"),
    )

    config_dict = config.to_dict()

    assert config_dict["sqlmesh"]["project_path"] == "/test"
    assert config_dict["airflow"]["dag_id"] == "test_dag"


def test_dag_generator_config_save_load():
    """Test saving and loading configuration"""
    config = DAGGeneratorConfig(
        sqlmesh=SQLMeshConfig(project_path="/test", environment="dev"),
        airflow=AirflowConfig(dag_id="test_dag", schedule_interval="@daily"),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test_config.yaml"

        # Save
        config.save(str(config_file))
        assert config_file.exists()

        # Load
        loaded_config = DAGGeneratorConfig.from_file(str(config_file))
        assert loaded_config.sqlmesh.project_path == "/test"
        assert loaded_config.airflow.dag_id == "test_dag"

