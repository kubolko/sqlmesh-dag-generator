"""
Several Airflow DAGs out of one SQLMesh project.

A SQLMesh project is one model graph, but it is rarely one pipeline. Finance
models run every 15 minutes and page the on-call; marketing models run nightly
and nobody wants to be woken up for them. Splitting those into separate DAGs
used to mean separate projects (or a lot of copy-pasted DAG files).

A *DAG group* is a selection plus DAG settings::

    dag_groups:
      - dag_id: dwh_finance
        select: ["tag:finance+"]
        schedule: "*/15 * * * *"
      - dag_id: dwh_marketing
        select: ["tag:marketing+"]
        schedule: "@daily"
        wait_for_upstream: dataset

Models shared between groups keep their SQLMesh lineage: the cross-group edges
become Airflow Datasets (the downstream DAG is scheduled by upstream model
completion) or ExternalTaskSensors, depending on ``wait_for_upstream``.

Usage in a DAG file::

    from sqlmesh_dag_generator import DAGGeneratorConfig, build_dag_groups

    for dag_id, dag in build_dag_groups(DAGGeneratorConfig.from_file("config.yaml")).items():
        globals()[dag_id] = dag
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from sqlmesh_dag_generator.config import DAGGeneratorConfig, DAGGroupConfig
from sqlmesh_dag_generator.models import SQLMeshModelInfo
from sqlmesh_dag_generator.selectors import select_models
from sqlmesh_dag_generator.utils import get_minimum_interval

logger = logging.getLogger(__name__)


@dataclass
class GroupPlan:
    """What a group contains and what it needs from its neighbours."""

    group: DAGGroupConfig
    models: Dict[str, SQLMeshModelInfo]
    # upstream model key -> dag_id of the group that owns it
    external_upstreams: Dict[str, str] = field(default_factory=dict)
    schedule: Optional[str] = None

    @property
    def dag_id(self) -> str:
        return self.group.dag_id

    @property
    def model_names(self) -> List[str]:
        return sorted(self.models)


def plan_dag_groups(
    config: DAGGeneratorConfig,
    all_models: Dict[str, SQLMeshModelInfo],
    strict: bool = False,
) -> List[GroupPlan]:
    """
    Resolve every group's selection against the full model graph.

    Pure bookkeeping: no Airflow objects are created, which makes it easy to
    unit test and to print from the CLI before deploying anything.
    """
    if not config.dag_groups:
        raise ValueError("No dag_groups are configured")

    owners: Dict[str, str] = {}
    plans: List[GroupPlan] = []

    for group in config.dag_groups:
        selected = select_models(
            all_models,
            select=group.select or None,
            exclude=group.exclude or None,
            named_selectors=config.selectors,
        )
        models = {name: info for name, info in all_models.items() if name in selected}
        if not models:
            message = f"DAG group '{group.dag_id}' selected no models: {group.select}"
            if strict:
                raise ValueError(message)
            logger.warning(message)

        for name in models:
            if name in owners and owners[name] != group.dag_id:
                message = (
                    f"Model {name} is selected by both '{owners[name]}' and "
                    f"'{group.dag_id}'; it will run in both DAGs"
                )
                if strict:
                    raise ValueError(message)
                logger.warning(message)
            else:
                owners[name] = group.dag_id

        plans.append(GroupPlan(group=group, models=models, schedule=group.schedule))

    # Second pass: the owner map is only complete once every group is resolved.
    for plan in plans:
        for info in plan.models.values():
            for dep in info.dependencies:
                owner = owners.get(dep)
                if dep in plan.models or owner is None or owner == plan.dag_id:
                    continue
                plan.external_upstreams[dep] = owner

    uncovered = sorted(set(all_models) - set(owners))
    if uncovered:
        logger.warning(
            "%s model(s) are not part of any DAG group and will not be scheduled: %s",
            len(uncovered),
            ", ".join(m.replace('"', "") for m in uncovered[:10])
            + (" ..." if len(uncovered) > 10 else ""),
        )

    return plans


def _group_schedule(plan: GroupPlan, config: DAGGeneratorConfig) -> Optional[str]:
    """Explicit group schedule, else the shortest interval among its models."""
    if plan.schedule:
        return plan.schedule
    if not config.airflow.auto_schedule:
        return config.airflow.schedule_interval
    intervals = [info.interval_unit for info in plan.models.values()]
    _, cron = get_minimum_interval(intervals)
    logger.info("DAG group '%s': auto-detected schedule %s", plan.dag_id, cron)
    return cron


def _group_generator(base_generator, plan: GroupPlan):
    """A generator clone scoped to one group (shares the loaded SQLMesh context)."""
    group_generator = copy.copy(base_generator)
    group_generator.config = copy.deepcopy(base_generator.config)
    group_generator.config.airflow.dag_id = plan.dag_id
    for key, value in (plan.group.generation_overrides or {}).items():
        if not hasattr(group_generator.config.generation, key):
            raise ValueError(f"Unknown generation override '{key}' in dag_group '{plan.dag_id}'")
        setattr(group_generator.config.generation, key, value)
    group_generator.models = dict(plan.models)
    # Models owned by other groups are still project models, not raw sources.
    group_generator.project_model_keys = set(base_generator.models)
    group_generator.dag_structure = None
    return group_generator


def _start_date(value: Optional[str], fallback: Optional[str]) -> datetime:
    raw = value or fallback
    if not raw:
        return datetime.now() - timedelta(days=1)
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        # start_date also accepts things like "days_ago(1)" in the YAML config,
        # which only mean something inside a generated DAG file.
        logger.warning("Could not parse start_date %r as ISO-8601; using yesterday instead.", raw)
        return datetime.now() - timedelta(days=1)


def build_dag_groups(
    config: DAGGeneratorConfig,
    generator: Optional[Any] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Build one Airflow DAG per configured group.

    Args:
        config: configuration carrying ``dag_groups`` (and optionally ``selectors``).
        generator: an existing ``SQLMeshDAGGenerator`` whose SQLMesh context is
            already loaded. When omitted, one is created from ``config`` - the
            SQLMesh project is then parsed once for all groups.
        strict: raise instead of warning on empty groups and on models claimed
            by more than one group.

    Returns:
        ``{dag_id: DAG}`` - assign them into the module globals of your DAG file.
    """
    from airflow import DAG

    from sqlmesh_dag_generator.airflow_compat import (
        ExternalTaskSensor,
        dag_schedule_kwargs,
        make_dataset,
        supports_datasets,
    )
    from sqlmesh_dag_generator.generator import SQLMeshDAGGenerator

    base = generator or SQLMeshDAGGenerator(config=config)
    if not base.models:
        base.extract_models()

    plans = plan_dag_groups(config, base.models, strict=strict)

    # Publishing is only worth it when some group actually waits on another one.
    wants_datasets = any(
        p.group.wait_for_upstream == "dataset" and p.external_upstreams for p in plans
    )
    if wants_datasets and not supports_datasets():
        logger.warning(
            "wait_for_upstream='dataset' needs Airflow 2.4+; falling back to "
            "cross-group edges being logged only."
        )
        wants_datasets = False

    dags: Dict[str, Any] = {}
    for plan in plans:
        group_generator = _group_generator(base, plan)
        if wants_datasets:
            # Every group has to publish, so that consumers have something to wait for.
            group_generator.config.generation.emit_datasets = True

        schedule: Union[str, List[Any], None] = _group_schedule(plan, config)
        inlet_datasets = []
        if plan.external_upstreams and plan.group.wait_for_upstream == "dataset" and wants_datasets:
            inlet_datasets = [
                make_dataset(group_generator.model_dataset_uri(base.models[dep]))
                for dep in sorted(plan.external_upstreams)
            ]
            if plan.group.schedule:
                logger.info(
                    "DAG group '%s' keeps its explicit schedule %s; upstream datasets "
                    "are published but not used for scheduling.",
                    plan.dag_id,
                    plan.group.schedule,
                )
            else:
                schedule = inlet_datasets
                logger.info(
                    "DAG group '%s' is scheduled by %s upstream model dataset(s)",
                    plan.dag_id,
                    len(inlet_datasets),
                )

        dag_kwargs: Dict[str, Any] = {
            "dag_id": plan.dag_id,
            "description": plan.group.description
            or f"SQLMesh models selected by {plan.group.select or 'the whole project'}",
            "start_date": _start_date(plan.group.start_date, config.airflow.start_date),
            "catchup": config.airflow.catchup if plan.group.catchup is None else plan.group.catchup,
            "max_active_runs": plan.group.max_active_runs or config.airflow.max_active_runs,
            "default_args": plan.group.default_args or config.airflow.default_args,
            "tags": plan.group.tags or config.airflow.tags,
        }
        dag_kwargs.update(dag_schedule_kwargs(schedule))

        with DAG(**dag_kwargs) as dag:
            tasks = group_generator.create_tasks_in_dag(dag, models=plan.model_names)

            if plan.external_upstreams and plan.group.wait_for_upstream == "sensor":
                _add_upstream_sensors(plan, base, tasks, dag, ExternalTaskSensor)
            elif plan.external_upstreams and plan.group.wait_for_upstream == "none":
                logger.info(
                    "DAG group '%s' depends on %s model(s) owned by other groups; "
                    "no cross-DAG wiring was requested (wait_for_upstream='none')",
                    plan.dag_id,
                    len(plan.external_upstreams),
                )

        dags[plan.dag_id] = dag
        logger.info(
            "DAG group '%s': %s model(s), schedule=%s, %s external upstream(s)",
            plan.dag_id,
            len(plan.models),
            f"{len(schedule)} dataset(s)" if isinstance(schedule, list) else schedule,
            len(plan.external_upstreams),
        )

    return dags


def _add_upstream_sensors(
    plan: GroupPlan,
    base_generator,
    tasks: Dict[str, Any],
    dag,
    external_task_sensor_cls,
) -> None:
    """Wait for the upstream group's model task with an ExternalTaskSensor."""
    if external_task_sensor_cls is None:  # pragma: no cover - very old Airflow
        logger.warning(
            "ExternalTaskSensor is unavailable; DAG group '%s' cannot wait for "
            "its upstream groups.",
            plan.dag_id,
        )
        return

    from sqlmesh_dag_generator.utils import sanitize_task_id

    for dep_key, upstream_dag_id in sorted(plan.external_upstreams.items()):
        dep_info = base_generator.models[dep_key]
        sensor_kwargs: Dict[str, Any] = {
            "task_id": f"wait_for__{sanitize_task_id(dep_info.display_name)}",
            "external_dag_id": upstream_dag_id,
            "external_task_id": dep_info.get_task_id(),
            "poke_interval": plan.group.sensor_poke_interval_seconds,
            "timeout": plan.group.sensor_timeout_minutes * 60,
            "mode": "reschedule",
            "allowed_states": ["success"],
            "dag": dag,
        }
        sensor = external_task_sensor_cls(**sensor_kwargs)
        for name, info in plan.models.items():
            if dep_key in info.dependencies and name in tasks:
                sensor >> tasks[name]


def describe_dag_groups(
    config: DAGGeneratorConfig,
    all_models: Dict[str, SQLMeshModelInfo],
) -> List[Dict[str, Any]]:
    """Plain-data summary of the groups, for CLI output and tests."""
    return [
        {
            "dag_id": plan.dag_id,
            "select": list(plan.group.select),
            "exclude": list(plan.group.exclude),
            "schedule": _group_schedule(plan, config),
            "models": [m.replace('"', "") for m in plan.model_names],
            "external_upstreams": {
                dep.replace('"', ""): owner for dep, owner in plan.external_upstreams.items()
            },
            "wait_for_upstream": plan.group.wait_for_upstream,
        }
        for plan in plan_dag_groups(config, all_models)
    ]


__all__ = [
    "GroupPlan",
    "build_dag_groups",
    "describe_dag_groups",
    "plan_dag_groups",
]
