"""
Tests for SQLMeshDAGGenerator

Tests the main generator functionality including:
- DAG generation (dynamic mode - default)
- Task creation
- Model extraction
- Dependency handling
"""

import pytest
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig
from sqlmesh_dag_generator.models import SQLMeshModelInfo


@pytest.fixture
def demo_sqlmesh_project():
    """Create a temporary SQLMesh project for testing"""
    temp_dir = tempfile.mkdtemp(prefix="test_sqlmesh_")
    project_path = Path(temp_dir)

    # Create config.yaml
    config_content = """
gateways:
  local:
    connection:
      type: duckdb
      database: ':memory:'

default_gateway: local

model_defaults:
  dialect: duckdb
"""
    (project_path / "config.yaml").write_text(config_content)

    # Create models directory
    models_dir = project_path / "models"
    models_dir.mkdir()

    # Create test models
    (models_dir / "raw_users.sql").write_text("""
MODEL (
  name test_db.raw_users,
  kind FULL,
);

SELECT 1 as user_id, 'John' as name;
""")

    (models_dir / "stg_users.sql").write_text("""
MODEL (
  name test_db.stg_users,
  kind FULL,
);

SELECT * FROM test_db.raw_users;
""")

    (models_dir / "user_summary.sql").write_text("""
MODEL (
  name test_db.user_summary,
  kind FULL,
);

SELECT COUNT(*) as user_count FROM test_db.stg_users;
""")

    yield str(project_path)

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestSQLMeshDAGGenerator:
    """Test suite for SQLMeshDAGGenerator"""

    def test_initialization_simple(self):
        """Test simple initialization"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/path/to/project",
            dag_id="test_dag"
        )
        assert generator.config.airflow.dag_id == "test_dag"
        assert generator.config.generation.mode == "dynamic"  # Default

    def test_initialization_with_config(self):
        """Test initialization with config object"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": "/path/to/project"},
            "airflow": {"dag_id": "my_dag"},
            "generation": {"mode": "dynamic"}
        })
        generator = SQLMeshDAGGenerator(config=config)
        assert generator.config.airflow.dag_id == "my_dag"

    def test_extract_models(self, demo_sqlmesh_project):
        """Test model extraction from SQLMesh project"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        models = generator.extract_models()

        assert len(models) == 3
        # Model names include database prefix from SQLMesh
        model_names = list(models.keys())
        assert any("raw_users" in name for name in model_names)
        assert any("stg_users" in name for name in model_names)
        assert any("user_summary" in name for name in model_names)

    def test_model_dependencies(self, demo_sqlmesh_project):
        """Test that dependencies are correctly extracted"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        models = generator.extract_models()
        model_names = list(models.keys())

        # Find the models (names include database prefix)
        raw_users = [n for n in model_names if "raw_users" in n][0]
        stg_users = [n for n in model_names if "stg_users" in n][0]
        user_summary = [n for n in model_names if "user_summary" in n][0]

        # raw_users has no dependencies
        assert len(models[raw_users].dependencies) == 0

        # stg_users depends on raw_users
        assert any("raw_users" in dep for dep in models[stg_users].dependencies)

        # user_summary depends on stg_users
        assert any("stg_users" in dep for dep in models[user_summary].dependencies)

    def test_generate_dynamic_dag(self, demo_sqlmesh_project):
        """Test dynamic DAG generation"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test_dag"
        )

        dag_code = generator.generate_dynamic_dag()

        # Should generate valid Python code
        assert isinstance(dag_code, str)
        assert len(dag_code) > 0

        # Check for key components
        assert "from airflow import DAG" in dag_code
        assert "from sqlmesh import Context" in dag_code
        assert "test_dag" in dag_code

        # Check for dynamic discovery
        assert "ctx.models.items()" in dag_code or "discovered_models" in dag_code

        # Check for proper time handling
        assert "data_interval_start" in dag_code
        assert "data_interval_end" in dag_code

    def test_generated_dag_syntax(self, demo_sqlmesh_project):
        """Test that generated DAG has valid Python syntax"""
        import ast

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test_dag"
        )

        dag_code = generator.generate_dynamic_dag()

        # Should parse without syntax errors
        try:
            ast.parse(dag_code)
        except SyntaxError as e:
            pytest.fail(f"Generated DAG has syntax error: {e}")

    def test_create_tasks_in_dag_returns_tasks(self, demo_sqlmesh_project):
        """Test that create_tasks_in_dag returns task dict"""
        from airflow import DAG
        from datetime import datetime

        with DAG("test", start_date=datetime(2024, 1, 1)) as dag:
            generator = SQLMeshDAGGenerator(
                sqlmesh_project_path=demo_sqlmesh_project,
                dag_id="test"
            )

            tasks = generator.create_tasks_in_dag(dag)

            # Should return dictionary of tasks
            assert isinstance(tasks, dict)
            assert len(tasks) == 3  # 3 models

            # All values should be Airflow operators
            for task in tasks.values():
                assert hasattr(task, 'task_id')
                assert hasattr(task, 'python_callable')

    def test_static_dag_generation(self, demo_sqlmesh_project):
        """Test static DAG generation (alternative mode)"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_static"},
            "generation": {"mode": "static"}
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()  # Use generate_dag for static

        # Should generate valid code
        assert isinstance(dag_code, str)
        assert len(dag_code) > 0
        assert "test_static" in dag_code

        # Static mode should have pre-defined tasks
        assert "PythonOperator" in dag_code

    def test_dag_structure_building(self, demo_sqlmesh_project):
        """Test DAG structure is built correctly"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        generator.extract_models()
        dag_structure = generator.build_dag_structure()

        # Should identify root and leaf models
        root_models = dag_structure.get_root_models()
        leaf_models = dag_structure.get_leaf_models()

        # raw_users should be root (no dependencies)
        assert any("raw_users" in model for model in root_models)

        # user_summary should be leaf (no dependents)
        assert any("user_summary" in model for model in leaf_models)

    def test_validation(self, demo_sqlmesh_project):
        """Test validation method"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        # Should validate successfully
        is_valid = generator.validate()
        assert is_valid is True

    def test_invalid_project_path(self):
        """Test behavior with invalid project path"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/nonexistent/path",
            dag_id="test"
        )

        # Validation should fail
        is_valid = generator.validate()
        assert is_valid is False

    def test_configuration_from_dict(self):
        """Test configuration from dictionary"""
        config_dict = {
            "sqlmesh": {
                "project_path": "/path/to/project",
                "environment": "prod"
            },
            "airflow": {
                "dag_id": "my_dag",
                "schedule_interval": "@daily",
                "tags": ["sqlmesh", "test"],
                "recovery": {
                    "mode": "warn",
                    "max_intervals": 4,
                    "fail_on_excess_gap": True,
                }
            },
            "generation": {
                "mode": "dynamic",
                "output_dir": "./dags"
            }
        }

        config = DAGGeneratorConfig.from_dict(config_dict)
        generator = SQLMeshDAGGenerator(config=config)

        assert generator.config.sqlmesh.environment == "prod"
        assert generator.config.airflow.dag_id == "my_dag"
        assert generator.config.airflow.schedule_interval == "@daily"
        assert "sqlmesh" in generator.config.airflow.tags
        assert generator.config.airflow.recovery.mode == "warn"
        assert generator.config.airflow.recovery.max_intervals == 4
        assert generator.config.airflow.recovery.fail_on_excess_gap is True

    def test_create_tasks_in_dag_adds_recovery_tasks_for_subhourly_incremental_models(self):
        """Test opt-in recovery helper tasks are added for sub-hourly incremental projects."""
        from airflow import DAG

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="test",
            recovery_mode="bounded_auto",
        )
        generator.models = {
            "dwh.raw_5m": SQLMeshModelInfo(
                name="dwh.raw_5m",
                dependencies=set(),
                interval_unit="FIVE_MINUTE",
                kind="INCREMENTAL_BY_TIME_RANGE",
            ),
            "dwh.report": SQLMeshModelInfo(
                name="dwh.report",
                dependencies={"dwh.raw_5m"},
                interval_unit="HOUR",
                kind="FULL",
            ),
        }

        with DAG("test", start_date=datetime(2024, 1, 1)) as dag:
            tasks = generator.create_tasks_in_dag(dag)

        assert "sqlmesh_integrity_guard" in tasks
        assert "sqlmesh_recovery_backfill" in tasks
        assert "sqlmesh_recovery_backfill" in tasks["dwh.raw_5m"].upstream_task_ids

    @patch("sqlmesh_dag_generator.generator.Context")
    def test_bounded_recovery_replays_full_missing_window(self, mock_context):
        """Test bounded recovery replays from the previous successful interval boundary."""
        from airflow import DAG

        run_ctx = MagicMock()
        run_result = MagicMock()
        run_result.name = "SUCCESS"
        run_ctx.run.return_value = run_result
        mock_context.return_value = run_ctx

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="test",
            recovery_mode="bounded_auto",
        )
        generator.models = {
            "dwh.raw_5m": SQLMeshModelInfo(
                name="dwh.raw_5m",
                dependencies=set(),
                interval_unit="FIVE_MINUTE",
                kind="INCREMENTAL_BY_TIME_RANGE",
            ),
        }

        with DAG("test", start_date=datetime(2024, 1, 1)) as dag:
            tasks = generator.create_tasks_in_dag(dag)

        guard_task = tasks["sqlmesh_integrity_guard"]
        recovery_task = tasks["sqlmesh_recovery_backfill"]

        prev_end = datetime(2024, 1, 1, 0, 0)
        current_start = datetime(2024, 1, 1, 0, 15)
        gap_payload = guard_task.python_callable(
            prev_data_interval_end_success=prev_end,
            data_interval_start=current_start,
        )

        assert gap_payload["gap_intervals"] == 3
        assert gap_payload["recovery_start"] == prev_end.isoformat()
        assert gap_payload["recovery_end"] == current_start.isoformat()

        task_instance = MagicMock()
        task_instance.xcom_pull.return_value = gap_payload
        recovery_result = recovery_task.python_callable(ti=task_instance)

        run_ctx.run.assert_called_once()
        _, run_kwargs = run_ctx.run.call_args
        assert run_kwargs["start"] == prev_end
        assert run_kwargs["end"] == current_start
        assert run_kwargs["select_models"] == ["dwh.raw_5m"]
        assert recovery_result["gap_intervals"] == 3

    @patch("sqlmesh_dag_generator.generator.Context")
    def test_create_manual_backfill_task_uses_defaults_and_conf_overrides(self, mock_context):
        """Test manual backfill task supports default windows and dag_run.conf overrides."""
        from airflow import DAG

        run_ctx = MagicMock()
        run_result = MagicMock()
        run_result.name = "SUCCESS"
        run_ctx.run.return_value = run_result
        mock_context.return_value = run_ctx

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="test",
        )
        generator.load_sqlmesh_context = MagicMock(return_value=run_ctx)
        generator.models = {
            "dwh.raw_5m": SQLMeshModelInfo(
                name="dwh.raw_5m",
                dependencies=set(),
                interval_unit="FIVE_MINUTE",
                kind="INCREMENTAL_BY_TIME_RANGE",
            ),
            "dwh.report": SQLMeshModelInfo(
                name="dwh.report",
                dependencies={"dwh.raw_5m"},
                interval_unit="HOUR",
                kind="FULL",
            ),
        }

        with DAG("test", start_date=datetime(2024, 1, 1)) as dag:
            task = generator.create_manual_backfill_task(
                dag,
                default_start="2024-01-01T00:00:00",
            )

        dag_run = MagicMock()
        dag_run.conf = {
            "end": "2024-01-01T02:00:00",
            "models": ["dwh.raw_5m"],
        }
        result = task.python_callable(dag_run=dag_run)

        run_ctx.run.assert_called_once()
        _, run_kwargs = run_ctx.run.call_args
        assert run_kwargs["start"].isoformat() == "2024-01-01T00:00:00+00:00"
        assert run_kwargs["end"].isoformat() == "2024-01-01T02:00:00+00:00"
        assert run_kwargs["select_models"] == ["dwh.raw_5m"]
        assert result["status"] == "SUCCESS"
        assert result["models"] == ["dwh.raw_5m"]

    def test_create_manual_backfill_task_rejects_unknown_models(self):
        """Test manual backfill task validates requested model names."""
        from airflow import DAG
        from airflow.exceptions import AirflowException

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/tmp/project",
            dag_id="test",
        )
        generator.load_sqlmesh_context = MagicMock()
        generator.models = {
            "dwh.raw_5m": SQLMeshModelInfo(
                name="dwh.raw_5m",
                dependencies=set(),
                interval_unit="FIVE_MINUTE",
                kind="INCREMENTAL_BY_TIME_RANGE",
            ),
        }

        with DAG("test", start_date=datetime(2024, 1, 1)) as dag:
            task = generator.create_manual_backfill_task(
                dag,
                default_start="2024-01-01T00:00:00",
            )

        dag_run = MagicMock()
        dag_run.conf = {
            "end": "2024-01-01T02:00:00",
            "models": ["dwh.missing"],
        }

        with pytest.raises(AirflowException, match="Unknown SQLMesh models"):
            task.python_callable(dag_run=dag_run)


class TestDynamicFeatures:
    """Test dynamic DAG specific features"""

    def test_airflow_variables_in_dynamic_dag(self, demo_sqlmesh_project):
        """Test that dynamic DAG uses Airflow Variables"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        dag_code = generator.generate_dynamic_dag()

        # Should use Airflow Variables
        assert "Variable.get" in dag_code
        assert "sqlmesh_project_path" in dag_code

    def test_runtime_discovery_in_dynamic_dag(self, demo_sqlmesh_project):
        """Test that dynamic DAG discovers models at runtime"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        dag_code = generator.generate_dynamic_dag()

        # Should have model discovery logic
        assert "ctx.models.items()" in dag_code
        assert "discovered_models" in dag_code

    def test_dynamic_dag_includes_recovery_controls(self, demo_sqlmesh_project):
        """Test that generated dynamic DAGs include recovery configuration and helper tasks."""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test",
            recovery_mode="bounded_auto",
            recovery_max_intervals=8,
        )

        dag_code = generator.generate_dynamic_dag()

        assert "RECOVERY_MODE" in dag_code
        assert "RECOVERY_MAX_INTERVALS" in dag_code
        assert "sqlmesh_integrity_guard" in dag_code
        assert "sqlmesh_recovery_backfill" in dag_code

    def test_error_handling_in_dynamic_dag(self, demo_sqlmesh_project):
        """Test that dynamic DAG has proper error handling"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        dag_code = generator.generate_dynamic_dag()

        # Should have error handling
        assert "try:" in dag_code
        assert "except" in dag_code
        assert "SQLMeshError" in dag_code or "Exception" in dag_code


class TestIncrementalHandling:
    """Test proper incremental model handling"""

    def test_data_interval_usage(self, demo_sqlmesh_project):
        """Test that generated code uses data_interval_start/end"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        dag_code = generator.generate_dynamic_dag()

        # Should use data_interval for proper incremental handling
        assert "data_interval_start" in dag_code
        assert "data_interval_end" in dag_code

        # Should have fallback for backward compatibility
        assert "execution_date" in dag_code

    def test_time_range_in_sqlmesh_run(self, demo_sqlmesh_project):
        """Test that SQLMesh run uses start and end parameters"""
        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=demo_sqlmesh_project,
            dag_id="test"
        )

        dag_code = generator.generate_dynamic_dag()

        # Should pass start and end to ctx.run()
        assert "start=start" in dag_code or "start=" in dag_code
        assert "end=end" in dag_code or "end=" in dag_code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

