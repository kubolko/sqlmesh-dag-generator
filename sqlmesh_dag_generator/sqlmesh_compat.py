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

    # Preferred modern API (0.228+ / 0.23x)
    try:
        from sqlmesh.core.config import load_config_from_paths

        project_path = path if path.is_dir() else path.parent
        return load_config_from_paths(
            Config,
            project_paths=[project_path],
            load_from_env=False,
        )
    except Exception:
        pass

    # YAML dict → Config (when given an explicit .yaml/.yml file)
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
    """Serialize a SQLMesh Config to a plain dict (Pydantic v1/v2)."""
    if hasattr(config, "model_dump"):
        return config.model_dump()
    if hasattr(config, "dict"):
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


__all__ = [
    "load_sqlmesh_config",
    "config_to_dict",
    "normalize_depends_on",
]
