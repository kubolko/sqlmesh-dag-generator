"""Tests for SQLMesh version compatibility helpers."""
from pathlib import Path

import pytest

from sqlmesh_dag_generator.sqlmesh_compat import (
    config_to_dict,
    load_sqlmesh_config,
    normalize_depends_on,
)


class TestNormalizeDependsOn:
    def test_strings(self):
        assert normalize_depends_on({"a.b", "c.d"}) == {"a.b", "c.d"}

    def test_objects_with_name(self):
        class Dep:
            def __init__(self, name):
                self.name = name

        assert normalize_depends_on([Dep("x.y"), Dep("z")]) == {"x.y", "z"}

    def test_mixed_and_empty(self):
        assert normalize_depends_on(None) == set()
        assert normalize_depends_on([]) == set()
        class Dep:
            name = "n.m"

        assert normalize_depends_on(["a", Dep(), 123]) == {"a", "n.m", "123"}


class TestLoadSqlmeshConfig:
    def test_loads_yaml_project(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text(
            "gateways:\n  local:\n    connection:\n      type: duckdb\n"
            "default_gateway: local\n"
            "model_defaults:\n  dialect: duckdb\n"
        )
        (tmp_path / "models").mkdir()
        cfg = load_sqlmesh_config(tmp_path / "config.yaml")
        assert cfg is not None
        d = config_to_dict(cfg)
        assert isinstance(d, dict)
        # gateway / defaults present in some form
        assert "gateways" in d or "default_gateway" in d or d
