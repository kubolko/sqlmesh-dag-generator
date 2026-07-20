"""
Tests for Airflow 2 / 3 compatibility shims.
"""
from unittest.mock import MagicMock, patch

import pytest


class TestDagScheduleKwargs:
    def test_returns_schedule_not_schedule_interval(self):
        from sqlmesh_dag_generator.airflow_compat import dag_schedule_kwargs

        kwargs = dag_schedule_kwargs("0 * * * *")
        assert kwargs == {"schedule": "0 * * * *"}
        assert "schedule_interval" not in kwargs

    def test_none_schedule(self):
        from sqlmesh_dag_generator.airflow_compat import dag_schedule_kwargs

        assert dag_schedule_kwargs(None) == {"schedule": None}


class TestIsAirflow3:
    def test_detects_major_version(self):
        import airflow
        from sqlmesh_dag_generator.airflow_compat import is_airflow_3

        major = str(getattr(airflow, "__version__", "0")).split(".", 1)[0]
        assert is_airflow_3() is (major == "3")


class TestCompatExports:
    def test_operators_importable(self):
        from sqlmesh_dag_generator.airflow_compat import (
            BashOperator,
            EmptyOperator,
            PythonOperator,
        )

        assert PythonOperator is not None
        assert EmptyOperator is not None
        assert BashOperator is not None

    def test_basehook_and_variable_importable(self):
        from sqlmesh_dag_generator.airflow_compat import BaseHook, Variable

        assert BaseHook is not None
        assert Variable is not None

    def test_package_root_reexports(self):
        from sqlmesh_dag_generator import (
            BaseHook,
            EmptyOperator,
            PythonOperator,
            Variable,
            dag_schedule_kwargs,
        )

        assert callable(dag_schedule_kwargs)
        assert BaseHook is not None
        assert PythonOperator is not None
        assert EmptyOperator is not None
        assert Variable is not None


class TestDagBuilderEmitsSchedule:
    def _builder(self, **airflow_overrides):
        from sqlmesh_dag_generator.config import (
            AirflowConfig,
            DAGGeneratorConfig,
            SQLMeshConfig,
        )
        from sqlmesh_dag_generator.dag_builder import AirflowDAGBuilder
        from sqlmesh_dag_generator.models import DAGStructure

        schedule = airflow_overrides.pop("schedule_interval", "0 * * * *")
        airflow = AirflowConfig(
            dag_id="test_sqlmesh",
            schedule_interval=schedule,
            **airflow_overrides,
        )
        config = DAGGeneratorConfig(
            sqlmesh=SQLMeshConfig(project_path="/tmp/sqlmesh"),
            airflow=airflow,
        )
        structure = DAGStructure(dag_id="test_sqlmesh", models={})
        return AirflowDAGBuilder(config, structure)

    def test_static_dag_uses_schedule_kwarg(self):
        builder = self._builder(schedule_interval="0 * * * *")
        body = builder._build_dag_definition()
        assert "schedule=" in body
        assert "schedule_interval=" not in body

    def test_static_imports_use_compat(self):
        builder = self._builder()
        builder.config.generation.operator_type = "python"
        builder.config.generation.include_source_tables = True
        imports = builder._build_imports()
        assert "sqlmesh_dag_generator.airflow_compat" in imports
        assert "PythonOperator" in imports
        assert "EmptyOperator" in imports
        assert "from airflow.operators.python import" not in imports

    def test_dynamic_imports_use_compat(self):
        builder = self._builder()
        imports = builder._build_dynamic_imports()
        assert "sqlmesh_dag_generator.airflow_compat" in imports
        assert "Variable" in imports
        assert "from airflow.models import Variable" not in imports
        assert "from airflow.operators.python import" not in imports
