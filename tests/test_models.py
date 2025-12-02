"""
Tests for models module
"""
import pytest
from sqlmesh_dag_generator.models import SQLMeshModelInfo, DAGStructure
from sqlmesh_dag_generator.config import DAGGeneratorConfig, SQLMeshConfig, AirflowConfig


def test_sqlmesh_model_info_task_id():
    """Test task ID generation"""
    model = SQLMeshModelInfo(
        name="schema.my_model",
        dependencies=set(),
    )

    task_id = model.get_task_id()
    assert task_id == "sqlmesh_schema_my_model"


def test_sqlmesh_model_info_is_incremental():
    """Test incremental model detection"""
    full_model = SQLMeshModelInfo(name="test", kind="FULL")
    incremental_model = SQLMeshModelInfo(name="test", kind="INCREMENTAL_BY_TIME")

    assert not full_model.is_incremental()
    assert incremental_model.is_incremental()


def test_dag_structure_root_models():
    """Test finding root models (no dependencies)"""
    models = {
        "model1": SQLMeshModelInfo(name="model1", dependencies=set()),
        "model2": SQLMeshModelInfo(name="model2", dependencies={"model1"}),
        "model3": SQLMeshModelInfo(name="model3", dependencies=set()),
    }

    dag = DAGStructure(dag_id="test", models=models)
    roots = dag.get_root_models()

    assert "model1" in roots
    assert "model3" in roots
    assert "model2" not in roots


def test_dag_structure_leaf_models():
    """Test finding leaf models (no dependents)"""
    models = {
        "model1": SQLMeshModelInfo(name="model1", dependencies=set()),
        "model2": SQLMeshModelInfo(name="model2", dependencies={"model1"}),
        "model3": SQLMeshModelInfo(name="model3", dependencies={"model2"}),
    }

    dag = DAGStructure(dag_id="test", models=models)
    leaves = dag.get_leaf_models()

    assert "model3" in leaves
    assert "model1" not in leaves
    assert "model2" not in leaves


def test_dag_structure_topological_sort():
    """Test topological sorting of models"""
    models = {
        "model1": SQLMeshModelInfo(name="model1", dependencies=set()),
        "model2": SQLMeshModelInfo(name="model2", dependencies={"model1"}),
        "model3": SQLMeshModelInfo(name="model3", dependencies={"model1", "model2"}),
    }

    dag = DAGStructure(dag_id="test", models=models)
    sorted_models = dag.topological_sort()

    # model1 should come before model2 and model3
    assert sorted_models.index("model1") < sorted_models.index("model2")
    assert sorted_models.index("model1") < sorted_models.index("model3")
    assert sorted_models.index("model2") < sorted_models.index("model3")


def test_dag_structure_circular_dependency_detection():
    """Test circular dependency detection"""
    models = {
        "model1": SQLMeshModelInfo(name="model1", dependencies={"model2"}),
        "model2": SQLMeshModelInfo(name="model2", dependencies={"model1"}),
    }

    dag = DAGStructure(dag_id="test", models=models)

    with pytest.raises(ValueError, match="Circular dependency"):
        dag.topological_sort()


def test_dag_structure_validate_missing_dependency():
    """Test validation catches missing dependencies"""
    models = {
        "model1": SQLMeshModelInfo(name="model1", dependencies={"missing_model"}),
    }

    dag = DAGStructure(dag_id="test", models=models)

    with pytest.raises(ValueError, match="does not exist"):
        dag.validate()


def test_dag_structure_validate_success():
    """Test successful validation"""
    models = {
        "model1": SQLMeshModelInfo(name="model1", dependencies=set()),
        "model2": SQLMeshModelInfo(name="model2", dependencies={"model1"}),
    }

    dag = DAGStructure(dag_id="test", models=models)

    assert dag.validate() is True

