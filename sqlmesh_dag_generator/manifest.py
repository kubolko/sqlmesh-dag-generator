"""
A manifest of what the generator would put in Airflow.

dbt writes ``target/manifest.json`` and a whole ecosystem grew on top of it:
CI diffs, catalogues, impact analysis. SQLMesh keeps its state in the warehouse,
which is great for correctness but leaves nothing to diff in a pull request.

``build_manifest`` produces the same kind of artifact for the *orchestration*
side: every model, its task id, its schedule, its dataset URI and its lineage,
plus the DAG groups they belong to. Commit it, or diff it in CI to see which
Airflow tasks a model change is about to add, remove, or reschedule.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

MANIFEST_VERSION = 1


def _model_entry(generator, model_info) -> Dict[str, Any]:
    return {
        "name": model_info.display_name,
        "fqn": model_info.name,
        "task_id": model_info.get_task_id(),
        "kind": model_info.kind,
        "cron": model_info.cron,
        "cron_tz": model_info.cron_tz,
        "interval_unit": str(model_info.interval_unit) if model_info.interval_unit else None,
        "owner": model_info.owner,
        "tags": list(model_info.tags or []),
        "audits": list(model_info.audits or []),
        "path": model_info.path,
        "project": model_info.project,
        "description": model_info.description,
        "depends_on": sorted(
            dep.replace('"', "") for dep in model_info.dependencies if dep in generator.models
        ),
        "sources": sorted(
            dep.replace('"', "") for dep in model_info.dependencies if dep not in generator.models
        ),
        "dataset_uri": generator.model_dataset_uri(model_info),
    }


def build_manifest(generator, include_groups: bool = True) -> Dict[str, Any]:
    """
    Describe the models this generator would schedule.

    Args:
        generator: a ``SQLMeshDAGGenerator`` (models are extracted if needed).
        include_groups: also resolve ``dag_groups`` from the configuration.
    """
    from sqlmesh_dag_generator import __version__

    if not generator.models:
        generator.extract_models()

    models = {
        info.display_name: _model_entry(generator, info) for info in generator.models.values()
    }

    manifest: Dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "generator_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_path": generator.config.sqlmesh.project_path,
        "gateway": generator.config.sqlmesh.gateway,
        "dag_id": generator.config.airflow.dag_id,
        "schedule": generator.get_recommended_schedule(),
        "selection": {
            "select": list(generator.config.generation.select or []),
            "exclude": list(generator.config.generation.exclude or []),
        },
        "models": models,
    }

    if include_groups and generator.config.dag_groups:
        from sqlmesh_dag_generator.dag_groups import describe_dag_groups

        manifest["dag_groups"] = describe_dag_groups(generator.config, generator.models)

    return manifest


def write_manifest(generator, output_path: str, include_groups: bool = True) -> Path:
    """Write :func:`build_manifest` to ``output_path`` as formatted JSON."""
    manifest = build_manifest(generator, include_groups=include_groups)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def diff_manifests(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    What changed between two manifests - the bit CI actually cares about.

    Returns added / removed models, and the ones whose schedule, lineage or
    task id moved (a renamed task means Airflow loses that task's history).
    """
    old_models = old.get("models", {})
    new_models = new.get("models", {})

    watched = ("task_id", "cron", "cron_tz", "interval_unit", "kind", "depends_on", "tags")
    changed = [
        name
        for name in sorted(set(old_models) & set(new_models))
        if any(old_models[name].get(key) != new_models[name].get(key) for key in watched)
    ]

    return {
        "added": sorted(set(new_models) - set(old_models)),
        "removed": sorted(set(old_models) - set(new_models)),
        "changed": changed,
    }


__all__ = ["MANIFEST_VERSION", "build_manifest", "diff_manifests", "write_manifest"]
