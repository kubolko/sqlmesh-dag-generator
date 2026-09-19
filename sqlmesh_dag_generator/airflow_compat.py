"""
Airflow 2.x / 3.x compatibility shims for sqlmesh-dag-generator.

Import operators, hooks, and Variable from here so the package works on:

- Airflow 2.4+ / 2.11 (``schedule=`` accepted; classic operator paths)
- Airflow 3.x (providers.standard operators; Task SDK BaseHook/Variable preferred)

Config field names such as ``schedule_interval`` in YAML remain unchanged for
backward compatibility; only the Airflow ``DAG(...)`` kwarg uses ``schedule``.
"""

from __future__ import annotations

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

try:
    # Airflow 3 + providers-standard (preferred)
    from airflow.providers.standard.operators.python import PythonOperator
except ImportError:  # pragma: no cover - AF2 / missing provider
    from airflow.operators.python import PythonOperator  # type: ignore

try:
    from airflow.providers.standard.operators.empty import EmptyOperator
except ImportError:  # pragma: no cover
    try:
        from airflow.operators.empty import EmptyOperator  # type: ignore
    except ImportError:  # very old AF2
        from airflow.operators.dummy import DummyOperator as EmptyOperator  # type: ignore

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:  # pragma: no cover
    from airflow.operators.bash import BashOperator  # type: ignore

try:
    from airflow.providers.standard.operators.trigger_dagrun import (
        TriggerDagRunOperator,
    )
except ImportError:  # pragma: no cover
    try:
        from airflow.operators.trigger_dagrun import TriggerDagRunOperator  # type: ignore
    except ImportError:
        TriggerDagRunOperator = None  # type: ignore  # optional dependency path


# ---------------------------------------------------------------------------
# BaseHook / Variable — AF3 Task SDK first, then classic paths
# ---------------------------------------------------------------------------

try:
    from airflow.sdk.bases.hook import BaseHook  # Airflow 3 Task SDK
except ImportError:  # pragma: no cover
    try:
        from airflow.hooks.base import BaseHook  # Airflow 2
    except ImportError:  # pragma: no cover
        from airflow.hooks.base_hook import BaseHook  # type: ignore  # ancient

try:
    from airflow.sdk import Variable  # Airflow 3 Task SDK
except ImportError:  # pragma: no cover
    from airflow.models import Variable  # type: ignore  # Airflow 2


# ---------------------------------------------------------------------------
# Datasets (Airflow 2.4+) / Assets (Airflow 3) and cross-DAG sensors
# ---------------------------------------------------------------------------

try:
    from airflow.sdk import Asset as Dataset  # Airflow 3 renamed Dataset -> Asset
except ImportError:  # pragma: no cover
    try:
        from airflow.datasets import Dataset  # type: ignore  # Airflow 2.4+
    except ImportError:  # pragma: no cover
        Dataset = None  # type: ignore  # Airflow < 2.4

try:
    from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
except ImportError:  # pragma: no cover
    try:
        from airflow.sensors.external_task import ExternalTaskSensor  # type: ignore
    except ImportError:  # pragma: no cover
        ExternalTaskSensor = None  # type: ignore


def supports_datasets() -> bool:
    """True when this Airflow can express dataset/asset dependencies."""
    return Dataset is not None


def make_dataset(uri: str):
    """
    Build a Dataset (AF2) / Asset (AF3) for a model.

    Airflow 3 requires assets to have a name, and accepts ``name=`` as the first
    positional argument, so pass the URI explicitly for both generations.
    """
    if Dataset is None:  # pragma: no cover - guarded by supports_datasets()
        raise RuntimeError(
            "This Airflow version has no Dataset/Asset support "
            "(needs Airflow 2.4+). Set generation.emit_datasets=false."
        )
    try:
        return Dataset(uri=uri, name=uri)  # Airflow 3 (Asset)
    except TypeError:  # pragma: no cover - Airflow 2 Dataset has no name kwarg
        return Dataset(uri=uri)


def dag_schedule_kwargs(schedule: Any) -> Dict[str, Any]:
    """
    Build kwargs for ``DAG(...)`` that work on Airflow 2.4+ and Airflow 3.

    Always uses ``schedule=`` (supported since AF 2.4; required on AF 3), which
    also accepts a list of Datasets/Assets for data-aware scheduling.
    Do not emit ``schedule_interval=`` — removed in Airflow 3.
    """
    return {"schedule": schedule}


def is_airflow_3() -> bool:
    """Return True when running under Airflow 3.x."""
    try:
        import airflow

        version = getattr(airflow, "__version__", "0")
        return str(version).split(".", 1)[0] == "3"
    except Exception:  # pragma: no cover
        return False


__all__ = [
    "PythonOperator",
    "EmptyOperator",
    "BashOperator",
    "TriggerDagRunOperator",
    "ExternalTaskSensor",
    "BaseHook",
    "Dataset",
    "Variable",
    "dag_schedule_kwargs",
    "is_airflow_3",
    "make_dataset",
    "supports_datasets",
]
