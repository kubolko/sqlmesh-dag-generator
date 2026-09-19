"""
Configuration module for SQLMesh DAG Generator
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from sqlmesh_dag_generator.triggers import (
    ModelTriggerConfig,
    normalize_model_triggers,
)


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
        # CORRECT - Use gateway
        config = SQLMeshConfig(
            project_path="/path/to/project",
            gateway="prod"  # This selects your environment
        )

        # DEPRECATED - Don't use environment
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
    config_overrides: Dict[str, Any] = field(
        default_factory=dict
    )  # Any other SQLMesh config overrides

    def __post_init__(self):
        """Validate configuration and show deprecation warnings"""
        import warnings

        # Warn if environment is set to a named environment (not empty string)
        # This is likely a misconfiguration - users probably meant to use 'gateway' instead
        if self.environment and self.environment != "":
            warnings.warn(
                f"\n{'='*80}\n"
                f"WARNING: environment='{self.environment}' detected!\n\n"
                f"SQLMesh 'environment' is a VIRTUAL ENVIRONMENT for testing changes,\n"
                f"not a way to switch between dev/staging/prod.\n\n"
                f"For Airflow production DAGs, you probably want:\n"
                f"  gateway='{self.environment}'  # To switch between dev/staging/prod\n"
                f"  environment=''  # Empty string (default) for production runs\n\n"
                f"Current config will try to run against virtual environment '{self.environment}'.\n"
                f"If this environment doesn't exist, you'll get: \"Environment '{self.environment}' was not found\"\n\n"
                f"See docs/ENVIRONMENTS.md for complete explanation.\n"
                f"{'='*80}\n",
                UserWarning,
                stacklevel=2,
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
                f"Unsupported recovery mode: {self.mode}. " f"Must be one of: {sorted(valid_modes)}"
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
class TaskOverride:
    """
    Airflow task settings for the models matched by a selection.

    The dbt equivalent is the ``models:`` config tree in ``dbt_project.yml``:
    instead of repeating operator kwargs per model, you attach them to a
    selection ("everything tagged heavy runs in the heavy pool, with a 2h timeout").
    """

    select: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    pool: Optional[str] = None
    pool_slots: Optional[int] = None
    queue: Optional[str] = None
    retries: Optional[int] = None
    retry_delay_minutes: Optional[int] = None
    execution_timeout_minutes: Optional[int] = None
    priority_weight: Optional[int] = None
    max_active_tis_per_dag: Optional[int] = None
    sla_minutes: Optional[int] = None
    trigger_rule: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.select, str):
            self.select = [self.select]
        if isinstance(self.exclude, str):
            self.exclude = [self.exclude]
        if not self.select and not self.exclude:
            raise ValueError("A task override needs a 'select' (or at least an 'exclude')")

    def operator_kwargs(self) -> Dict[str, Any]:
        """Translate the override into Airflow operator kwargs."""
        from datetime import timedelta

        kwargs: Dict[str, Any] = {}
        if self.pool is not None:
            kwargs["pool"] = self.pool
        if self.pool_slots is not None:
            kwargs["pool_slots"] = self.pool_slots
        if self.queue is not None:
            kwargs["queue"] = self.queue
        if self.retries is not None:
            kwargs["retries"] = self.retries
        if self.retry_delay_minutes is not None:
            kwargs["retry_delay"] = timedelta(minutes=self.retry_delay_minutes)
        if self.execution_timeout_minutes is not None:
            kwargs["execution_timeout"] = timedelta(minutes=self.execution_timeout_minutes)
        if self.priority_weight is not None:
            kwargs["priority_weight"] = self.priority_weight
        if self.max_active_tis_per_dag is not None:
            kwargs["max_active_tis_per_dag"] = self.max_active_tis_per_dag
        if self.sla_minutes is not None:
            kwargs["sla"] = timedelta(minutes=self.sla_minutes)
        if self.trigger_rule is not None:
            kwargs["trigger_rule"] = self.trigger_rule
        return kwargs


@dataclass
class DAGGroupConfig:
    """
    One DAG carved out of a SQLMesh project by a selection.

    A project is rarely one pipeline: finance models run hourly and page the
    on-call, marketing models run nightly and nobody cares. A group turns each
    of those lineages into its own Airflow DAG, with its own schedule and its
    own alerting, while SQLMesh keeps a single model graph.
    """

    dag_id: str
    select: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    schedule: Optional[str] = None  # None = auto-detect from the group's models
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    catchup: Optional[bool] = None
    max_active_runs: Optional[int] = None
    start_date: Optional[str] = None
    default_args: Optional[Dict[str, Any]] = None
    # How a group depends on models owned by another group:
    #   "dataset" - upstream models emit Airflow Datasets, this DAG is scheduled on them
    #   "sensor"  - ExternalTaskSensor on the upstream group's task
    #   "none"    - cross-group edges are only logged
    wait_for_upstream: str = "dataset"
    sensor_timeout_minutes: int = 60
    sensor_poke_interval_seconds: int = 60
    # Group-level overrides of generation settings (e.g. auto_replan_on_change)
    generation_overrides: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.select, str):
            self.select = [self.select]
        if isinstance(self.exclude, str):
            self.exclude = [self.exclude]
        valid = {"dataset", "sensor", "none"}
        if self.wait_for_upstream not in valid:
            raise ValueError(
                f"Unsupported wait_for_upstream: {self.wait_for_upstream}. "
                f"Must be one of: {sorted(valid)}"
            )


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
    # Trigger downstream DAG after completion of *all leaf* models (pipeline-level)
    trigger_dag_id: Optional[str] = None  # DAG to trigger on success
    trigger_dag_conf: Optional[Dict[str, Any]] = None  # Conf to pass to triggered DAG
    # Per-model triggers (model FQN -> dag id / ModelTriggerConfig / dict).
    # Also discoverable via SQLMesh tags: trigger_dag:<id>, trigger_conf:k=v
    # Explicit map wins over tags. See sqlmesh_dag_generator.triggers.
    model_triggers: Dict[str, Union[str, Dict[str, Any], ModelTriggerConfig]] = field(
        default_factory=dict
    )
    # Plan optimization options (for auto_replan_on_change)
    skip_backfill: bool = False  # Skip apply if backfill is required (use with CI/CD deploys)
    plan_only: bool = False  # Generate plan without applying (for review/dry-run)
    log_plan_details: bool = True  # Log detailed plan information (snapshots, intervals)
    # Mixed-cadence DAGs (schedule = min model interval): coarser models still get a
    # task every tick. When True (default), those tasks return skipped/not_due *before*
    # loading SQLMesh Context — avoids tens of seconds of no-op cost per tick.
    skip_if_not_due: bool = True
    # dbt-style selection, evaluated against the model graph. Understands
    # "tag:finance+", "+path:models/marts", "kind:INCREMENTAL*", "selector:<name>", ...
    # See sqlmesh_dag_generator.selectors. include_models/exclude_models still work
    # and are applied on top of these.
    select: Optional[List[str]] = None
    exclude: Optional[List[str]] = None
    # Per-selection task settings, applied in order (later entries win):
    #   - select: ["tag:heavy"]
    #     pool: heavy, retries: 5, execution_timeout_minutes: 120
    task_overrides: List[Union[Dict[str, Any], "TaskOverride"]] = field(default_factory=list)
    # Emit an Airflow Dataset/Asset per model task, so other DAGs can be scheduled
    # on model completion instead of on a clock.
    emit_datasets: bool = False
    dataset_uri_prefix: str = "sqlmesh://models/"
    # Copy SQLMesh model metadata (owner, description, tags, audits) onto the tasks
    # so the Airflow UI shows what the model actually is.
    model_docs: bool = True
    # Run the model's SQLMesh audits in a dedicated task after the model task.
    audit_tasks: bool = False
    # Pass no_auto_upstream=True to Context.run (SQLMesh 0.230+). Recommended:
    # Airflow already schedules the upstream models as their own tasks, so letting
    # SQLMesh chase upstream again duplicates work. Off by default to keep the
    # behaviour of existing DAGs unchanged.
    no_auto_upstream: bool = False

    def __post_init__(self) -> None:
        # Normalize model_triggers so consumers always see ModelTriggerConfig
        self.model_triggers = normalize_model_triggers(self.model_triggers)  # type: ignore[assignment]
        self.task_overrides = [
            override if isinstance(override, TaskOverride) else TaskOverride(**override)
            for override in (self.task_overrides or [])
        ]


@dataclass
class DAGGeneratorConfig:
    """Complete configuration for DAG generator"""

    sqlmesh: SQLMeshConfig
    airflow: AirflowConfig
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    # Named selections, reusable from select/exclude as "selector:<name>"
    # (the dbt selectors.yml idea, kept in the same file).
    selectors: Dict[str, Any] = field(default_factory=dict)
    # One SQLMesh project, several DAGs - see DAGGroupConfig.
    dag_groups: List[DAGGroupConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.dag_groups = [
            group if isinstance(group, DAGGroupConfig) else DAGGroupConfig(**group)
            for group in (self.dag_groups or [])
        ]
        duplicates = {
            g.dag_id
            for g in self.dag_groups
            if [x.dag_id for x in self.dag_groups].count(g.dag_id) > 1
        }
        if duplicates:
            raise ValueError(f"Duplicate dag_group dag_id(s): {sorted(duplicates)}")

    def group(self, dag_id: str) -> DAGGroupConfig:
        """Look up a DAG group by id (raises with the known ids when missing)."""
        for group in self.dag_groups:
            if group.dag_id == dag_id:
                return group
        known = ", ".join(g.dag_id for g in self.dag_groups) or "(none defined)"
        raise KeyError(f"Unknown dag_group '{dag_id}'. Defined groups: {known}")

    @classmethod
    def from_file(cls, config_path: str) -> "DAGGeneratorConfig":
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        return cls.from_dict(config_data or {})

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "DAGGeneratorConfig":
        """Load configuration from dictionary"""
        return cls(
            sqlmesh=SQLMeshConfig(**config_dict.get("sqlmesh", {})),
            airflow=cls._build_airflow_config(config_dict.get("airflow", {})),
            generation=cls._build_generation_config(config_dict.get("generation", {})),
            selectors=dict(config_dict.get("selectors") or {}),
            dag_groups=list(config_dict.get("dag_groups") or []),
        )

    @staticmethod
    def _build_airflow_config(config_dict: Dict[str, Any]) -> AirflowConfig:
        """Build AirflowConfig, including nested recovery settings."""
        airflow_dict = dict(config_dict or {})
        recovery_dict = airflow_dict.pop("recovery", None) or {}
        airflow_dict["recovery"] = RecoveryConfig(**recovery_dict)
        return AirflowConfig(**airflow_dict)

    @staticmethod
    def _build_generation_config(config_dict: Dict[str, Any]) -> GenerationConfig:
        """Build GenerationConfig (normalizes model_triggers)."""
        gen = dict(config_dict or {})
        # Leave model_triggers as-is; GenerationConfig.__post_init__ normalizes
        return GenerationConfig(**gen)

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
                "model_triggers": {
                    name: (
                        {
                            "dag_id": getattr(cfg, "dag_id", cfg),
                            "conf": getattr(cfg, "conf", {}) or {},
                            "wait_for_completion": getattr(cfg, "wait_for_completion", False),
                            "reset_dag_run": getattr(cfg, "reset_dag_run", False),
                            "poke_interval": getattr(cfg, "poke_interval", None),
                        }
                        if not isinstance(cfg, str)
                        else {"dag_id": cfg, "conf": {}}
                    )
                    for name, cfg in (self.generation.model_triggers or {}).items()
                },
                "skip_backfill": self.generation.skip_backfill,
                "plan_only": self.generation.plan_only,
                "log_plan_details": self.generation.log_plan_details,
                "skip_if_not_due": self.generation.skip_if_not_due,
                "select": self.generation.select,
                "exclude": self.generation.exclude,
                "task_overrides": [asdict(o) for o in self.generation.task_overrides],
                "emit_datasets": self.generation.emit_datasets,
                "dataset_uri_prefix": self.generation.dataset_uri_prefix,
                "model_docs": self.generation.model_docs,
                "audit_tasks": self.generation.audit_tasks,
                "no_auto_upstream": self.generation.no_auto_upstream,
            },
            "selectors": dict(self.selectors or {}),
            "dag_groups": [asdict(g) for g in self.dag_groups],
        }

    def save(self, output_path: str) -> None:
        """Save configuration to YAML file"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
