"""
Tests for runtime connection configuration and Airflow utilities
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlmesh_dag_generator.airflow_utils import (
    resolve_credentials,
    register_credential_resolver,
    CredentialResolver,
    _map_airflow_conn_type_to_sqlmesh,
)


class TestConnectionTypeMapping:
    """Test connection type mapping"""

    def test_postgres_mapping(self):
        assert _map_airflow_conn_type_to_sqlmesh("postgres") == "postgres"
        assert _map_airflow_conn_type_to_sqlmesh("postgresql") == "postgres"

    def test_redshift_mapping(self):
        assert _map_airflow_conn_type_to_sqlmesh("redshift") == "redshift"

    def test_mysql_mapping(self):
        assert _map_airflow_conn_type_to_sqlmesh("mysql") == "mysql"

    def test_snowflake_mapping(self):
        assert _map_airflow_conn_type_to_sqlmesh("snowflake") == "snowflake"

    def test_bigquery_mapping(self):
        assert _map_airflow_conn_type_to_sqlmesh("bigquery") == "bigquery"
        assert _map_airflow_conn_type_to_sqlmesh("google_cloud_platform") == "bigquery"

    def test_databricks_mapping(self):
        assert _map_airflow_conn_type_to_sqlmesh("databricks") == "databricks"

    def test_unknown_type(self):
        # Unknown types should be returned as-is
        assert _map_airflow_conn_type_to_sqlmesh("custom_db") == "custom_db"


class TestResolveCredentials:
    """Test the new resolve_credentials API"""

    @patch('airflow.hooks.base.BaseHook')
    def test_resolve_from_connection_object(self, mock_hook):
        """Test resolving from Airflow Connection object directly"""
        mock_conn = Mock()
        mock_conn.conn_type = "postgres"
        mock_conn.host = "localhost"
        mock_conn.port = 5432
        mock_conn.login = "user"
        mock_conn.password = "password"
        mock_conn.schema = "mydb"
        mock_conn.extra_dejson = {}

        # Pass connection object directly
        result = resolve_credentials(mock_conn)

        assert result["type"] == "postgres"
        assert result["host"] == "localhost"
        assert result["port"] == 5432
        assert result["user"] == "user"
        assert result["password"] == "password"
        assert result["database"] == "mydb"

    @patch('airflow.hooks.base.BaseHook')
    def test_resolve_from_connection_id(self, mock_hook):
        """Test resolving from connection ID string"""
        mock_conn = Mock()
        mock_conn.conn_type = "postgres"
        mock_conn.host = "localhost"
        mock_conn.port = 5432
        mock_conn.login = "user"
        mock_conn.password = "password"
        mock_conn.schema = "mydb"
        mock_conn.extra_dejson = {}
        mock_hook.get_connection.return_value = mock_conn

        result = resolve_credentials("postgres_prod")

        assert result["type"] == "postgres"
        assert result["host"] == "localhost"

    def test_resolve_from_dict(self):
        """Test that dicts are passed through as-is"""
        config_dict = {
            "type": "postgres",
            "host": "localhost",
            "port": 5432,
            "user": "user",
            "password": "password",
        }

        result = resolve_credentials(config_dict)

        assert result == config_dict

    @patch('airflow.hooks.base.BaseHook')
    def test_resolve_snowflake(self, mock_hook):
        """Test Snowflake connection resolution"""
        mock_conn = Mock()
        mock_conn.conn_type = "snowflake"
        mock_conn.host = "account.snowflakecomputing.com"
        mock_conn.login = "user"
        mock_conn.password = "password"
        mock_conn.schema = "mydb"
        mock_conn.extra_dejson = {
            "account": "xy12345",
            "warehouse": "COMPUTE_WH",
            "role": "TRANSFORMER"
        }
        mock_hook.get_connection.return_value = mock_conn

        result = resolve_credentials("snowflake_prod")

        assert result["type"] == "snowflake"
        assert result["account"] == "xy12345"
        assert result["warehouse"] == "COMPUTE_WH"
        assert result["role"] == "TRANSFORMER"

    @patch('airflow.hooks.base.BaseHook')
    def test_explicit_resolver_type(self, mock_hook):
        """Test explicitly specifying resolver type"""
        mock_conn = Mock()
        mock_conn.conn_type = "postgres"
        mock_conn.host = "localhost"
        mock_conn.port = 5432
        mock_conn.login = "user"
        mock_conn.password = "password"
        mock_conn.schema = "mydb"
        mock_conn.extra_dejson = {}
        mock_hook.get_connection.return_value = mock_conn

        result = resolve_credentials("postgres_prod", resolver_type="airflow")

        assert result["type"] == "postgres"


class TestCustomResolver:
    """Test custom resolver registration"""

    def test_register_custom_resolver(self):
        """Test registering a custom credential resolver"""
        class TestResolver(CredentialResolver):
            def resolve(self, identifier):
                return {
                    "type": "custom",
                    "identifier": identifier,
                }

        register_credential_resolver('test', TestResolver())

        result = resolve_credentials("test_id", resolver_type="test")

        assert result["type"] == "custom"
        assert result["identifier"] == "test_id"



class TestGeneratorIntegration:
    """Integration tests with SQLMeshDAGGenerator"""

    @patch('airflow.hooks.base.BaseHook')
    def test_generator_with_connection_object(self, mock_hook):
        """Test passing connection object directly to generator"""
        from sqlmesh_dag_generator import SQLMeshDAGGenerator

        mock_conn = Mock()
        mock_conn.conn_type = "postgres"
        mock_conn.host = "localhost"
        mock_conn.port = 5432
        mock_conn.login = "user"
        mock_conn.password = "password"
        mock_conn.schema = "mydb"
        mock_conn.extra_dejson = {}

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/path/to/project",
            dag_id="test_dag",
            gateway="prod",
            connection=mock_conn,  # Direct object!
        )

        assert generator.config.sqlmesh.connection_config is not None
        assert generator.config.sqlmesh.connection_config["type"] == "postgres"
        assert generator.config.sqlmesh.connection_config["host"] == "localhost"

    @patch('airflow.hooks.base.BaseHook')
    def test_generator_with_connection_id(self, mock_hook):
        """Test passing connection ID string to generator"""
        from sqlmesh_dag_generator import SQLMeshDAGGenerator

        mock_conn = Mock()
        mock_conn.conn_type = "postgres"
        mock_conn.host = "localhost"
        mock_conn.port = 5432
        mock_conn.login = "user"
        mock_conn.password = "password"
        mock_conn.schema = "mydb"
        mock_conn.extra_dejson = {}
        mock_hook.get_connection.return_value = mock_conn

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/path/to/project",
            dag_id="test_dag",
            gateway="prod",
            connection="postgres_prod",  # String ID!
        )

        assert generator.config.sqlmesh.connection_config is not None
        assert generator.config.sqlmesh.connection_config["type"] == "postgres"

    def test_generator_with_dict_config(self):
        """Test passing dict configuration to generator"""
        from sqlmesh_dag_generator import SQLMeshDAGGenerator

        connection_config = {
            "type": "postgres",
            "host": "localhost",
            "port": 5432,
            "user": "user",
            "password": "password",
            "database": "mydb"
        }

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/path/to/project",
            dag_id="test_dag",
            gateway="prod",
            connection=connection_config,  # Dict!
        )

        assert generator.config.sqlmesh.connection_config == connection_config

    @patch('airflow.hooks.base.BaseHook')
    def test_generator_with_separate_connections(self, mock_hook):
        """Test separate data and state connections"""
        from sqlmesh_dag_generator import SQLMeshDAGGenerator

        mock_conn = Mock()
        mock_conn.conn_type = "postgres"
        mock_conn.host = "localhost"
        mock_conn.port = 5432
        mock_conn.login = "user"
        mock_conn.password = "password"
        mock_conn.schema = "mydb"
        mock_conn.extra_dejson = {}
        mock_hook.get_connection.return_value = mock_conn

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path="/path/to/project",
            dag_id="test_dag",
            gateway="prod",
            connection="postgres_data",
            state_connection="postgres_state",
        )

        assert generator.config.sqlmesh.connection_config is not None
        assert generator.config.sqlmesh.state_connection_config is not None

