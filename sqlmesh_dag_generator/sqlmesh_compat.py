"""
SQLMesh version compatibility helpers.

Supports SQLMesh 0.228+ through at least 0.236 (and newer, when APIs remain stable):

- ``Config.load`` was removed; use ``load_config_from_paths`` / ``load_config_from_yaml``
- ``Context.run(skip_audits=...)`` was removed; callers already gate via ``inspect.signature``
- ``depends_on`` may be a set of names (str) or objects with ``.name``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Union


def load_sqlmesh_config(config_path: Union[str, Path]):
    """
    Load a SQLMesh ``Config`` from a project path or config file.

    Works across SQLMesh versions that no longer expose ``Config.load``.
    """
    from sqlmesh.core.config import Config

    path = Path(config_path)

    # Preferred modern API (0.228+ / 0.23x).
    # load_config_from_paths expects config *files* (not bare project dirs).
    try:
        from sqlmesh.core.config import load_config_from_paths

        if path.is_dir():
            candidates = [path / "config.yaml", path / "config.yml"]
            file_paths = [p for p in candidates if p.exists()]
            if not file_paths:
                file_paths = [path]
        else:
            file_paths = [path]
        return load_config_from_paths(
            Config,
            project_paths=file_paths,
            load_from_env=False,
        )
    except Exception:
        pass

    # YAML dict -> Config (when given an explicit .yaml/.yml file)
    if path.is_file() and path.suffix in {".yaml", ".yml"}:
        try:
            from sqlmesh.core.config import load_config_from_yaml

            data = load_config_from_yaml(path)
            if hasattr(Config, "model_validate"):
                return Config.model_validate(data)
            if hasattr(Config, "parse_obj"):
                return Config.parse_obj(data)
            return Config(**data)
        except Exception:
            pass

    # Legacy: Config.load if it ever reappears
    if hasattr(Config, "load"):
        try:
            return Config.load(path, gateway=None)  # type: ignore[attr-defined]
        except TypeError:
            return Config.load(path)  # type: ignore[attr-defined]

    raise RuntimeError(
        f"Unable to load SQLMesh config from {path}. "
        "Upgrade sqlmesh or check that config.yaml exists."
    )


def config_to_dict(config: Any) -> Dict[str, Any]:
    """Serialize a SQLMesh Config to a plain dict (Pydantic v1/v2).

    Important for SQLMesh 0.23x+: ``model_dump()`` without ``by_alias`` emits
    field names like ``type_`` for scheduler configs. Re-validating that dict
    with ``Config.parse_obj`` / ``model_validate`` then fails with
    ``Missing scheduler type`` (validator looks for ``type``).

    Prefer ``exclude_defaults=True`` so we only carry project-specific settings
    (model_defaults, physical_schema_mapping, …) into the runtime merge and
    avoid round-tripping broken default objects (e.g. model kind ``NONE``).
    """
    if hasattr(config, "model_dump"):
        try:
            return config.model_dump(exclude_defaults=True, by_alias=True)
        except TypeError:
            # Older pydantic may not accept the same kwargs together
            try:
                return config.model_dump(by_alias=True)
            except TypeError:
                return config.model_dump()
    if hasattr(config, "dict"):
        try:
            return config.dict(exclude_defaults=True, by_alias=True)
        except TypeError:
            try:
                return config.dict(by_alias=True)
            except TypeError:
                return config.dict()
    if isinstance(config, dict):
        return config
    raise TypeError(f"Cannot convert config of type {type(config)} to dict")


def normalize_depends_on(depends_on: Optional[Iterable[Any]]) -> Set[str]:
    """
    Normalize model.depends_on to a set of string names.

    Handles both string table/model names and objects with a ``.name`` attribute.
    """
    if not depends_on:
        return set()
    out: Set[str] = set()
    for dep in depends_on:
        if dep is None:
            continue
        if isinstance(dep, str):
            out.add(dep)
        elif hasattr(dep, "name"):
            out.add(str(dep.name))
        else:
            out.add(str(dep))
    return out


def normalize_cron_tz(cron_tz: Any) -> Optional[str]:
    """
    Return the IANA zone name of a model's ``cron_tz``, or None.

    ``cron_tz`` was added in SQLMesh 0.235.4 and is a ``zoneinfo.ZoneInfo`` on
    the model; older versions do not have the attribute at all.
    """
    if not cron_tz:
        return None
    key = getattr(cron_tz, "key", None)  # zoneinfo.ZoneInfo
    if key:
        return str(key)
    zone = getattr(cron_tz, "zone", None)  # pytz
    if zone:
        return str(zone)
    return str(cron_tz)


def extract_audit_names(model: Any) -> list:
    """
    Names of the audits attached to a model.

    SQLMesh stores them as ``[(name, args_dict), ...]``; some versions expose
    plain strings or objects with a ``name``.
    """
    audits = getattr(model, "audits", None) or []
    names = []
    for audit in audits:
        if isinstance(audit, str):
            names.append(audit)
        elif isinstance(audit, (tuple, list)) and audit:
            names.append(str(audit[0]))
        elif hasattr(audit, "name"):
            names.append(str(audit.name))
    return names


def extract_columns(model: Any) -> Dict[str, str]:
    """
    ``{column: type}`` for a model, as SQL type strings in the model's dialect.

    SQLMesh infers the types from the query, or takes them from an explicit
    ``columns`` block. Anything it cannot infer comes back empty rather than
    failing DAG parsing.
    """
    try:
        columns = getattr(model, "columns_to_types", None)
    except Exception:  # noqa: BLE001 - type inference must not break DAG parsing
        return {}
    if not columns:
        return {}

    dialect = getattr(model, "dialect", None) or None
    out: Dict[str, str] = {}
    for name, data_type in columns.items():
        try:
            out[str(name)] = (
                data_type.sql(dialect=dialect) if hasattr(data_type, "sql") else str(data_type)
            )
        except Exception:  # noqa: BLE001
            out[str(name)] = str(data_type)
    return out


def extract_column_descriptions(model: Any) -> Dict[str, str]:
    """Column comments from the MODEL block or ``-- comments`` in the query."""
    try:
        descriptions = getattr(model, "column_descriptions", None) or {}
    except Exception:  # noqa: BLE001
        return {}
    return {str(k): str(v) for k, v in descriptions.items() if v}


def extract_time_column(model: Any) -> Optional[str]:
    """The ``time_column`` of an INCREMENTAL_BY_TIME_RANGE model, unquoted."""
    time_column = getattr(getattr(model, "kind", None), "time_column", None)
    column = getattr(time_column, "column", None)
    if column is None:
        return None
    name = getattr(column, "name", None) or str(column)
    return str(name).replace('"', "")


def extract_grains(model: Any) -> list:
    """Grain columns (``grain`` / ``grains`` in the MODEL block)."""
    grains = getattr(model, "grains", None) or []
    out = []
    for grain in grains:
        sql = grain.sql() if hasattr(grain, "sql") else str(grain)
        out.append(sql.replace('"', ""))
    return out


__all__ = [
    "extract_columns",
    "extract_column_descriptions",
    "extract_grains",
    "extract_time_column",
    "load_sqlmesh_config",
    "config_to_dict",
    "normalize_depends_on",
    "normalize_cron_tz",
    "extract_audit_names",
]
