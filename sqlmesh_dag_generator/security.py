"""
Security utilities for sqlmesh-dag-generator

Provides credential filtering and security best practices.
"""
import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CredentialFilter(logging.Filter):
    """
    Logging filter to scrub sensitive credentials from log messages.

    Automatically redacts:
    - passwords
    - tokens
    - secrets
    - API keys
    - Database connection strings with passwords
    """

    SENSITIVE_PATTERNS = [
        # Key-value patterns
        (r'password["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r'password=***REDACTED***'),
        (r'passwd["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r'passwd=***REDACTED***'),
        (r'token["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r'token=***REDACTED***'),
        (r'secret["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r'secret=***REDACTED***'),
        (r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r'api_key=***REDACTED***'),
        (r'access[_-]?key["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)', r'access_key=***REDACTED***'),

        # Database connection strings
        (r'postgresql://[^:]+:([^@]+)@', r'postgresql://user:***REDACTED***@'),
        (r'mysql://[^:]+:([^@]+)@', r'mysql://user:***REDACTED***@'),
        (r'redshift://[^:]+:([^@]+)@', r'redshift://user:***REDACTED***@'),
        (r'snowflake://[^:]+:([^@]+)@', r'snowflake://user:***REDACTED***@'),

        # AWS credentials
        (r'(aws_secret_access_key\s*[:=]\s*)[^\s,}]+', r'\1***REDACTED***'),
        (r'(AWS_SECRET_ACCESS_KEY\s*[:=]\s*)[^\s,}]+', r'\1***REDACTED***'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and scrub the log record"""
        record.msg = self._scrub(str(record.msg))
        if record.args:
            record.args = tuple(self._scrub(str(arg)) for arg in record.args)
        return True

    def _scrub(self, text: str) -> str:
        """Scrub sensitive data from text"""
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


def validate_connection_security(connection: Any) -> None:
    """
    Validate connection configuration for security issues.

    Warns if credentials are passed as dict instead of Airflow Connection.

    Args:
        connection: Connection configuration (str, dict, or Connection object)
    """
    if isinstance(connection, dict):
        sensitive_keys = {'password', 'passwd', 'token', 'secret', 'api_key', 'access_key'}
        found_sensitive = sensitive_keys & set(connection.keys())

        if found_sensitive:
            logger.warning(
                "⚠️  SECURITY WARNING: Connection dict contains sensitive keys: %s\n"
                "   Credentials may appear in logs, config files, or error messages.\n"
                "   \n"
                "   RECOMMENDED: Use Airflow Connection ID instead:\n"
                "   \n"
                "   # Instead of this:\n"
                "   generator = SQLMeshDAGGenerator(\n"
                "       connection={'password': 'secret123'}  # ❌ Risky!\n"
                "   )\n"
                "   \n"
                "   # Do this:\n"
                "   generator = SQLMeshDAGGenerator(\n"
                "       connection='my_connection_id'  # ✅ Secure!\n"
                "   )\n"
                "   \n"
                "   Create connection in Airflow UI: Admin → Connections → Add\n",
                found_sensitive
            )


def install_credential_filter() -> None:
    """
    Install credential filter on the root logger.

    This ensures all log messages are scrubbed of sensitive data.
    """
    root_logger = logging.getLogger()

    # Check if already installed
    for filter_obj in root_logger.filters:
        if isinstance(filter_obj, CredentialFilter):
            return  # Already installed

    root_logger.addFilter(CredentialFilter())
    logger.debug("Installed credential filter on root logger")


def scrub_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively scrub sensitive data from a dictionary.

    Useful for logging configuration objects.

    Args:
        data: Dictionary potentially containing sensitive data

    Returns:
        Dictionary with sensitive values replaced

    Example:
        >>> config = {"host": "db.example.com", "password": "secret"}
        >>> scrub_dict(config)
        {"host": "db.example.com", "password": "***REDACTED***"}
    """
    sensitive_keys = {'password', 'passwd', 'token', 'secret', 'api_key', 'access_key',
                     'aws_secret_access_key', 'private_key'}

    scrubbed = {}
    for key, value in data.items():
        if key.lower() in sensitive_keys:
            scrubbed[key] = "***REDACTED***"
        elif isinstance(value, dict):
            scrubbed[key] = scrub_dict(value)
        elif isinstance(value, str):
            # Scrub connection strings
            scrubbed_value = value
            for pattern, replacement in CredentialFilter.SENSITIVE_PATTERNS:
                scrubbed_value = re.sub(pattern, replacement, scrubbed_value, flags=re.IGNORECASE)
            scrubbed[key] = scrubbed_value
        else:
            scrubbed[key] = value

    return scrubbed

