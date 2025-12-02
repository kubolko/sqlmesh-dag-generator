"""
Configuration module for SQLMesh DAG Generator
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml


@dataclass
class SQLMeshConfig:
    """SQLMesh project configuration"""
    project_path: str
    environment: str = "prod"
    gateway: Optional[str] = None
    config_path: Optional[str] = None


@dataclass
class AirflowConfig:
    """Airflow DAG configuration"""
    dag_id: str
    schedule_interval: Optional[str] = None
    start_date: Optional[str] = None  # ISO format: "2024-01-01" or use "days_ago(1)"
    default_args: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    catchup: bool = False
    max_active_runs: int = 1
    description: Optional[str] = None
    env_vars: Dict[str, str] = field(default_factory=dict)  # Environment variables for tasks


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

        with open(config_file, "r") as f:
            config_data = yaml.safe_load(f)

        return cls(
            sqlmesh=SQLMeshConfig(**config_data.get("sqlmesh", {})),
            airflow=AirflowConfig(**config_data.get("airflow", {})),
            generation=GenerationConfig(**config_data.get("generation", {})),
        )

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "DAGGeneratorConfig":
        """Load configuration from dictionary"""
        return cls(
            sqlmesh=SQLMeshConfig(**config_dict.get("sqlmesh", {})),
            airflow=AirflowConfig(**config_dict.get("airflow", {})),
            generation=GenerationConfig(**config_dict.get("generation", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "sqlmesh": {
                "project_path": self.sqlmesh.project_path,
                "environment": self.sqlmesh.environment,
                "gateway": self.sqlmesh.gateway,
                "config_path": self.sqlmesh.config_path,
            },
            "airflow": {
                "dag_id": self.airflow.dag_id,
                "schedule_interval": self.airflow.schedule_interval,
                "default_args": self.airflow.default_args,
                "tags": self.airflow.tags,
                "catchup": self.airflow.catchup,
                "max_active_runs": self.airflow.max_active_runs,
                "description": self.airflow.description,
            },
            "generation": {
                "output_dir": self.generation.output_dir,
                "operator_type": self.generation.operator_type,
                "include_tests": self.generation.include_tests,
                "parallel_tasks": self.generation.parallel_tasks,
                "max_parallel_tasks": self.generation.max_parallel_tasks,
                "include_models": self.generation.include_models,
                "exclude_models": self.generation.exclude_models,
                "model_pattern": self.generation.model_pattern,
                "dry_run": self.generation.dry_run,
            },
        }

    def save(self, output_path: str) -> None:
        """Save configuration to YAML file"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

