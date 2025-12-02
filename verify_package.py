#!/usr/bin/env python3
"""
Verification script to test that the SQLMesh DAG Generator package works correctly.
"""
import sys
import traceback

def test_imports():
    """Test that all package imports work"""
    print("Testing imports...")
    try:
        from sqlmesh_dag_generator import SQLMeshDAGGenerator
        from sqlmesh_dag_generator.config import DAGGeneratorConfig
        from sqlmesh_dag_generator.models import SQLMeshModelInfo, DAGStructure
        from sqlmesh_dag_generator.dag_builder import AirflowDAGBuilder
        from sqlmesh_dag_generator import utils
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        traceback.print_exc()
        return False

def test_config():
    """Test configuration system"""
    print("\nTesting configuration system...")
    try:
        from sqlmesh_dag_generator.config import DAGGeneratorConfig

        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {
                "project_path": "/test/path",
                "environment": "dev",
            },
            "airflow": {
                "dag_id": "test_dag",
            },
        })

        assert config.sqlmesh.project_path == "/test/path"
        assert config.airflow.dag_id == "test_dag"
        print("✓ Configuration system works")
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        traceback.print_exc()
        return False

def test_models():
    """Test data models"""
    print("\nTesting data models...")
    try:
        from sqlmesh_dag_generator.models import SQLMeshModelInfo, DAGStructure

        model1 = SQLMeshModelInfo(name="test_model", dependencies=set())
        assert model1.get_task_id() == "sqlmesh_test_model"

        models = {
            "model1": SQLMeshModelInfo(name="model1", dependencies=set()),
            "model2": SQLMeshModelInfo(name="model2", dependencies={"model1"}),
        }

        dag = DAGStructure(dag_id="test", models=models)
        assert dag.validate()

        sorted_models = dag.topological_sort()
        assert sorted_models.index("model1") < sorted_models.index("model2")

        print("✓ Data models work correctly")
        return True
    except Exception as e:
        print(f"✗ Data models test failed: {e}")
        traceback.print_exc()
        return False

def test_generator_init():
    """Test generator initialization"""
    print("\nTesting generator initialization...")
    try:
        from sqlmesh_dag_generator import SQLMeshDAGGenerator

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/test/path",
            dag_id="test_dag",
            schedule_interval="0 0 * * *",
        )

        assert generator.config.sqlmesh.project_path == "/test/path"
        assert generator.config.airflow.dag_id == "test_dag"
        print("✓ Generator initialization works")
        return True
    except Exception as e:
        print(f"✗ Generator initialization failed: {e}")
        traceback.print_exc()
        return False

def test_utils():
    """Test utility functions"""
    print("\nTesting utility functions...")
    try:
        from sqlmesh_dag_generator.utils import (
            sanitize_task_id,
            parse_cron_schedule,
            estimate_dag_complexity,
        )

        assert sanitize_task_id("my.model.name") == "my_model_name"
        assert parse_cron_schedule("0 0 * * *") == "0 0 * * *"
        assert estimate_dag_complexity(5, 5) == "simple"

        print("✓ Utility functions work correctly")
        return True
    except Exception as e:
        print(f"✗ Utility test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all verification tests"""
    print("=" * 70)
    print("SQLMesh DAG Generator - Package Verification")
    print("=" * 70)

    tests = [
        test_imports,
        test_config,
        test_models,
        test_generator_init,
        test_utils,
    ]

    results = []
    for test in tests:
        results.append(test())

    print("\n" + "=" * 70)
    print("Verification Results")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"Passed: {passed}/{total}")

    if all(results):
        print("\n✅ ALL TESTS PASSED - Package is working correctly!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED - Please review errors above")
        return 1

if __name__ == "__main__":
    sys.exit(main())

