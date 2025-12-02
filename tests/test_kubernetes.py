"""
Tests for Kubernetes operator support

Tests the Kubernetes operator generation including:
- Configuration validation
- KubernetesPodOperator task generation
- Docker image requirement
- Environment variable injection
- Proper imports
"""

import pytest
import ast
import tempfile
import shutil
from pathlib import Path
from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig


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


class TestKubernetesOperator:
    """Test suite for Kubernetes operator functionality"""

    def test_kubernetes_requires_docker_image(self, demo_sqlmesh_project):
        """Test that kubernetes operator requires docker_image in config"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_k8s"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                # Missing docker_image - should raise error
            }
        })

        generator = SQLMeshDAGGenerator(config=config)

        # Should raise ValueError when generating DAG without docker_image
        with pytest.raises(ValueError, match="docker_image is required"):
            generator.generate_dag()

    def test_kubernetes_dag_generation_with_image(self, demo_sqlmesh_project):
        """Test successful kubernetes DAG generation with docker_image"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_k8s"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
                "namespace": "data-pipelines"
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Verify DAG code was generated
        assert isinstance(dag_code, str)
        assert len(dag_code) > 0

        # Verify Kubernetes-specific imports
        assert "from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator" in dag_code
        assert "from kubernetes.client.models import V1EnvVar" in dag_code

        # Verify docker image is used
        assert 'image="my-sqlmesh:v1.0"' in dag_code

        # Verify namespace is used
        assert 'namespace="data-pipelines"' in dag_code

        # Verify KubernetesPodOperator is used (not PythonOperator)
        assert "KubernetesPodOperator" in dag_code
        assert "PythonOperator" not in dag_code

    def test_kubernetes_default_namespace(self, demo_sqlmesh_project):
        """Test that namespace defaults to 'default' if not specified"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_k8s"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
                # namespace not specified
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Should use default namespace
        assert 'namespace="default"' in dag_code

    def test_kubernetes_dag_syntax_valid(self, demo_sqlmesh_project):
        """Test that generated Kubernetes DAG has valid Python syntax"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_k8s"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Should parse without syntax errors
        try:
            ast.parse(dag_code)
        except SyntaxError as e:
            pytest.fail(f"Generated Kubernetes DAG has syntax error: {e}")

    def test_kubernetes_environment_variables(self, demo_sqlmesh_project):
        """Test that environment variables are properly injected in K8s tasks"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {
                "dag_id": "test_k8s",
                "env_vars": {
                    "SNOWFLAKE_ACCOUNT": "{{ var.value.snowflake_account }}",
                    "DB_HOST": "prod-db.example.com"
                }
            },
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Should include custom environment variables
        assert "SNOWFLAKE_ACCOUNT" in dag_code
        assert "DB_HOST" in dag_code
        assert "prod-db.example.com" in dag_code

        # Should also include default SQLMesh env vars
        assert "SQLMESH_PROJECT_PATH" in dag_code
        assert "SQLMESH_ENVIRONMENT" in dag_code

    def test_kubernetes_task_arguments(self, demo_sqlmesh_project):
        """Test that Kubernetes tasks have proper sqlmesh command arguments"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_k8s"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Should use sqlmesh CLI
        assert 'cmds=["sqlmesh"]' in dag_code

        # Should pass proper arguments
        assert '"run"' in dag_code
        assert '"--select-models"' in dag_code

        # Should use data_interval for time range
        assert "data_interval_start" in dag_code
        assert "data_interval_end" in dag_code

    def test_kubernetes_pod_cleanup(self, demo_sqlmesh_project):
        """Test that Kubernetes pods are configured to be deleted after execution"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_k8s"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Should enable pod deletion and log retrieval
        assert "is_delete_operator_pod=True" in dag_code
        assert "get_logs=True" in dag_code

    def test_invalid_operator_type_raises_error(self, demo_sqlmesh_project):
        """Test that invalid operator type raises clear error"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_invalid"},
            "generation": {
                "mode": "static",
                "operator_type": "invalid_operator",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)

        # Should raise ValueError with helpful message
        with pytest.raises(ValueError, match="Unsupported operator_type"):
            generator.generate_dag()

    def test_kubernetes_with_gateway(self, demo_sqlmesh_project):
        """Test Kubernetes operator with SQLMesh gateway configuration"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {
                "project_path": demo_sqlmesh_project,
                "gateway": "local"  # Use existing gateway from demo project
            },
            "airflow": {"dag_id": "test_k8s"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Should include gateway in environment variables
        assert "SQLMESH_GATEWAY" in dag_code
        assert "local" in dag_code

    def test_kubernetes_multiple_tasks(self, demo_sqlmesh_project):
        """Test that multiple models generate multiple K8s pods"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_k8s_multi"},
            "generation": {
                "mode": "static",
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dag()

        # Should have multiple KubernetesPodOperator instances
        # (one per model in the demo project - we have 3 models)
        k8s_operator_count = dag_code.count("KubernetesPodOperator(")
        assert k8s_operator_count == 3  # 3 models in demo project


class TestKubernetesConfiguration:
    """Test Kubernetes-specific configuration fields"""

    def test_docker_image_field_exists(self):
        """Test that docker_image field exists in GenerationConfig"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": "/path/to/project"},
            "airflow": {"dag_id": "test"},
            "generation": {
                "docker_image": "my-image:v1.0",
                "namespace": "my-namespace"
            }
        })

        assert config.generation.docker_image == "my-image:v1.0"
        assert config.generation.namespace == "my-namespace"

    def test_namespace_defaults_to_default(self):
        """Test that namespace defaults to 'default'"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": "/path/to/project"},
            "airflow": {"dag_id": "test"},
            "generation": {}
        })

        assert config.generation.namespace == "default"

    def test_docker_image_defaults_to_none(self):
        """Test that docker_image defaults to None"""
        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": "/path/to/project"},
            "airflow": {"dag_id": "test"},
            "generation": {}
        })

        assert config.generation.docker_image is None


class TestDynamicModeKubernetesLimitation:
    """Test that dynamic mode with kubernetes is properly handled"""

    def test_dynamic_mode_kubernetes_not_yet_supported(self, demo_sqlmesh_project):
        """Test that dynamic mode currently only supports Python operator"""
        # Note: This documents current limitation
        # When we implement kubernetes in dynamic mode, this test should be updated

        config = DAGGeneratorConfig.from_dict({
            "sqlmesh": {"project_path": demo_sqlmesh_project},
            "airflow": {"dag_id": "test_dynamic_k8s"},
            "generation": {
                "mode": "dynamic",  # Dynamic mode
                "operator_type": "kubernetes",
                "docker_image": "my-sqlmesh:v1.0",
            }
        })

        generator = SQLMeshDAGGenerator(config=config)
        dag_code = generator.generate_dynamic_dag()

        # Dynamic mode currently hardcodes PythonOperator
        # This is documented limitation - will be fixed in v0.3.0
        assert "PythonOperator" in dag_code
        # Kubernetes imports should not be present in dynamic mode yet
        assert "KubernetesPodOperator" not in dag_code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

