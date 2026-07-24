"""
Core DAG generator module
"""
from datetime import datetime, timedelta, timezone
import inspect
import logging
from pathlib import Path
from typing import Dict, Optional, Union, Any, List

from sqlmesh import Context
from sqlmesh.core.model import Model

from sqlmesh_dag_generator.config import DAGGeneratorConfig, SQLMeshConfig, AirflowConfig, GenerationConfig
from sqlmesh_dag_generator.models import SQLMeshModelInfo, DAGStructure
from sqlmesh_dag_generator.dag_builder import AirflowDAGBuilder
from sqlmesh_dag_generator.security import install_credential_filter, validate_connection_security
from sqlmesh_dag_generator.utils import get_interval_frequency_minutes, sanitize_task_id

logger = logging.getLogger(__name__)

# Install credential filter globally on first import
install_credential_filter()


class SQLMeshDAGGenerator:
    """
    Main class for generating Airflow DAGs from SQLMesh projects.

    This generator:
    1. Loads a SQLMesh project using Context
    2. Extracts models and their dependencies
    3. Builds an Airflow DAG with proper task dependencies
    4. Generates Python DAG files for Airflow
    """

    def __init__(
        self,
        sqlmesh_project_path: Optional[str] = None,
        dag_id: Optional[str] = None,
        schedule_interval: Optional[str] = None,
        auto_schedule: bool = True,
        config: Optional[DAGGeneratorConfig] = None,
        connection: Optional[Union[str, Dict, Any]] = None,
        state_connection: Optional[Union[str, Dict, Any]] = None,
        **kwargs
    ):
        """
        Initialize the DAG generator.

        Args:
            sqlmesh_project_path: Path to SQLMesh project
            dag_id: Airflow DAG ID
            schedule_interval: Airflow schedule interval (overrides auto_schedule if set)
            auto_schedule: Automatically detect schedule from SQLMesh models (default: True)
            config: Full DAGGeneratorConfig object
            connection: Database connection - can be:
                - Airflow Connection object (RECOMMENDED)
                - Airflow connection ID (string)
                - Dict with connection parameters
                - AWS Secrets Manager secret name (with resolver_type)
            state_connection: State database connection (same types as connection)
            **kwargs: Additional configuration options
                - gateway: SQLMesh gateway name
                - environment: (deprecated) use gateway instead
                - credential_resolver: Override credential resolver type
                - default_args: Airflow DAG default_args
                - tags: Airflow DAG tags
                - catchup: Airflow catchup setting
                - max_active_runs: Airflow max_active_runs
                - output_dir: Directory for generated DAG files
                - operator_type: Type of operator (python, bash, kubernetes)
                - include_tests: Include test models
                - parallel_tasks: Enable parallel task execution
                - include_models: List of models to include
                - exclude_models: List of models to exclude

        Examples:
            # RECOMMENDED: Auto-schedule based on SQLMesh models
            generator = SQLMeshDAGGenerator(
                sqlmesh_project_path="/path/to/project",
                connection="postgres_prod",
                auto_schedule=True,  # Default - detects minimum interval
            )

            # Or override with manual schedule
            generator = SQLMeshDAGGenerator(
                sqlmesh_project_path="/path/to/project",
                schedule_interval="@hourly",  # Disables auto_schedule
                connection="postgres_prod",
            )

            # Or just pass connection ID (will be resolved automatically)
            generator = SQLMeshDAGGenerator(
                sqlmesh_project_path="/path/to/project",
                connection="postgres_prod",  # Simpler!
            )

            # Or pass a dict directly
            generator = SQLMeshDAGGenerator(
                sqlmesh_project_path="/path/to/project",
                connection={
                    "type": "postgres",
                    "host": "localhost",
                    "user": "user",
                    "password": "pass",
                },
            )

            # Separate state connection
            generator = SQLMeshDAGGenerator(
                sqlmesh_project_path="/path/to/project",
                connection="snowflake_prod",
                state_connection="postgres_state",
            )

            # AWS Secrets Manager
            generator = SQLMeshDAGGenerator(
                sqlmesh_project_path="/path/to/project",
                connection="prod/database/creds",
                credential_resolver="aws_secrets",
            )
        """
        # Resolve credentials if provided
        resolved_connection = None
        resolved_state_connection = None
        credential_resolver = kwargs.get('credential_resolver')

        if connection is not None:
            # Validate security before resolving
            validate_connection_security(connection)

            from sqlmesh_dag_generator.airflow_utils import resolve_credentials
            resolved_connection = resolve_credentials(connection, resolver_type=credential_resolver)

        if state_connection is not None:
            validate_connection_security(state_connection)

            from sqlmesh_dag_generator.airflow_utils import resolve_credentials
            resolved_state_connection = resolve_credentials(state_connection, resolver_type=credential_resolver)

        if config:
            self.config = config
        else:
            # Build config from individual parameters
            sqlmesh_config = SQLMeshConfig(
                project_path=sqlmesh_project_path or "./",
                environment=kwargs.get("environment", ""),  # Empty string = no virtual env (production)
                gateway=kwargs.get("gateway"),
                connection_config=resolved_connection,
                state_connection_config=resolved_state_connection,
                default_catalog=kwargs.get("default_catalog"),
                config_overrides=kwargs.get("config_overrides", {}),
            )

            airflow_config = AirflowConfig(
                dag_id=dag_id or "sqlmesh_dag",
                schedule_interval=schedule_interval,
                auto_schedule=auto_schedule if schedule_interval is None else False,
                default_args=kwargs.get("default_args", {}),
                tags=kwargs.get("tags", ["sqlmesh"]),
                catchup=kwargs.get("catchup", False),
                max_active_runs=kwargs.get("max_active_runs", 1),
                on_failure_callback=kwargs.get("on_failure_callback"),
                on_success_callback=kwargs.get("on_success_callback"),
                sla_miss_callback=kwargs.get("sla_miss_callback"),
                sla=kwargs.get("sla"),
            )
            airflow_config.recovery.mode = kwargs.get("recovery_mode", airflow_config.recovery.mode)
            airflow_config.recovery.max_intervals = kwargs.get(
                "recovery_max_intervals", airflow_config.recovery.max_intervals
            )
            airflow_config.recovery.fail_on_excess_gap = kwargs.get(
                "recovery_fail_on_excess_gap", airflow_config.recovery.fail_on_excess_gap
            )

            generation_config = GenerationConfig(
                output_dir=kwargs.get("output_dir", "./dags"),
                operator_type=kwargs.get("operator_type", "python"),
                include_tests=kwargs.get("include_tests", False),
                parallel_tasks=kwargs.get("parallel_tasks", True),
                include_models=kwargs.get("include_models"),
                exclude_models=kwargs.get("exclude_models"),
                model_pattern=kwargs.get("model_pattern"),
                include_source_tables=kwargs.get("include_source_tables", True),  # Default: enabled
                return_value=kwargs.get("return_value", True),
                auto_replan_on_change=kwargs.get("auto_replan_on_change", True),
                replan_timeout_hours=kwargs.get("replan_timeout_hours", 6),  # None disables the replan timeout.
                skip_audits=kwargs.get("skip_audits", False),
                enable_health_check=kwargs.get("enable_health_check", False),
                include_tags=kwargs.get("include_tags"),
                exclude_tags=kwargs.get("exclude_tags"),
                pool=kwargs.get("pool"),
                pool_slots=kwargs.get("pool_slots", 1),
                trigger_dag_id=kwargs.get("trigger_dag_id"),
                trigger_dag_conf=kwargs.get("trigger_dag_conf"),
                model_triggers=kwargs.get("model_triggers") or {},
                # Plan optimization options
                skip_backfill=kwargs.get("skip_backfill", False),
                plan_only=kwargs.get("plan_only", False),
                log_plan_details=kwargs.get("log_plan_details", True),
            )

            self.config = DAGGeneratorConfig(
                sqlmesh=sqlmesh_config,
                airflow=airflow_config,
                generation=generation_config,
            )

        self.context: Optional[Context] = None
        self.models: Dict[str, SQLMeshModelInfo] = {}
        self.dag_structure: Optional[DAGStructure] = None
        self.merged_config = None  # Store merged config for runtime task execution
        self.runtime_gateway = None  # Store gateway name for runtime task execution

        # Validate configuration and show helpful warnings
        self._validate_config()

    def _validate_config(self):
        """Validate configuration and show helpful warnings."""
        # Note: default_catalog is NOT a valid SQLMesh config option.
        # SQLMesh automatically determines the default catalog from the database connection.
        # For Redshift (2-part naming), SQLMesh handles this automatically when configured
        # with a valid Redshift connection.
        return None

    def load_sqlmesh_context(self) -> Context:
        """
        Load the SQLMesh context from the project path.

        If runtime connection configuration is provided, it will be merged into
        the SQLMesh config to avoid hardcoded credentials.

        Returns:
            SQLMesh Context object
        """
        from sqlmesh_dag_generator.validation import validate_project_structure, check_resource_availability

        logger.info(f"Loading SQLMesh context from: {self.config.sqlmesh.project_path}")

        # Validate project structure first
        validate_project_structure(self.config.sqlmesh.project_path)

        # Check system resources
        check_resource_availability()

        try:
            import os

            # Build context kwargs
            context_kwargs = {
                "paths": self.config.sqlmesh.project_path,
                "gateway": self.config.sqlmesh.gateway,
            }

            # Add config path if provided
            if self.config.sqlmesh.config_path:
                context_kwargs["config"] = self.config.sqlmesh.config_path

            # If runtime connection config is provided, we need to merge it with the config
            # Also check for SQLMESH_CACHE_DIR environment variable
            cache_dir = os.environ.get("SQLMESH_CACHE_DIR")

            if self.config.sqlmesh.connection_config or self.config.sqlmesh.state_connection_config or self.config.sqlmesh.config_overrides or cache_dir:
                from sqlmesh.core.config import Config

                # Determine gateway name for runtime connections
                # If gateway is not specified, use "default" as the gateway name
                gateway_name = self.config.sqlmesh.gateway or "default"

                # Start with a minimal base config dict
                config_dict = {
                    "gateways": {},
                    "default_gateway": gateway_name,
                }

                # Try to load existing config to preserve other settings
                # (Config.load was removed in modern SQLMesh; use sqlmesh_compat)
                try:
                    from sqlmesh_dag_generator.sqlmesh_compat import (
                        config_to_dict,
                        load_sqlmesh_config,
                    )

                    if self.config.sqlmesh.config_path:
                        base_config = load_sqlmesh_config(self.config.sqlmesh.config_path)
                    else:
                        config_path = Path(self.config.sqlmesh.project_path) / "config.yaml"
                        if config_path.exists():
                            base_config = load_sqlmesh_config(config_path)
                        else:
                            base_config = None

                    if base_config:
                        # Merge settings from base config (but NOT gateway connections)
                        base_dict = config_to_dict(base_config)
                        for key in base_dict:
                            if key not in ["gateways", "default_gateway"]:
                                config_dict[key] = base_dict[key]
                except Exception as e:
                    logger.warning(f"Could not load base config, using minimal config: {e}")

                logger.info(f"Configuring runtime connections for gateway: {gateway_name}")

                # Create gateway config with runtime connections
                if gateway_name not in config_dict["gateways"]:
                    config_dict["gateways"][gateway_name] = {}

                # Merge connection config for the gateway
                if self.config.sqlmesh.connection_config:
                    connection_config = self.config.sqlmesh.connection_config.copy()

                    # Handle default_catalog for Redshift connections
                    # For Redshift, keep default_catalog in connection config
                    # SQLMesh uses this to determine which catalog to omit from SQL generation
                    if connection_config.get("default_catalog"):
                        logger.info(f"Redshift default_catalog: {connection_config['default_catalog']}")

                    config_dict["gateways"][gateway_name]["connection"] = connection_config
                    logger.info(f"Runtime connection configured for gateway: {gateway_name}")
                    logger.debug(f"Connection config: {connection_config}")

                # Merge state connection config
                if self.config.sqlmesh.state_connection_config:
                    config_dict["gateways"][gateway_name]["state_connection"] = self.config.sqlmesh.state_connection_config
                    logger.info(f"Runtime state connection configured for gateway: {gateway_name}")
                    logger.debug(f"State connection config: {self.config.sqlmesh.state_connection_config}")

                # Note: default_catalog is NOT a valid SQLMesh Config field.
                # It is automatically determined from the database connection.
                # If user passed default_catalog, log a warning but don't set it.
                if self.config.sqlmesh.default_catalog:
                    logger.warning(
                        f"default_catalog='{self.config.sqlmesh.default_catalog}' was provided, "
                        f"but this is not a SQLMesh config option. SQLMesh automatically determines "
                        f"the default catalog from the database connection. This parameter will be ignored."
                    )

                # Configure cache directory from environment variable
                if cache_dir:
                    logger.warning(
                        f"SQLMESH_CACHE_DIR is set to: {cache_dir}\n"
                        f"\n"
                        f"⚠️  This environment variable is NOT needed if you're using EFS!\n"
                        f"\n"
                        f"For AWS Fargate + EFS:\n"
                        f"  1. Remove SQLMESH_CACHE_DIR environment variable\n"
                        f"  2. Mount EFS at /opt/airflow/core with readOnly=false\n"
                        f"  3. Cache at /opt/airflow/core/sqlmesh_project/.cache will work automatically\n"
                        f"\n"
                        f"See: docs/YOUR_SETUP_FIX.md for details\n"
                    )


                # Apply any other config overrides
                if self.config.sqlmesh.config_overrides:
                    self._deep_merge(config_dict, self.config.sqlmesh.config_overrides)

                # Create new config from merged dict
                merged_config = Config.parse_obj(config_dict)
                context_kwargs["config"] = merged_config
                self.merged_config = merged_config  # Store for runtime task execution
                self.runtime_gateway = gateway_name  # Store gateway name for runtime

            self.context = Context(**context_kwargs)
            logger.info(f"Successfully loaded SQLMesh context")
            return self.context
        except Exception as e:
            logger.error(f"Failed to load SQLMesh context: {e}")
            raise

    def _deep_merge(self, base_dict: Dict, override_dict: Dict) -> None:
        """Deep merge override_dict into base_dict"""
        for key, value in override_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_merge(base_dict[key], value)
            else:
                base_dict[key] = value

    def extract_models(self) -> Dict[str, SQLMeshModelInfo]:
        """
        Extract model information from SQLMesh context.

        Returns:
            Dictionary mapping model names to SQLMeshModelInfo objects
        """
        from sqlmesh_dag_generator.validation import (
            validate_no_circular_dependencies,
            validate_missing_dependencies,
            estimate_dag_complexity
        )

        if not self.context:
            self.load_sqlmesh_context()

        logger.info("Extracting models from SQLMesh context")

        models = {}

        # Access the models from context
        # The context has a models attribute that contains all loaded models
        if hasattr(self.context, '_models'):
            sqlmesh_models = self.context._models
        elif hasattr(self.context, 'models'):
            sqlmesh_models = self.context.models
        else:
            # Try to get models through the dag
            sqlmesh_models = {}
            logger.warning("Could not find models in context")

        for model_name, model in sqlmesh_models.items():
            # Filter models based on include/exclude patterns and tags
            if not self._should_include_model(model_name, model):
                continue

            model_info = self._extract_model_info(model_name, model)
            models[model_name] = model_info
            logger.debug(f"Extracted model: {model_name}")

        self.models = models
        logger.info(f"Extracted {len(models)} models")

        # Validate dependencies
        if len(models) > 0:
            validate_no_circular_dependencies(models)
            validate_missing_dependencies(models)
            complexity = estimate_dag_complexity(models)
            logger.info(
                f"DAG complexity: {complexity['total_models']} models, "
                f"max depth: {complexity['max_depth']}, "
                f"{complexity['orphan_models']} orphans, "
                f"{complexity['leaf_models']} leaves"
            )

        return models

    def _should_include_model(self, model_name: str, model: Model = None) -> bool:
        """Check if a model should be included based on filters"""
        import re

        # Check include patterns
        if self.config.generation.include_models:
            if model_name not in self.config.generation.include_models:
                return False

        # Check exclude patterns
        if self.config.generation.exclude_models:
            if model_name in self.config.generation.exclude_models:
                return False

        # Check model_pattern (regex)
        if self.config.generation.model_pattern:
            pattern = self.config.generation.model_pattern
            if not re.match(pattern, model_name):
                logger.debug(f"Model {model_name} excluded by pattern: {pattern}")
                return False

        # Tag-based filtering (requires model object)
        if model is not None:
            model_tags = set(getattr(model, 'tags', []) or [])

            # Check include_tags - model must have at least one of these tags
            if self.config.generation.include_tags:
                include_tags = set(self.config.generation.include_tags)
                if not model_tags.intersection(include_tags):
                    logger.debug(f"Model {model_name} excluded: no matching include_tags")
                    return False

            # Check exclude_tags - model must not have any of these tags
            if self.config.generation.exclude_tags:
                exclude_tags = set(self.config.generation.exclude_tags)
                if model_tags.intersection(exclude_tags):
                    logger.debug(f"Model {model_name} excluded: has exclude_tags")
                    return False

        return True

    def _extract_model_info(self, model_name: str, model: Model) -> SQLMeshModelInfo:
        """
        Extract relevant information from a SQLMesh model.

        Args:
            model_name: Name of the model
            model: SQLMesh Model object

        Returns:
            SQLMeshModelInfo object with extracted data
        """
        # Extract dependencies (str names or objects with .name — varies by sqlmesh version)
        from sqlmesh_dag_generator.sqlmesh_compat import normalize_depends_on

        if hasattr(model, "depends_on"):
            dependencies = normalize_depends_on(model.depends_on)
        elif hasattr(model, "dependencies"):
            dependencies = normalize_depends_on(model.dependencies)
        else:
            dependencies = set()

        # Extract scheduling information
        cron = getattr(model, 'cron', None)
        interval_unit = getattr(model, 'interval_unit', None)

        # Extract model kind (FULL, INCREMENTAL, etc.)
        kind = str(getattr(model, 'kind', 'FULL'))

        # Extract metadata
        owner = getattr(model, 'owner', None)
        tags = getattr(model, 'tags', [])
        description = getattr(model, 'description', None)

        return SQLMeshModelInfo(
            name=model_name,
            dependencies=dependencies,
            cron=cron,
            interval_unit=interval_unit,
            kind=kind,
            owner=owner,
            tags=tags,
            description=description,
            model=model,
        )

    def get_source_tables(self, model_name: str) -> List[str]:
        """
        Extract source tables (raw tables) that a model reads from.

        These are tables that are NOT SQLMesh models (e.g., raw.event_hub_all_mt).

        Args:
            model_name: Name of the SQLMesh model

        Returns:
            List of source table names
        """
        if model_name not in self.models:
            return []

        model_info = self.models[model_name]
        model = model_info.model

        source_tables = []

        # SQLMesh models have a 'source_tables' or 'depends_on_past' attribute
        # that lists external tables they read from
        if hasattr(model, 'source_tables'):
            source_tables = list(model.source_tables)
        elif hasattr(model, "depends_on"):
            # Filter out SQLMesh models from dependencies
            # Source tables are dependencies that are NOT in self.models
            from sqlmesh_dag_generator.sqlmesh_compat import normalize_depends_on

            all_deps = normalize_depends_on(model.depends_on)
            source_tables = [dep for dep in all_deps if dep not in self.models]

        return source_tables

    def get_recommended_schedule(self) -> str:
        """
        Get the recommended schedule based on SQLMesh model intervals.

        This analyzes all models in the SQLMesh project and returns the
        shortest (most frequent) interval as an Airflow cron expression.

        Returns:
            Cron expression for the recommended schedule (e.g., "*/5 * * * *")

        Example:
            generator = SQLMeshDAGGenerator(...)
            recommended = generator.get_recommended_schedule()
            # Use in DAG: schedule=recommended
        """
        # If schedule is manually set, return it
        if self.config.airflow.schedule_interval:
            return self.config.airflow.schedule_interval

        # If auto_schedule is disabled, return default
        if not self.config.airflow.auto_schedule:
            return "@daily"

        # Load models if not already loaded
        if not self.models:
            if not self.context:
                self.load_sqlmesh_context()
            self.extract_models()

        # Collect all interval_units from models
        interval_units = [model.interval_unit for model in self.models.values()]

        # Get minimum interval and convert to cron
        from sqlmesh_dag_generator.utils import get_minimum_interval
        min_interval, cron = get_minimum_interval(interval_units)

        if min_interval:
            logger.info(f"Auto-detected schedule: {cron} (based on interval: {min_interval})")
        else:
            logger.info(f"No intervals found in models, using default: {cron}")

        return cron

    def get_model_intervals_summary(self) -> Dict[str, List[str]]:
        """
        Get a summary of models grouped by their interval_unit.

        Useful for understanding the scheduling distribution in your project.

        Returns:
            Dict mapping interval names to lists of model names

        Example:
            summary = generator.get_model_intervals_summary()
            # {'FIVE_MINUTE': ['model1', 'model2'], 'HOUR': ['model3'], ...}
        """
        if not self.models:
            if not self.context:
                self.load_sqlmesh_context()
            self.extract_models()

        summary = {}
        for model_name, model_info in self.models.items():
            interval_key = str(model_info.interval_unit) if model_info.interval_unit else "UNSCHEDULED"
            if interval_key not in summary:
                summary[interval_key] = []
            summary[interval_key].append(model_name)

        return summary

    def get_expected_interval_minutes(self) -> Optional[int]:
        """Return the minimum configured model interval in minutes."""
        if not self.models:
            if not self.context:
                self.load_sqlmesh_context()
            self.extract_models()

        intervals = [
            get_interval_frequency_minutes(model.interval_unit)
            for model in self.models.values()
            if model.interval_unit is not None
        ]
        return min(intervals) if intervals else None

    def has_subhourly_incremental_models(self) -> bool:
        """Return True when the project contains sub-hourly incremental models."""
        if not self.models:
            if not self.context:
                self.load_sqlmesh_context()
            self.extract_models()

        for model in self.models.values():
            interval_minutes = get_interval_frequency_minutes(model.interval_unit)
            kind = str(model.kind or "").upper()
            if interval_minutes < 60 and "INCREMENTAL" in kind:
                return True

        return False

    def _integrity_warning_message(self) -> Optional[str]:
        """Describe when Airflow scheduling can leave SQLMesh completeness gaps."""
        if self.config.airflow.catchup or not self.has_subhourly_incremental_models():
            return None

        recovery_mode = self.config.airflow.recovery.mode
        if recovery_mode == "bounded_auto":
            return None

        if recovery_mode == "warn":
            return (
                "Sub-hourly incremental SQLMesh models detected with catchup=False. "
                "recovery_mode='warn' will detect missed Airflow intervals, but it will not replay them automatically. "
                "Use recovery_mode='bounded_auto' or a manual replay path if outage completeness matters."
            )

        return (
            "Sub-hourly incremental SQLMesh models detected with catchup=False. Missed Airflow intervals "
            "will not be replayed automatically after downtime. Consider enabling recovery_mode='warn' or "
            "recovery_mode='bounded_auto', enabling Airflow catchup, or operating a manual replay path."
        )

    def _log_integrity_warning_if_needed(self) -> None:
        """Emit a runtime warning for potentially incomplete outage recovery setups."""
        warning_message = self._integrity_warning_message()
        if warning_message:
            logger.warning(warning_message)

    def build_dag_structure(self) -> DAGStructure:
        """
        Build the DAG structure from extracted models.

        Returns:
            DAGStructure object representing the task graph
        """
        if not self.models:
            self.extract_models()

        self._log_integrity_warning_if_needed()

        logger.info("Building DAG structure")

        self.dag_structure = DAGStructure(
            dag_id=self.config.airflow.dag_id,
            models=self.models,
            config=self.config,
        )

        logger.info(f"DAG structure built with {len(self.models)} tasks")
        return self.dag_structure

    def generate_dag(self) -> str:
        """
        Generate the complete Airflow DAG (static generation).

        Returns:
            Generated DAG Python code as a string
        """
        logger.info(f"Generating Airflow DAG: {self.config.airflow.dag_id}")

        # Load context and extract models
        if not self.context:
            self.load_sqlmesh_context()

        if not self.models:
            self.extract_models()

        self._log_integrity_warning_if_needed()

        if not self.dag_structure:
            self.build_dag_structure()

        # Build the DAG
        dag_builder = AirflowDAGBuilder(self.config, self.dag_structure)
        dag_code = dag_builder.build()

        # Save to file if not dry run
        if not self.config.generation.dry_run:
            output_path = self._get_output_path()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dag_code)

            logger.info(f"DAG file written to: {output_path}")

        return dag_code

    def generate_dynamic_dag(self) -> str:
        """
        Generate a dynamic Airflow DAG that discovers SQLMesh models at runtime.

        This creates a single DAG file that works for any SQLMesh project.
        The DAG discovers models when Airflow parses it, so no regeneration
        is needed when models change. This is a "fire and forget" solution.

        Features:
        - Auto-discovers models at DAG parse time
        - Uses Airflow Variables for configuration (multi-environment support)
        - Uses data_interval_start/end for proper incremental model handling
        - Enhanced error handling with SQLMesh-specific logging
        - No manual regeneration needed

        Returns:
            Generated dynamic DAG Python code as a string
        """
        logger.info(f"Generating dynamic Airflow DAG: {self.config.airflow.dag_id}")

        # Load context for initial validation (optional)
        if not self.context:
            self.load_sqlmesh_context()

        if not self.models:
            self.extract_models()

        if not self.dag_structure:
            self.build_dag_structure()

        # Build the dynamic DAG
        dag_builder = AirflowDAGBuilder(self.config, self.dag_structure)
        dag_code = dag_builder.build_dynamic()

        # Save to file if not dry run
        if not self.config.generation.dry_run:
            output_path = self._get_output_path()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(dag_code)

            logger.info(f"Dynamic DAG file written to: {output_path}")
            logger.info("📌 Place this file in Airflow's dags/ folder and forget about it!")
            logger.info("   The DAG will automatically discover SQLMesh models at runtime.")

        return dag_code

    def create_tasks_in_dag(self, dag, models: Optional[List[str]] = None):
        """
        Create Airflow tasks directly inside a DAG context.

        This method is designed to be called inside a DAG definition:

        Example:
            with DAG(...) as dag:
                generator = SQLMeshDAGGenerator(...)
                generator.create_tasks_in_dag(dag)

        Args:
            dag: Airflow DAG object
            models: Optional list of model names to include (partial run)

        Returns:
            Dictionary of created tasks {model_name: task}
        """
        from sqlmesh_dag_generator.airflow_compat import (
            EmptyOperator,
            PythonOperator,
            TriggerDagRunOperator,
        )
        from sqlmesh_dag_generator.triggers import (
            default_trigger_conf,
            resolve_model_trigger,
            trigger_task_id,
        )

        # Load models if not already loaded
        if not self.models:
            self.extract_models()

        # Filter models if specified
        target_models = self.models
        if models:
            target_models = {k: v for k, v in self.models.items() if k in models}
            logger.info(f"Filtering DAG to {len(target_models)} models: {list(target_models.keys())}")

        self._log_integrity_warning_if_needed()

        tasks = {}
        source_table_tasks = {}
        recovery_config = self.config.airflow.recovery
        expected_interval_minutes = self.get_expected_interval_minutes()

        # Step -1: Create Health Check Task (if enabled)
        health_check_task = None
        if self.config.generation.enable_health_check:
            def run_health_check(**context):
                from sqlmesh import Context
                logger.info("Running SQLMesh health check...")
                
                # Build context kwargs
                context_kwargs = {
                    "paths": self.config.sqlmesh.project_path,
                }
                if self.merged_config is not None:
                    context_kwargs["config"] = self.merged_config
                    if self.runtime_gateway is not None:
                        context_kwargs["gateway"] = self.runtime_gateway
                else:
                    context_kwargs["gateway"] = self.config.sqlmesh.gateway

                # Load context
                ctx = Context(**context_kwargs)
                
                # Check connection
                logger.info(f"Checking connection to gateway: {ctx.gateway}")
                # Simple query to verify connection
                try:
                    ctx.engine_adapter.fetchone("SELECT 1")
                    logger.info("✅ Database connection successful")
                except Exception as e:
                    raise RuntimeError(f"❌ Database connection failed: {e}")
                
                # Check environment
                env_name = self.config.sqlmesh.environment
                if env_name:
                    logger.info(f"Checking environment: {env_name}")
                    # This will fail if environment doesn't exist and we try to use it
                    # But for now just logging that we are using it
                
                return "Health check passed"

            health_check_task = PythonOperator(
                task_id="sqlmesh_health_check",
                python_callable=run_health_check,
                dag=dag
            )
            logger.info("Created health check task: sqlmesh_health_check")

        # Step 0: Create Replan Task (if enabled)
        # Prefer a dedicated deploy DAG (create_plan_apply_task) for large warehouses
        # so interval runs never block on plan/apply.
        replan_task = None
        if self.config.generation.auto_replan_on_change:
            replan_task = self.create_plan_apply_task(dag=dag)
            if health_check_task:
                health_check_task >> replan_task

        recovery_anchor_task = None
        if (
            recovery_config.mode != "disabled"
            and expected_interval_minutes
            and self.has_subhourly_incremental_models()
        ):
            def detect_interval_gap(**context):
                prev_end = context.get("prev_data_interval_end_success")
                current_start = context.get("data_interval_start") or context.get("execution_date")
                payload = {
                    "gap_intervals": 0,
                    "recovery_start": None,
                    "recovery_end": None,
                }

                if not prev_end or not current_start:
                    logger.warning(
                        "Skipping SQLMesh integrity gap detection because Airflow interval context is incomplete."
                    )
                    return payload

                if isinstance(prev_end, str):
                    prev_end = datetime.fromisoformat(prev_end)
                if isinstance(current_start, str):
                    current_start = datetime.fromisoformat(current_start)

                gap_minutes = int((current_start - prev_end).total_seconds() // 60)
                if gap_minutes <= 0:
                    return payload

                gap_intervals = (gap_minutes + expected_interval_minutes - 1) // expected_interval_minutes
                payload = {
                    "gap_intervals": gap_intervals,
                    "recovery_start": prev_end.isoformat(),
                    "recovery_end": current_start.isoformat(),
                }
                logger.warning(
                    "Detected %s missing SQLMesh interval(s) before %s. Recovery window: %s -> %s.",
                    gap_intervals,
                    current_start,
                    prev_end,
                    current_start,
                )

                if (
                    recovery_config.fail_on_excess_gap
                    and gap_intervals > recovery_config.max_intervals
                ):
                    raise RuntimeError(
                        "Detected a SQLMesh interval gap larger than recovery.max_intervals. "
                        "Manual replay is required before the DAG can continue."
                    )

                return payload

            integrity_task = PythonOperator(
                task_id="sqlmesh_integrity_guard",
                python_callable=detect_interval_gap,
                dag=dag,
            )
            tasks["sqlmesh_integrity_guard"] = integrity_task

            if replan_task:
                replan_task >> integrity_task
            elif health_check_task:
                health_check_task >> integrity_task

            recovery_anchor_task = integrity_task

            if recovery_config.mode == "bounded_auto":
                selected_models = list(target_models.keys())

                def replay_missing_intervals(**context):
                    task_instance = context["ti"]
                    gap_payload = task_instance.xcom_pull(task_ids="sqlmesh_integrity_guard") or {}
                    gap_intervals = gap_payload.get("gap_intervals", 0)
                    if not gap_intervals:
                        logger.info("No SQLMesh recovery backfill needed for this Airflow run.")
                        return {"status": "skipped", "gap_intervals": 0}

                    if gap_intervals > recovery_config.max_intervals:
                        message = (
                            "Detected a SQLMesh interval gap larger than recovery.max_intervals. "
                            "Skipping bounded recovery and leaving replay to manual intervention."
                        )
                        if recovery_config.fail_on_excess_gap:
                            raise RuntimeError(message)
                        logger.warning(message)
                        return {"status": "skipped", "gap_intervals": gap_intervals}

                    recovery_start = datetime.fromisoformat(gap_payload["recovery_start"])
                    recovery_end = datetime.fromisoformat(gap_payload["recovery_end"])
                    logger.info(
                        "Running bounded SQLMesh recovery for %s missing interval(s): %s -> %s",
                        gap_intervals,
                        recovery_start,
                        recovery_end,
                    )

                    context_kwargs = {"paths": self.config.sqlmesh.project_path}
                    if self.merged_config is not None:
                        context_kwargs["config"] = self.merged_config
                        if self.runtime_gateway is not None:
                            context_kwargs["gateway"] = self.runtime_gateway
                    else:
                        context_kwargs["gateway"] = self.config.sqlmesh.gateway

                    run_ctx = Context(**context_kwargs)
                    run_kwargs = {
                        "environment": self.config.sqlmesh.environment,
                        "start": recovery_start,
                        "end": recovery_end,
                    }
                    if selected_models:
                        run_kwargs["select_models"] = selected_models

                    import inspect

                    run_sig = inspect.signature(run_ctx.run)
                    if "skip_audits" in run_sig.parameters and self.config.generation.skip_audits:
                        run_kwargs["skip_audits"] = True

                    result = run_ctx.run(**run_kwargs)
                    return {
                        "status": result.name if hasattr(result, "name") else str(result),
                        "gap_intervals": gap_intervals,
                        "recovery_start": gap_payload["recovery_start"],
                        "recovery_end": gap_payload["recovery_end"],
                    }

                recovery_task = PythonOperator(
                    task_id="sqlmesh_recovery_backfill",
                    python_callable=replay_missing_intervals,
                    dag=dag,
                )
                tasks["sqlmesh_recovery_backfill"] = recovery_task
                integrity_task >> recovery_task
                recovery_anchor_task = recovery_task

        # Step 1: Create dummy tasks for source tables (if enabled)
        if self.config.generation.include_source_tables:
            all_source_tables = set()

            # Collect all unique source tables across all models
            for model_name in target_models:
                source_tables = self.get_source_tables(model_name)
                all_source_tables.update(source_tables)

            # Create EmptyOperator for each source table
            for source_table in all_source_tables:
                # Create a clean task_id from table name using sanitize_task_id
                # This removes quotes, dots, and other invalid characters
                task_id = f"source__{sanitize_task_id(source_table)}"

                source_task = EmptyOperator(
                    task_id=task_id,
                    dag=dag,
                )

                # Store with original table name as key
                source_table_tasks[source_table] = source_task

                # Link replan task if it exists
                if recovery_anchor_task:
                    recovery_anchor_task >> source_task
                elif replan_task:
                    replan_task >> source_task
                elif health_check_task:
                    health_check_task >> source_task

                logger.debug(f"Created source table task: {task_id} for {source_table}")

            if source_table_tasks:
                logger.info(f"Created {len(source_table_tasks)} source table dummy tasks")

        # Step 2: Create a task for each SQLMesh model
        for model_name, model_info in target_models.items():
            task_id = model_info.get_task_id()

            # Create the execution function
            def make_callable(m_name, m_fqn, m_interval_minutes=None):
                def execute_model(**context):
                    from sqlmesh import Context

                    # Build context kwargs - use merged config if available
                    context_kwargs = {
                        "paths": self.config.sqlmesh.project_path,
                    }

                    # Use merged config and runtime gateway if they were created
                    if self.merged_config is not None:
                        context_kwargs["config"] = self.merged_config
                        # Use the runtime gateway name (where connections are configured)
                        if self.runtime_gateway is not None:
                            context_kwargs["gateway"] = self.runtime_gateway
                    else:
                        # Fallback to original gateway if no merged config
                        context_kwargs["gateway"] = self.config.sqlmesh.gateway

                    # Load fresh context with runtime connections
                    run_ctx = Context(**context_kwargs)

                    # Get time interval (Airflow 2.2+)
                    # data_interval_start/end provides correct time range for incremental models
                    # Falls back to execution_date for backward compatibility with Airflow < 2.2
                    start = context.get('data_interval_start') or context.get('execution_date')
                    end = context.get('data_interval_end') or context.get('execution_date')

                    # When this model's interval is COARSER than the DAG tick,
                    # the tick's data_interval window (e.g. 5 minutes on a mixed
                    # sub-hourly + hourly project) spans no full model interval.
                    # SQLMesh then returns NOTHING_TO_DO and the model's state
                    # silently freezes while the task still reports success.
                    # In that case omit start/end so SQLMesh selects the correct
                    # interval(s) from the model's own cron instead.
                    if (
                        m_interval_minutes
                        and expected_interval_minutes
                        and m_interval_minutes > expected_interval_minutes
                    ):
                        logger.info(
                            "Model %s interval (%s min) is coarser than the DAG tick "
                            "(%s min); running without an explicit window so SQLMesh "
                            "picks the due interval(s) from the model cron.",
                            m_fqn, m_interval_minutes, expected_interval_minutes,
                        )
                        start = None
                        end = None

                    # Run the model with proper time range
                    try:
                        # Build run kwargs - only include skip_audits if enabled
                        # (some SQLMesh versions may not support this parameter)
                        run_kwargs = {
                            "environment": self.config.sqlmesh.environment,
                            "select_models": [m_fqn],
                        }
                        # Only pass an explicit window when we have one. For
                        # coarser-than-tick models start/end were cleared above so
                        # SQLMesh selects the due interval(s) from the model cron.
                        if start is not None:
                            run_kwargs["start"] = start
                        if end is not None:
                            run_kwargs["end"] = end

                        # Check if skip_audits is supported by inspecting the method signature
                        import inspect
                        run_sig = inspect.signature(run_ctx.run)
                        if "skip_audits" in run_sig.parameters and self.config.generation.skip_audits:
                            run_kwargs["skip_audits"] = True

                        result = run_ctx.run(**run_kwargs)

                        if not self.config.generation.return_value:
                            return None

                        if result is None:
                            return {"status": "success", "model": m_fqn}

                        # Convert CompletionStatus enum to string for XCom serialization
                        # Airflow cannot serialize enum types, so we return a simple dict
                        return {
                            "status": result.name if hasattr(result, 'name') else str(result),
                            "value": str(result.value) if hasattr(result, 'value') else None,
                            "model": m_fqn,
                        }
                    except Exception as e:
                        error_msg = str(e)

                        # Check for "Environment not found" error
                        if "Environment" in error_msg and "was not found" in error_msg:
                            env_name = self.config.sqlmesh.environment
                            raise RuntimeError(
                                f"SQLMesh environment '{env_name}' was not found.\n\n"
                                f"🔧 SOLUTION: For Airflow production DAGs, use environment='' (empty string):\n\n"
                                f"   generator = SQLMeshDAGGenerator(\n"
                                f"       sqlmesh_project_path='/path/to/project',\n"
                                f"       gateway='prod',  # ✅ Use gateway to switch environments\n"
                                f"       # environment defaults to '' - no virtual environment\n"
                                f"   )\n\n"
                                f"   OR in YAML config:\n"
                                f"   sqlmesh:\n"
                                f"     project_path: /path/to/project\n"
                                f"     gateway: prod\n"
                                f"     environment: ''  # Empty string = no virtual environment\n\n"
                                f"📚 Why? SQLMesh environments are virtual schemas for testing changes,\n"
                                f"   not for production runs. Use 'gateway' to switch between dev/staging/prod.\n\n"
                                f"   See docs/SQLMESH_ENVIRONMENTS.md for complete explanation.\n\n"
                                f"Original error: {e}"
                            ) from e

                        # Check for Redshift catalog/3-part naming error
                        elif "does not exist" in error_msg and (
                            "redshift" in error_msg.lower() or
                            "3D000" in error_msg or  # Redshift error code for invalid catalog
                            ("." in error_msg and error_msg.count('"') >= 6)  # 3-part naming pattern
                        ):
                            raise RuntimeError(
                                f"SQLMesh catalog error (likely 3-part naming issue):\n"
                                f"{error_msg}\n\n"
                                f"🔧 SOLUTION: For Redshift (2-part naming), check your SQLMesh config.yaml:\n\n"
                                f"   gateways:\n"
                                f"     prod:\n"
                                f"       connection:\n"
                                f"         type: redshift\n"
                                f"         database: your_database_name  # ✅ Ensure this is correct!\n"
                                f"         ...\n\n"
                                f"📚 Why? Redshift uses schema.table (2-part), not catalog.schema.table (3-part).\n"
                                f"   SQLMesh automatically detects the default catalog from your connection.\n"
                                f"   Make sure your Redshift connection database is correctly configured.\n\n"
                                f"Original error: {e}"
                            ) from e

                        else:
                            # Re-raise other errors as-is
                            raise
                return execute_model

            # Create PythonOperator
            task = PythonOperator(
                task_id=task_id,
                python_callable=make_callable(
                    model_name,
                    model_info.name,
                    get_interval_frequency_minutes(model_info.interval_unit)
                    if model_info.interval_unit is not None
                    else None,
                ),
                dag=dag,
            )

            tasks[model_name] = task

        # Step 3: Set up dependencies between models
        for model_name, model_info in target_models.items():
            if model_name not in tasks:
                continue

            current_task = tasks[model_name]

            # Connect to upstream SQLMesh models
            for dep_name in model_info.dependencies:
                if dep_name in tasks:
                    tasks[dep_name] >> current_task

            # Step 4: Connect to upstream source tables
            if self.config.generation.include_source_tables:
                source_tables = self.get_source_tables(model_name)
                for source_table in source_tables:
                    if source_table in source_table_tasks:
                        source_table_tasks[source_table] >> current_task
                        logger.debug(f"Linked source table {source_table} -> {model_name}")

            # Link replan task if no other dependencies (root nodes)
            if recovery_anchor_task and not current_task.upstream_task_ids:
                recovery_anchor_task >> current_task
            elif replan_task and not current_task.upstream_task_ids:
                replan_task >> current_task
            elif health_check_task and not current_task.upstream_task_ids:
                health_check_task >> current_task

        # Step 5: Per-model downstream DAG triggers (tags and/or model_triggers map)
        # Fires only after *that* model succeeds — clean SoC for unload / notify DAGs.
        if TriggerDagRunOperator is not None:
            for model_name, model_info in target_models.items():
                if model_name not in tasks:
                    continue
                trigger_cfg = resolve_model_trigger(
                    model_name,
                    tags=model_info.tags,
                    model_triggers=self.config.generation.model_triggers,
                )
                if not trigger_cfg:
                    continue
                conf = default_trigger_conf(model_name, trigger_cfg.conf)
                tid = trigger_task_id(trigger_cfg.dag_id, model_info.get_task_id())
                op_kwargs = {
                    "task_id": tid,
                    "trigger_dag_id": trigger_cfg.dag_id,
                    "conf": conf,
                    "reset_dag_run": trigger_cfg.reset_dag_run,
                    "wait_for_completion": trigger_cfg.wait_for_completion,
                    "dag": dag,
                }
                if (
                    trigger_cfg.wait_for_completion
                    and trigger_cfg.poke_interval is not None
                ):
                    op_kwargs["poke_interval"] = trigger_cfg.poke_interval
                try:
                    trigger_op = TriggerDagRunOperator(**op_kwargs)
                except TypeError:
                    # Older Airflow may not accept all kwargs
                    op_kwargs.pop("poke_interval", None)
                    trigger_op = TriggerDagRunOperator(**op_kwargs)
                tasks[model_name] >> trigger_op
                tasks[tid] = trigger_op
                logger.info(
                    "Per-model trigger: %s -> DAG %s (task %s)",
                    model_name,
                    trigger_cfg.dag_id,
                    tid,
                )

        # Step 6: Optional pipeline-level trigger after all leaf *model* tasks
        if (
            TriggerDagRunOperator is not None
            and self.config.generation.trigger_dag_id
        ):
            leaf_names = []
            if self.dag_structure:
                leaf_names = [
                    n
                    for n in self.dag_structure.get_leaf_models()
                    if n in tasks
                ]
            else:
                deps = {
                    d
                    for info in target_models.values()
                    for d in info.dependencies
                }
                leaf_names = [n for n in target_models if n not in deps and n in tasks]
            if leaf_names:
                conf = dict(self.config.generation.trigger_dag_conf or {})
                conf.setdefault("source", "sqlmesh")
                conf.setdefault("pipeline", self.config.airflow.dag_id)
                pipeline_trigger = TriggerDagRunOperator(
                    task_id=f"trigger_{self.config.generation.trigger_dag_id}",
                    trigger_dag_id=self.config.generation.trigger_dag_id,
                    conf=conf,
                    dag=dag,
                )
                for name in leaf_names:
                    tasks[name] >> pipeline_trigger
                tasks[f"trigger_{self.config.generation.trigger_dag_id}"] = (
                    pipeline_trigger
                )
                logger.info(
                    "Pipeline-level trigger after leaves %s -> %s",
                    leaf_names,
                    self.config.generation.trigger_dag_id,
                )

        # Return all tasks (both models and source tables)
        all_tasks = {**tasks, **source_table_tasks}
        return all_tasks

    def _build_runtime_context_kwargs(self) -> Dict[str, Any]:
        """Build SQLMesh Context kwargs using merged runtime connection config when available."""
        context_kwargs = {
            "paths": self.config.sqlmesh.project_path,
        }

        if self.merged_config is not None:
            context_kwargs["config"] = self.merged_config
            if self.runtime_gateway is not None:
                context_kwargs["gateway"] = self.runtime_gateway
        else:
            context_kwargs["gateway"] = self.config.sqlmesh.gateway

        return context_kwargs

    @staticmethod
    def _coerce_bool_conf(value: Any, default: bool) -> bool:
        """Coerce dag_run.conf / config values to bool."""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def create_plan_apply_task(
        self,
        dag,
        task_id: str = "sqlmesh_plan_apply",
        execution_timeout: Optional[timedelta] = None,
        plan_only: Optional[bool] = None,
        skip_backfill: Optional[bool] = None,
    ):
        """
        Create a standalone SQLMesh plan+apply task (deploy path).

        Use this on a dedicated deploy DAG so interval/run DAGs never block on
        model changes. Hot-path pipelines should set ``auto_replan_on_change=False``
        and call only ``create_tasks_in_dag``.

        Optional ``dag_run.conf`` overrides:

        - ``plan_only``: compute plan without applying
        - ``skip_backfill``: skip apply when the plan requires backfill

        Args:
            dag: Airflow DAG object.
            task_id: Task ID for the plan/apply operator.
            execution_timeout: Optional timeout. Defaults to
                ``generation.replan_timeout_hours`` when set.
            plan_only: Override ``generation.plan_only`` for this task.
            skip_backfill: Override ``generation.skip_backfill`` for this task.

        Returns:
            PythonOperator configured for SQLMesh plan+apply.
        """
        import time

        from sqlmesh_dag_generator.airflow_compat import PythonOperator

        default_plan_only = (
            self.config.generation.plan_only if plan_only is None else plan_only
        )
        default_skip_backfill = (
            self.config.generation.skip_backfill if skip_backfill is None else skip_backfill
        )
        log_details = self.config.generation.log_plan_details

        def run_plan_apply(**context):
            """
            Optimized plan/apply:
            1. Skip apply when nothing changed
            2. Honour plan_only / skip_backfill (config or dag_run.conf)
            3. Detailed phase logging
            """
            dag_run = context.get("dag_run")
            conf = dag_run.conf if dag_run and dag_run.conf else {}

            effective_plan_only = self._coerce_bool_conf(
                conf.get("plan_only"), default_plan_only
            )
            effective_skip_backfill = self._coerce_bool_conf(
                conf.get("skip_backfill"), default_skip_backfill
            )

            start_time = time.time()

            # Ensure runtime connection merge is available for this worker.
            if self.merged_config is None:
                self.load_sqlmesh_context()

            logger.info("Phase 1/3: Loading SQLMesh context...")
            ctx_start = time.time()
            run_ctx = Context(**self._build_runtime_context_kwargs())
            ctx_duration = time.time() - ctx_start
            logger.info("Context loaded in %.2fs", ctx_duration)

            logger.info("Phase 2/3: Computing plan (checking for changes)...")
            plan_start = time.time()
            plan = run_ctx.plan(
                environment=self.config.sqlmesh.environment,
                auto_apply=False,
                no_prompts=True,
            )
            plan_duration = time.time() - plan_start
            logger.info("Plan computed in %.2fs", plan_duration)

            if log_details:
                logger.info("  - has_changes: %s", plan.has_changes)
                logger.info("  - requires_backfill: %s", plan.requires_backfill)
                if plan.new_snapshots:
                    logger.info("  - new_snapshots: %s", len(plan.new_snapshots))
                if plan.modified_snapshots:
                    logger.info("  - modified_snapshots: %s", len(plan.modified_snapshots))
                if plan.missing_intervals:
                    logger.info(
                        "  - missing_intervals: %s model(s)",
                        len(plan.missing_intervals),
                    )

            if not plan.has_changes and not plan.requires_backfill:
                total_duration = time.time() - start_time
                logger.info("No model changes detected, skipping apply")
                logger.info("Total time: %.2fs", total_duration)
                return {
                    "status": "skipped",
                    "reason": "no_changes",
                    "duration_seconds": total_duration,
                    "context_load_seconds": ctx_duration,
                    "plan_compute_seconds": plan_duration,
                }

            if effective_plan_only:
                total_duration = time.time() - start_time
                logger.info("Plan-only mode: changes detected but not applying")
                if plan.has_changes:
                    logger.info("  - Would apply model changes")
                if plan.requires_backfill:
                    logger.info("  - Would run backfill")
                logger.info("Total time: %.2fs", total_duration)
                return {
                    "status": "plan_only",
                    "reason": "plan_only_mode",
                    "has_changes": plan.has_changes,
                    "requires_backfill": plan.requires_backfill,
                    "duration_seconds": total_duration,
                }

            if effective_skip_backfill and plan.requires_backfill:
                total_duration = time.time() - start_time
                logger.warning(
                    "Backfill required but skip_backfill=True, skipping apply"
                )
                logger.info(
                    "Run plan+apply with skip_backfill=false (or CI deploy) to apply"
                )
                logger.info("Total time: %.2fs", total_duration)
                return {
                    "status": "skipped",
                    "reason": "backfill_skipped",
                    "has_changes": plan.has_changes,
                    "requires_backfill": plan.requires_backfill,
                    "duration_seconds": total_duration,
                }

            logger.info("Phase 3/3: Applying plan...")
            if plan.has_changes:
                logger.info("  - Applying model changes...")
            if plan.requires_backfill:
                logger.info("  - Running backfill (this may take a while)...")

            apply_start = time.time()
            run_ctx.apply(plan)
            apply_duration = time.time() - apply_start
            logger.info("Plan applied in %.2fs", apply_duration)

            total_duration = time.time() - start_time
            logger.info("Total time: %.2fs", total_duration)
            return {
                "status": "applied",
                "has_changes": plan.has_changes,
                "requires_backfill": plan.requires_backfill,
                "duration_seconds": total_duration,
                "context_load_seconds": ctx_duration,
                "plan_compute_seconds": plan_duration,
                "apply_seconds": apply_duration,
            }

        if execution_timeout is None:
            replan_timeout_hours = self.config.generation.replan_timeout_hours
            if replan_timeout_hours is not None:
                execution_timeout = timedelta(hours=replan_timeout_hours)

        task = PythonOperator(
            task_id=task_id,
            python_callable=run_plan_apply,
            dag=dag,
            execution_timeout=execution_timeout,
        )

        if execution_timeout is None:
            logger.info("Created plan/apply task: %s (timeout: disabled)", task_id)
        else:
            logger.info(
                "Created plan/apply task: %s (timeout: %s)",
                task_id,
                execution_timeout,
            )
        return task

    @staticmethod
    def _parse_manual_backfill_datetime(value: Union[str, datetime], field_name: str) -> datetime:
        """Parse a manual backfill boundary into a timezone-aware UTC datetime."""
        if isinstance(value, datetime):
            parsed = value
        else:
            raw_value = str(value).strip()
            if not raw_value:
                raise ValueError(f"Manual backfill requires a non-empty '{field_name}' value.")
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _normalize_manual_backfill_models(
        raw_models: Optional[Union[str, List[str]]]
    ) -> Optional[List[str]]:
        """Normalize manual backfill model selection into a list of model names."""
        if raw_models is None:
            return None
        if isinstance(raw_models, str):
            return [raw_models]
        if not isinstance(raw_models, list) or not all(isinstance(model, str) for model in raw_models):
            raise ValueError("Manual backfill 'models' must be a string or a list of model names.")
        if not raw_models:
            raise ValueError("Manual backfill 'models' cannot be an empty list.")
        return raw_models

    def create_manual_backfill_task(
        self,
        dag,
        task_id: str = "sqlmesh_manual_backfill",
        default_start: Optional[Union[str, datetime]] = None,
        default_end: Optional[Union[str, datetime]] = None,
        default_models: Optional[Union[str, List[str]]] = None,
        execution_timeout: Optional[timedelta] = None,
    ):
        """
        Create a manual SQLMesh backfill task for ad hoc historical replay.

        The returned task reads optional overrides from ``dag_run.conf``:

        - ``start``: ISO-8601 start boundary
        - ``end``: ISO-8601 end boundary (defaults to current UTC time when omitted)
        - ``models``: single model name or list of model names to replay

        Args:
            dag: Airflow DAG object.
            task_id: Task ID for the manual backfill operator.
            default_start: Default start boundary when ``dag_run.conf.start`` is omitted.
            default_end: Default end boundary when ``dag_run.conf.end`` is omitted.
            default_models: Optional default model selection.
            execution_timeout: Optional Airflow execution timeout for the task.

        Returns:
            PythonOperator configured for manual SQLMesh backfill.
        """
        from airflow.exceptions import AirflowException

        from sqlmesh_dag_generator.airflow_compat import PythonOperator

        normalized_default_models = self._normalize_manual_backfill_models(default_models)

        def run_manual_backfill(**context):
            dag_run = context.get("dag_run")
            conf = dag_run.conf if dag_run and dag_run.conf else {}

            requested_start = conf.get("start", default_start)
            requested_end = conf.get("end", default_end)
            requested_models = conf.get("models", normalized_default_models)

            if requested_start is None:
                raise AirflowException(
                    "Manual backfill requires a start boundary. Provide default_start or dag_run.conf['start']."
                )

            try:
                backfill_start = self._parse_manual_backfill_datetime(requested_start, "start")
                if requested_end is None:
                    backfill_end = datetime.now(timezone.utc).replace(microsecond=0)
                else:
                    backfill_end = self._parse_manual_backfill_datetime(requested_end, "end")
                selected_models = self._normalize_manual_backfill_models(requested_models)
            except ValueError as exc:
                raise AirflowException(str(exc)) from exc

            if backfill_start >= backfill_end:
                raise AirflowException(
                    f"Manual backfill start must be earlier than end. Got {backfill_start} >= {backfill_end}."
                )

            logger.info(
                "Starting manual SQLMesh backfill for %s -> %s (models=%s)",
                backfill_start,
                backfill_end,
                selected_models or "ALL",
            )

            self.load_sqlmesh_context()
            if selected_models is not None:
                if not self.models:
                    self.extract_models()
                unknown_models = sorted(set(selected_models) - set(self.models))
                if unknown_models:
                    raise AirflowException(
                        f"Unknown SQLMesh models requested for manual backfill: {unknown_models}"
                    )

            run_ctx = Context(**self._build_runtime_context_kwargs())

            run_kwargs = {
                "environment": self.config.sqlmesh.environment,
                "start": backfill_start,
                "end": backfill_end,
            }
            if selected_models is not None:
                run_kwargs["select_models"] = selected_models

            run_sig = inspect.signature(run_ctx.run)
            if "skip_audits" in run_sig.parameters and self.config.generation.skip_audits:
                run_kwargs["skip_audits"] = True

            result = run_ctx.run(**run_kwargs)
            status = result.name if hasattr(result, "name") else str(result)
            logger.info("Manual SQLMesh backfill finished with status: %s", status)

            return {
                "status": status,
                "start": backfill_start.isoformat(),
                "end": backfill_end.isoformat(),
                "models": selected_models or "ALL",
            }

        return PythonOperator(
            task_id=task_id,
            python_callable=run_manual_backfill,
            execution_timeout=execution_timeout,
            dag=dag,
        )

    def _get_output_path(self) -> Path:
        """Get the output file path for the generated DAG"""
        output_dir = Path(self.config.generation.output_dir)
        filename = f"{self.config.airflow.dag_id}.py"
        return output_dir / filename

    def validate(self) -> bool:
        """
        Validate the SQLMesh project and configuration.

        Returns:
            True if validation passes
        """
        logger.info("Validating SQLMesh project and configuration")

        # Check project path exists
        project_path = Path(self.config.sqlmesh.project_path)
        if not project_path.exists():
            logger.error(f"SQLMesh project path does not exist: {project_path}")
            return False

        # Try to load context
        try:
            self.load_sqlmesh_context()
        except Exception as e:
            logger.error(f"Failed to load SQLMesh context: {e}")
            return False

        # Check for models
        try:
            models = self.extract_models()
            if not models:
                logger.warning("No models found in SQLMesh project")
                return False
        except Exception as e:
            logger.error(f"Failed to extract models: {e}")
            return False

        logger.info("Validation passed")
        return True

