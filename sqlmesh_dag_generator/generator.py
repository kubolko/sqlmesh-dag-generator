"""
Core DAG generator module
"""
import logging
from pathlib import Path
from typing import Dict, Optional

from sqlmesh import Context
from sqlmesh.core.model import Model

from sqlmesh_dag_generator.config import DAGGeneratorConfig, SQLMeshConfig, AirflowConfig, GenerationConfig
from sqlmesh_dag_generator.models import SQLMeshModelInfo, DAGStructure
from sqlmesh_dag_generator.dag_builder import AirflowDAGBuilder

logger = logging.getLogger(__name__)


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
        config: Optional[DAGGeneratorConfig] = None,
        **kwargs
    ):
        """
        Initialize the DAG generator.

        Args:
            sqlmesh_project_path: Path to SQLMesh project
            dag_id: Airflow DAG ID
            schedule_interval: Airflow schedule interval
            config: Full DAGGeneratorConfig object
            **kwargs: Additional configuration options
        """
        if config:
            self.config = config
        else:
            # Build config from individual parameters
            sqlmesh_config = SQLMeshConfig(
                project_path=sqlmesh_project_path or "./",
                environment=kwargs.get("environment", "prod"),
                gateway=kwargs.get("gateway"),
            )

            airflow_config = AirflowConfig(
                dag_id=dag_id or "sqlmesh_dag",
                schedule_interval=schedule_interval,
                default_args=kwargs.get("default_args", {}),
                tags=kwargs.get("tags", ["sqlmesh"]),
                catchup=kwargs.get("catchup", False),
                max_active_runs=kwargs.get("max_active_runs", 1),
            )

            generation_config = GenerationConfig(
                output_dir=kwargs.get("output_dir", "./dags"),
                operator_type=kwargs.get("operator_type", "python"),
                include_tests=kwargs.get("include_tests", False),
                parallel_tasks=kwargs.get("parallel_tasks", True),
                include_models=kwargs.get("include_models"),
                exclude_models=kwargs.get("exclude_models"),
            )

            self.config = DAGGeneratorConfig(
                sqlmesh=sqlmesh_config,
                airflow=airflow_config,
                generation=generation_config,
            )

        self.context: Optional[Context] = None
        self.models: Dict[str, SQLMeshModelInfo] = {}
        self.dag_structure: Optional[DAGStructure] = None

    def load_sqlmesh_context(self) -> Context:
        """
        Load the SQLMesh context from the project path.

        Returns:
            SQLMesh Context object
        """
        logger.info(f"Loading SQLMesh context from: {self.config.sqlmesh.project_path}")

        try:
            self.context = Context(
                paths=self.config.sqlmesh.project_path,
                gateway=self.config.sqlmesh.gateway,
                config=self.config.sqlmesh.config_path,
            )
            logger.info(f"Successfully loaded SQLMesh context")
            return self.context
        except Exception as e:
            logger.error(f"Failed to load SQLMesh context: {e}")
            raise

    def extract_models(self) -> Dict[str, SQLMeshModelInfo]:
        """
        Extract model information from SQLMesh context.

        Returns:
            Dictionary mapping model names to SQLMeshModelInfo objects
        """
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
            # Filter models based on include/exclude patterns
            if not self._should_include_model(model_name):
                continue

            model_info = self._extract_model_info(model_name, model)
            models[model_name] = model_info
            logger.debug(f"Extracted model: {model_name}")

        self.models = models
        logger.info(f"Extracted {len(models)} models")
        return models

    def _should_include_model(self, model_name: str) -> bool:
        """Check if a model should be included based on filters"""
        # Check include patterns
        if self.config.generation.include_models:
            if model_name not in self.config.generation.include_models:
                return False

        # Check exclude patterns
        if self.config.generation.exclude_models:
            if model_name in self.config.generation.exclude_models:
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
        # Extract dependencies
        dependencies = set()
        if hasattr(model, 'depends_on'):
            dependencies = model.depends_on
        elif hasattr(model, 'dependencies'):
            dependencies = model.dependencies

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

    def build_dag_structure(self) -> DAGStructure:
        """
        Build the DAG structure from extracted models.

        Returns:
            DAGStructure object representing the task graph
        """
        if not self.models:
            self.extract_models()

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

        if not self.dag_structure:
            self.build_dag_structure()

        # Build the DAG
        dag_builder = AirflowDAGBuilder(self.config, self.dag_structure)
        dag_code = dag_builder.build()

        # Save to file if not dry run
        if not self.config.generation.dry_run:
            output_path = self._get_output_path()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w") as f:
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

            with open(output_path, "w") as f:
                f.write(dag_code)

            logger.info(f"Dynamic DAG file written to: {output_path}")
            logger.info("📌 Place this file in Airflow's dags/ folder and forget about it!")
            logger.info("   The DAG will automatically discover SQLMesh models at runtime.")

        return dag_code

    def create_tasks_in_dag(self, dag):
        """
        Create Airflow tasks directly inside a DAG context.

        This method is designed to be called inside a DAG definition:

        Example:
            with DAG(...) as dag:
                generator = SQLMeshDAGGenerator(...)
                generator.create_tasks_in_dag(dag)

        Args:
            dag: Airflow DAG object

        Returns:
            Dictionary of created tasks {model_name: task}
        """
        from airflow.operators.python import PythonOperator

        # Load models if not already loaded
        if not self.models:
            self.extract_models()

        tasks = {}

        # Create a task for each model
        for model_name, model_info in self.models.items():
            task_id = model_info.get_task_id()

            # Create the execution function
            def make_callable(m_name, m_fqn):
                def execute_model(**context):
                    from sqlmesh import Context

                    # Load fresh context
                    run_ctx = Context(
                        paths=self.config.sqlmesh.project_path,
                        gateway=self.config.sqlmesh.gateway,
                    )

                    # Get time interval (Airflow 2.2+)
                    # data_interval_start/end provides correct time range for incremental models
                    # Falls back to execution_date for backward compatibility with Airflow < 2.2
                    start = context.get('data_interval_start') or context.get('execution_date')
                    end = context.get('data_interval_end') or context.get('execution_date')

                    # Run the model with proper time range
                    return run_ctx.run(
                        environment=self.config.sqlmesh.environment,
                        start=start,
                        end=end,
                        select_models=[m_fqn],
                    )
                return execute_model

            # Create PythonOperator
            task = PythonOperator(
                task_id=task_id,
                python_callable=make_callable(model_name, model_info.name),
                dag=dag,
            )

            tasks[model_name] = task

        # Set up dependencies
        for model_name, model_info in self.models.items():
            if model_name not in tasks:
                continue

            current_task = tasks[model_name]

            for dep_name in model_info.dependencies:
                if dep_name in tasks:
                    tasks[dep_name] >> current_task

        return tasks

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

