"""
Per-model Airflow downstream DAG triggers.

Resolution order (highest wins):
  1. ``generation.model_triggers[model_name]`` explicit config
  2. SQLMesh model tags:
       - ``trigger_dag:<dag_id>``  (required for tag-based trigger)
       - ``trigger_conf:<key>=<value>``  (optional, repeatable; values are strings)

Example model tags (SQLMesh-native)::

    tags (
      rt,
      flink,
      'trigger_dag:etl_rt_fraud_da_unload',
      'trigger_conf:source=sqlmesh'
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional


TRIGGER_DAG_TAG_PREFIX = "trigger_dag:"
TRIGGER_CONF_TAG_PREFIX = "trigger_conf:"


@dataclass
class ModelTriggerConfig:
    """Downstream DAG to fire after a specific SQLMesh model task succeeds."""

    dag_id: str
    conf: Dict[str, Any] = field(default_factory=dict)
    wait_for_completion: bool = False
    reset_dag_run: bool = False
    poke_interval: Optional[int] = None  # only used if wait_for_completion

    def __post_init__(self) -> None:
        if not self.dag_id or not str(self.dag_id).strip():
            raise ValueError("ModelTriggerConfig.dag_id must be a non-empty string")
        self.dag_id = str(self.dag_id).strip()
        if self.conf is None:
            self.conf = {}
        if not isinstance(self.conf, dict):
            raise ValueError("ModelTriggerConfig.conf must be a dict")


def parse_trigger_from_tags(tags: Optional[Iterable[str]]) -> Optional[ModelTriggerConfig]:
    """Parse ``trigger_dag:`` / ``trigger_conf:`` tags into a config, if present."""
    if not tags:
        return None

    dag_id: Optional[str] = None
    conf: Dict[str, Any] = {}

    for raw in tags:
        if raw is None:
            continue
        tag = str(raw).strip()
        if not tag:
            continue
        lower = tag.lower()
        if lower.startswith(TRIGGER_DAG_TAG_PREFIX):
            value = tag[len(TRIGGER_DAG_TAG_PREFIX) :].strip()
            if value:
                dag_id = value
            continue
        if lower.startswith(TRIGGER_CONF_TAG_PREFIX):
            rest = tag[len(TRIGGER_CONF_TAG_PREFIX) :]
            if "=" not in rest:
                continue
            key, value = rest.split("=", 1)
            key = key.strip()
            if key:
                conf[key] = value.strip()

    if not dag_id:
        return None
    return ModelTriggerConfig(dag_id=dag_id, conf=conf)


def _coerce_trigger_entry(entry: Any) -> ModelTriggerConfig:
    if isinstance(entry, ModelTriggerConfig):
        return entry
    if isinstance(entry, str):
        return ModelTriggerConfig(dag_id=entry)
    if isinstance(entry, Mapping):
        return ModelTriggerConfig(
            dag_id=str(entry.get("dag_id") or entry.get("trigger_dag_id") or ""),
            conf=dict(entry.get("conf") or {}),
            wait_for_completion=bool(entry.get("wait_for_completion", False)),
            reset_dag_run=bool(entry.get("reset_dag_run", False)),
            poke_interval=entry.get("poke_interval"),
        )
    raise TypeError(
        f"Unsupported model_triggers entry type: {type(entry)!r} "
        f"(expected str, dict, or ModelTriggerConfig)"
    )


def normalize_model_triggers(
    raw: Optional[Mapping[str, Any]],
) -> Dict[str, ModelTriggerConfig]:
    """Normalize YAML/dict model_triggers map to ModelTriggerConfig values."""
    if not raw:
        return {}
    out: Dict[str, ModelTriggerConfig] = {}
    for model_name, entry in raw.items():
        if not model_name:
            continue
        out[str(model_name)] = _coerce_trigger_entry(entry)
    return out


def resolve_model_trigger(
    model_name: str,
    tags: Optional[Iterable[str]] = None,
    model_triggers: Optional[Mapping[str, Any]] = None,
) -> Optional[ModelTriggerConfig]:
    """
    Resolve trigger for one model.

    Explicit ``model_triggers[model_name]`` wins over tags.
    """
    normalized = normalize_model_triggers(model_triggers)
    if model_name in normalized:
        return normalized[model_name]

    # FQN / short-name flexibility
    short = model_name.split(".")[-1]
    for key, cfg in normalized.items():
        if key == model_name or key == short:
            return cfg
        if key.endswith(f".{short}") and model_name.endswith(f".{short}"):
            return cfg

    return parse_trigger_from_tags(tags)


def trigger_task_id(dag_id: str, model_task_id: str) -> str:
    """Stable Airflow task_id for a per-model trigger operator."""
    safe_dag = (
        dag_id.replace(".", "_").replace("-", "_").replace(" ", "_").strip("_")
    )
    base = f"trigger_{safe_dag}__after_{model_task_id}"
    if len(base) <= 200:
        return base
    return f"trigger_{safe_dag}_{abs(hash(model_task_id)) % 10_000_000}"


def default_trigger_conf(
    model_name: str,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    conf: Dict[str, Any] = {
        "source": "sqlmesh",
        "model": model_name,
    }
    if extra:
        conf.update(dict(extra))
    return conf
