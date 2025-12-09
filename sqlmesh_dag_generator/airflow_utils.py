"""
Credential resolution utilities for SQLMesh DAG Generator.

This module provides a flexible, plugin-based architecture for resolving
database credentials from various sources:
- Airflow Connections (direct object support)
- Airflow Variables
- AWS Secrets Manager
- HashiCorp Vault
- Environment variables
- Custom resolvers

Design Philosophy:
- Accept connection objects directly (no conversion needed)
- Support multiple credential sources
- Extensible via plugins
- Minimal boilerplate for users
"""
from typing import Dict, Any, Optional, Union, Callable
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ==============================================================================
# Credential Resolver Architecture
# ==============================================================================

class CredentialResolver(ABC):
    """
    Base class for credential resolvers.

    Allows pluggable credential resolution from various sources.
    """

    @abstractmethod
    def resolve(self, identifier: Any) -> Dict[str, Any]:
        """
        Resolve credentials from the source.

        Args:
            identifier: Source-specific identifier (conn_id, secret_name, etc.)

        Returns:
            Dictionary with connection configuration
        """
        pass


class AirflowConnectionResolver(CredentialResolver):
    """
    Resolve credentials from Airflow Connections.

    Supports both:
    - Connection ID (string) - will fetch the connection
    - Connection object directly - will use as-is
    """

    def resolve(self, identifier: Union[str, Any]) -> Dict[str, Any]:
        """
        Resolve from Airflow Connection.

        Args:
            identifier: Either connection ID (str) or Connection object

        Returns:
            SQLMesh-compatible connection config
        """
        # If it's already a connection object, use it directly
        if hasattr(identifier, 'conn_type'):
            conn = identifier
        else:
            # It's a connection ID, fetch it
            try:
                from airflow.hooks.base import BaseHook
                conn = BaseHook.get_connection(identifier)
            except Exception as e:
                logger.error(f"Failed to get Airflow connection '{identifier}': {e}")
                raise

        # Auto-detect type or use provided
        conn_type = _map_airflow_conn_type_to_sqlmesh(conn.conn_type)

        return _build_config_from_connection(conn, conn_type)


class EnvironmentVariableResolver(CredentialResolver):
    """Resolve credentials from environment variables."""

    def resolve(self, identifier: Dict[str, str]) -> Dict[str, Any]:
        """
        Resolve from environment variables.

        Args:
            identifier: Dict mapping config keys to env var names
                Example: {"host": "DB_HOST", "user": "DB_USER", ...}

        Returns:
            SQLMesh-compatible connection config
        """
        import os

        config = {}
        for key, env_var in identifier.items():
            value = os.getenv(env_var)
            if value is not None:
                config[key] = value

        return config


class AWSSecretsManagerResolver(CredentialResolver):
    """Resolve credentials from AWS Secrets Manager."""

    def resolve(self, identifier: str) -> Dict[str, Any]:
        """
        Resolve from AWS Secrets Manager.

        Args:
            identifier: Secret name

        Returns:
            SQLMesh-compatible connection config
        """
        try:
            import boto3
            import json

            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId=identifier)

            # Parse JSON secret
            if 'SecretString' in response:
                secret = json.loads(response['SecretString'])
                return secret
            else:
                raise ValueError("Binary secrets not supported")

        except Exception as e:
            logger.error(f"Failed to resolve from AWS Secrets Manager '{identifier}': {e}")
            raise


class CallableResolver(CredentialResolver):
    """Resolve credentials using a custom callable."""

    def __init__(self, func: Callable):
        self.func = func

    def resolve(self, identifier: Any) -> Dict[str, Any]:
        """Call the custom function to resolve credentials."""
        return self.func(identifier)


# Registry of available resolvers
_RESOLVERS = {
    'airflow': AirflowConnectionResolver(),
    'env': EnvironmentVariableResolver(),
    'aws_secrets': AWSSecretsManagerResolver(),
}


def register_credential_resolver(name: str, resolver: CredentialResolver):
    """
    Register a custom credential resolver.

    Example:
        class VaultResolver(CredentialResolver):
            def resolve(self, identifier):
                # Fetch from Vault
                return {...}

        register_credential_resolver('vault', VaultResolver())
    """
    _RESOLVERS[name] = resolver


def resolve_credentials(
    source: Union[str, Any],
    resolver_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve credentials from any source.

    This is the main entry point for credential resolution.

    Args:
        source: The credential source (conn_id, Connection object, secret name, etc.)
        resolver_type: Type of resolver to use ('airflow', 'env', 'aws_secrets', custom)
                       If None, will auto-detect based on source type

    Returns:
        SQLMesh-compatible connection configuration

    Examples:
        # Direct Airflow Connection object (auto-detected)
        conn = BaseHook.get_connection("postgres_prod")
        config = resolve_credentials(conn)

        # Airflow connection ID
        config = resolve_credentials("postgres_prod", resolver_type="airflow")

        # AWS Secrets Manager
        config = resolve_credentials("prod/database/creds", resolver_type="aws_secrets")

        # Environment variables
        config = resolve_credentials({
            "type": "DB_TYPE",
            "host": "DB_HOST",
            "user": "DB_USER",
            "password": "DB_PASSWORD",
        }, resolver_type="env")

        # Already a dict - pass through
        config = resolve_credentials({"type": "postgres", "host": "..."})
    """
    # If already a dict, return as-is
    if isinstance(source, dict):
        return source

    # Auto-detect resolver type if not provided
    if resolver_type is None:
        resolver_type = _auto_detect_resolver(source)

    # Get resolver
    if resolver_type not in _RESOLVERS:
        raise ValueError(f"Unknown resolver type: {resolver_type}")

    resolver = _RESOLVERS[resolver_type]

    # Resolve and return
    return resolver.resolve(source)


def _auto_detect_resolver(source: Any) -> str:
    """Auto-detect which resolver to use based on source type."""

    # Check if it's an Airflow Connection object
    if hasattr(source, 'conn_type') and hasattr(source, 'host'):
        return 'airflow'

    # Check if it's a string (could be connection ID or secret name)
    if isinstance(source, str):
        # Default to Airflow for strings
        return 'airflow'

    # Check if it's a dict (env var mapping)
    if isinstance(source, dict):
        return 'env'

    # Default to Airflow
    return 'airflow'


# ==============================================================================
# Connection Building Helpers
# ==============================================================================

def _build_config_from_connection(conn: Any, conn_type: str) -> Dict[str, Any]:
    """Build SQLMesh config from an Airflow connection object."""

    # Build base config
    config = {
        "type": conn_type,
    }

    # Add connection details based on type
    if conn_type in ["postgres", "postgresql", "redshift"]:
        config.update({
            "host": conn.host,
            "port": conn.port or 5432,
            "user": conn.login,
            "password": conn.password,
            "database": conn.schema or "postgres",
        })
    elif conn_type in ["mysql", "mariadb"]:
        config.update({
            "host": conn.host,
            "port": conn.port or 3306,
            "user": conn.login,
            "password": conn.password,
            "database": conn.schema,
        })
    elif conn_type == "snowflake":
        # Parse extra for Snowflake-specific settings
        extra = conn.extra_dejson
        config.update({
            "account": extra.get("account") or conn.host,
            "user": conn.login,
            "password": conn.password,
            "database": conn.schema,
            "warehouse": extra.get("warehouse"),
            "role": extra.get("role"),
        })
    elif conn_type == "bigquery":
        extra = conn.extra_dejson
        config.update({
            "project": extra.get("project") or conn.schema,
            "credentials_path": extra.get("keyfile_path"),
            "location": extra.get("location", "US"),
        })
    elif conn_type == "databricks":
        extra = conn.extra_dejson
        config.update({
            "server_hostname": conn.host,
            "http_path": extra.get("http_path"),
            "access_token": conn.password or extra.get("token"),
            "catalog": extra.get("catalog"),
        })
    elif conn_type == "duckdb":
        config.update({
            "database": conn.host or ":memory:",
        })
    else:
        # Generic config - include all available fields
        if conn.host:
            config["host"] = conn.host
        if conn.port:
            config["port"] = conn.port
        if conn.login:
            config["user"] = conn.login
        if conn.password:
            config["password"] = conn.password
        if conn.schema:
            config["database"] = conn.schema

        # Include extra fields
        if conn.extra_dejson:
            config.update(conn.extra_dejson)

    logger.info(f"Built SQLMesh config from Airflow connection (type: {conn_type})")
    return config


def _map_airflow_conn_type_to_sqlmesh(airflow_conn_type: str) -> str:
    """Map Airflow connection type to SQLMesh connection type"""
    mapping = {
        "postgres": "postgres",
        "postgresql": "postgres",
        "redshift": "redshift",
        "mysql": "mysql",
        "snowflake": "snowflake",
        "bigquery": "bigquery",
        "google_cloud_platform": "bigquery",
        "databricks": "databricks",
        "duckdb": "duckdb",
    }

    return mapping.get(airflow_conn_type.lower(), airflow_conn_type)




