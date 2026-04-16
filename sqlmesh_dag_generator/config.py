"""
Configuration module for SQLMesh DAG Generator
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml


@dataclass
class SQLMeshConfig:
    """
    SQLMesh project configuration

    Important: Use 'gateway' to switch between environments (dev/staging/prod),
    NOT the 'environment' parameter which is deprecated.

    Runtime Connection Configuration:
        You can pass connection parameters at runtime to avoid hardcoding credentials:

        config = SQLMeshConfig(
            project_path="/path/to/project",
            gateway="prod",
            connection_config={
                "type": "postgres",
                "host": "{{ conn.postgres_default.host }}",
                "user": "{{ conn.postgres_default.login }}",
                ...
            }
        )

    Example:
        # ✅ CORRECT - Use gateway
        config = SQLMeshConfig(
            project_path="/path/to/project",
            gateway="prod"  # This selects your environment
        )

        # ❌ DEPRECATED - Don't use environment
        config = SQLMeshConfig(
            project_path="/path/to/project",
            environment="some_env"  # This creates SQLMesh virtual environment
        )

        # For production without virtual environments, use empty string (default):
        config = SQLMeshConfig(
            project_path="/path/to/project",
            environment=""  # No virtual env - uses main schemas directly
        )
    """
    project_path: str
    environment: str = ""  # Empty string = no virtual environment (production mode)
    gateway: Optional[str] = None
    config_path: Optional[str] = None
    connection_config: Optional[Dict[str, Any]] = None  # Runtime connection parameters
    state_connection_config: Optional[Dict[str, Any]] = None  # Runtime state connection parameters
    default_catalog: Optional[str] = None  # Default catalog for 3-part naming
    config_overrides: Dict[str, Any] = field(default_factory=dict)  # Any other SQLMesh config overrides

    def __post_init__(self):
        """Validate configuration and show deprecation warnings"""
        import warnings

        # Warn if environment is set to a named environment (not empty string)
        # This is likely a misconfiguration - users probably meant to use 'gateway' instead
        if self.environment and self.environment != "":
            warnings.warn(
                f"\n{'='*80}\n"
                f"⚠️  WARNING: environment='{self.environment}' detected!\n\n"
                f"SQLMesh 'environment' is a VIRTUAL ENVIRONMENT for testing changes,\n"
                f"not a way to switch between dev/staging/prod.\n\n"
                f"For Airflow production DAGs, you probably want:\n"
                f"  ✅ gateway='{self.environment}'  # To switch between dev/staging/prod\n"
                f"  ✅ environment=''  # Empty string (default) for production runs\n\n"
                f"Current config will try to run against virtual environment '{self.environment}'.\n"
                f"If this environment doesn't exist, you'll get: \"Environment '{self.environment}' was not found\"\n\n"
                f"📚 See docs/SQLMESH_ENVIRONMENTS.md for complete explanation.\n"
                f"{'='*80}\n",
                UserWarning,
                stacklevel=2
            )


@dataclass
class RecoveryConfig:
    """Optional runtime recovery behavior for missed Airflow intervals."""
    mode: str = "bounded_auto"  # disabled, warn, bounded_auto
    max_intervals: int = 6
    fail_on_excess_gap: bool = False

    def __post_init__(self):
        valid_modes = {"disabled", "warn", "bounded_auto"}
        if self.mode not in valid_modes:
            raise ValueError(
                f"Unsupported recovery mode: {self.mode}. "
                f"Must be one of: {sorted(valid_modes)}"
            )
        if self.max_intervals < 1:
            raise ValueError("recovery.max_intervals must be >= 1")


@dataclass
class AirflowConfig:
    """Airflow DAG configuration"""
    dag_id: str
    schedule_interval: Optional[str] = None
    auto_schedule: bool = True  # Automatically detect schedule from SQLMesh models
    start_date: Optional[str] = None  # ISO format: "2024-01-01" or use "days_ago(1)"
    default_args: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    catchup: bool = False
    max_active_runs: int = 1
    description: Optional[str] = None
    env_vars: Dict[str, str] = field(default_factory=dict)  # Environment variables for tasks
    # Callback configuration - pass callable names (will be imported in generated DAG)
    on_failure_callback: Optional[str] = None  # e.g., "my_module.slack_alert"
    on_success_callback: Optional[str] = None  # e.g., "my_module.log_success"
    sla_miss_callback: Optional[str] = None  # e.g., "my_module.sla_alert"
    sla: Optional[int] = None  # SLA in seconds for all tasks
    recovery: RecoveryConfig = field(default_factory=RecoveryConfig)


@dataclass
class GenerationConfig:
    """DAG generation settings"""
    output_dir: str = "./dags"
    mode: str = "dynamic"  # "static" or "dynamic" - dynamic is default (fire & forget!)
    operator_type: str = "python"  # python, bash, or kubernetes
    docker_image: Optional[str] = None  # Required for kubernetes operator
    namespace: str = "default"  # Kubernetes namespace for KubernetesPodOperator
    include_tests: bool = False
    parallel_tasks: bool = True
    max_parallel_tasks: Optional[int] = None
    include_models: Optional[List[str]] = None
    exclude_models: Optional[List[str]] = None
    model_pattern: Optional[str] = None
    dry_run: bool = False
    include_source_tables: bool = True  # Include upstream source tables as dummy tasks
    return_value: bool = True  # Whether to return execution result (XCom)
    auto_replan_on_change: bool = True  # Automatically plan+apply before running models
    replan_timeout_hours: Optional[int] = 6  # None disables the replan task timeout.
    skip_audits: bool = False  # Skip audit checks during execution
    enable_health_check: bool = False  # Add a pre-flight health check task
    # Tag-based filtering - only include models with any of these tags
    include_tags: Optional[List[str]] = None  # e.g., ["finance", "core"]
    exclude_tags: Optional[List[str]] = None  # e.g., ["deprecated", "test"]
    # Resource management
    pool: Optional[str] = None  # Airflow pool for all tasks
    pool_slots: int = 1  # Number of pool slots per task
    # Trigger downstream DAG after completion
    trigger_dag_id: Optional[str] = None  # DAG to trigger on success
    trigger_dag_conf: Optional[Dict[str, Any]] = None  # Conf to pass to triggered DAG
    # Plan optimization options (for auto_replan_on_change)
    skip_backfill: bool = False  # Skip apply if backfill is required (use with CI/CD deploys)
    plan_only: bool = False  # Generate plan without applying (for review/dry-run)
    log_plan_details: bool = True  # Log detailed plan information (snapshots, intervals)


@dataclass
class DAGGeneratorConfig:
    """Complete configuration for DAG generator"""
    sqlmesh: SQLMeshConfig
    airflow: AirflowConfig
    generation: GenerationConfig = field(default_factory=GenerationConfig)

    @classmethod
    def from_file(cls, config_path: str) -> "DAGGeneratorConfig":
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        return cls(
            sqlmesh=SQLMeshConfig(**config_data.get("sqlmesh", {})),
            airflow=cls._build_airflow_config(config_data.get("airflow", {})),
            generation=GenerationConfig(**config_data.get("generation", {})),
        )

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "DAGGeneratorConfig":
        """Load configuration from dictionary"""
        return cls(
            sqlmesh=SQLMeshConfig(**config_dict.get("sqlmesh", {})),
            airflow=cls._build_airflow_config(config_dict.get("airflow", {})),
            generation=GenerationConfig(**config_dict.get("generation", {})),
        )

    @staticmethod
    def _build_airflow_config(config_dict: Dict[str, Any]) -> AirflowConfig:
        """Build AirflowConfig, including nested recovery settings."""
        airflow_dict = dict(config_dict or {})
        recovery_dict = airflow_dict.pop("recovery", None) or {}
        airflow_dict["recovery"] = RecoveryConfig(**recovery_dict)
        return AirflowConfig(**airflow_dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "sqlmesh": {
                "project_path": self.sqlmesh.project_path,
                "environment": self.sqlmesh.environment,
                "gateway": self.sqlmesh.gateway,
                "config_path": self.sqlmesh.config_path,
                "connection_config": self.sqlmesh.connection_config,
                "state_connection_config": self.sqlmesh.state_connection_config,
                "default_catalog": self.sqlmesh.default_catalog,
                "config_overrides": self.sqlmesh.config_overrides,
            },
            "airflow": {
                "dag_id": self.airflow.dag_id,
                "schedule_interval": self.airflow.schedule_interval,
                "auto_schedule": self.airflow.auto_schedule,
                "start_date": self.airflow.start_date,
                "default_args": self.airflow.default_args,
                "tags": self.airflow.tags,
                "catchup": self.airflow.catchup,
                "max_active_runs": self.airflow.max_active_runs,
                "description": self.airflow.description,
                "env_vars": self.airflow.env_vars,
                "on_failure_callback": self.airflow.on_failure_callback,
                "on_success_callback": self.airflow.on_success_callback,
                "sla_miss_callback": self.airflow.sla_miss_callback,
                "sla": self.airflow.sla,
                "recovery": {
                    "mode": self.airflow.recovery.mode,
                    "max_intervals": self.airflow.recovery.max_intervals,
                    "fail_on_excess_gap": self.airflow.recovery.fail_on_excess_gap,
                },
            },
            "generation": {
                "output_dir": self.generation.output_dir,
                "mode": self.generation.mode,
                "operator_type": self.generation.operator_type,
                "docker_image": self.generation.docker_image,
                "namespace": self.generation.namespace,
                "include_tests": self.generation.include_tests,
                "parallel_tasks": self.generation.parallel_tasks,
                "max_parallel_tasks": self.generation.max_parallel_tasks,
                "include_models": self.generation.include_models,
                "exclude_models": self.generation.exclude_models,
                "model_pattern": self.generation.model_pattern,
                "dry_run": self.generation.dry_run,
                "include_source_tables": self.generation.include_source_tables,
                "return_value": self.generation.return_value,
                "auto_replan_on_change": self.generation.auto_replan_on_change,
                "replan_timeout_hours": self.generation.replan_timeout_hours,
                "skip_audits": self.generation.skip_audits,
                "enable_health_check": self.generation.enable_health_check,
                "include_tags": self.generation.include_tags,
                "exclude_tags": self.generation.exclude_tags,
                "pool": self.generation.pool,
                "pool_slots": self.generation.pool_slots,
                "trigger_dag_id": self.generation.trigger_dag_id,
                "trigger_dag_conf": self.generation.trigger_dag_conf,
                "skip_backfill": self.generation.skip_backfill,
                "plan_only": self.generation.plan_only,
                "log_plan_details": self.generation.log_plan_details,
            },
        }

    def save(self, output_path: str) -> None:
        """Save configuration to YAML file"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

