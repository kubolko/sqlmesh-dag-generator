"""
Data models for SQLMesh DAG Generator
"""
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from sqlmesh.core.model import Model


@dataclass
class SQLMeshModelInfo:
    """
    Information extracted from a SQLMesh model.
    """
    name: str
    dependencies: Set[str] = field(default_factory=set)
    cron: Optional[str] = None
    interval_unit: Optional[str] = None
    kind: str = "FULL"
    owner: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    description: Optional[str] = None
    model: Optional[Model] = None

    def get_task_id(self) -> str:
        """Generate Airflow task ID from model name"""
        # Replace dots, quotes, and special characters with underscores
        task_id = (self.name
                   .replace('"', '')
                   .replace("'", '')
                   .replace(".", "_")
                   .replace("-", "_")
                   .replace(" ", "_"))
        # Remove any consecutive underscores
        while "__" in task_id:
            task_id = task_id.replace("__", "_")
        # Remove leading/trailing underscores
        task_id = task_id.strip("_")
        return f"sqlmesh_{task_id}"

    def is_incremental(self) -> bool:
        """Check if this is an incremental model"""
        return "INCREMENTAL" in self.kind.upper()

    def get_upstream_task_ids(self) -> List[str]:
        """Get list of upstream task IDs"""
        return [
            dep.replace(".", "_").replace("-", "_")
            for dep in self.dependencies
        ]


@dataclass
class DAGStructure:
    """
    Structure representing the complete DAG.
    """
    dag_id: str
    models: Dict[str, SQLMeshModelInfo]
    config: Any = None  # DAGGeneratorConfig

    def get_root_models(self) -> List[str]:
        """Get models with no dependencies (root nodes)"""
        roots = []
        for name, model_info in self.models.items():
            if not model_info.dependencies:
                roots.append(name)
        return roots

    def get_leaf_models(self) -> List[str]:
        """Get models that no other model depends on (leaf nodes)"""
        all_deps = set()
        for model_info in self.models.values():
            all_deps.update(model_info.dependencies)

        leaves = []
        for name in self.models.keys():
            if name not in all_deps:
                leaves.append(name)
        return leaves

    def topological_sort(self) -> List[str]:
        """
        Return models in topological order (dependencies first).
        """
        # Build dependency map
        graph = {name: set(info.dependencies) for name, info in self.models.items()}
        # Track number of unresolved dependencies for each node
        in_degree = {name: len(deps) for name, deps in graph.items()}
        # Map each node to the models that depend on it
        dependents: Dict[str, Set[str]] = {name: set() for name in graph}
        for model_name, deps in graph.items():
            for dep in deps:
                if dep in dependents:
                    dependents[dep].add(model_name)

        queue = [name for name, degree in in_degree.items() if degree == 0]
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for dependent in dependents.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(graph):
            raise ValueError("Circular dependency detected in models")

        return result

    def validate(self) -> bool:
        """
        Validate the DAG structure.

        Returns:
            True if valid, raises exception otherwise
        """
        # Check that all dependencies exist
        all_model_names = set(self.models.keys())
        for name, model_info in self.models.items():
            for dep in model_info.dependencies:
                if dep not in all_model_names:
                    raise ValueError(
                        f"Model '{name}' depends on '{dep}' which does not exist"
                    )

        # Check for circular dependencies
        try:
            self.topological_sort()
        except ValueError as e:
            raise ValueError(f"DAG validation failed: {e}")

        return True
