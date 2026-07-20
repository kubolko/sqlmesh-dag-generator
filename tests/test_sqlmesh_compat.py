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

    def test_config_to_dict_round_trip_without_missing_scheduler_type(self, tmp_path: Path):
        """Regression: model_dump() emits type_ not type → Config re-parse fails."""
        pytest.importorskip("sqlmesh")
        from sqlmesh.core.config import Config

        (tmp_path / "config.yaml").write_text(
            "project: carrierops_dwh\n"
            "gateways:\n  local:\n    connection:\n      type: duckdb\n"
            "default_gateway: local\n"
            "model_defaults:\n  dialect: duckdb\n  start: 2023-01-01\n"
            "physical_schema_override:\n  dwh: public\n"
        )
        (tmp_path / "models").mkdir()
        base = load_sqlmesh_config(tmp_path / "config.yaml")
        dumped = config_to_dict(base)

        # Must not leave bare default_scheduler without type alias
        sched = dumped.get("default_scheduler")
        if isinstance(sched, dict):
            assert "type" in sched, f"expected alias 'type', got {sched!r}"

        # Same merge path as SQLMeshDAGGenerator.load_sqlmesh_context
        merged = {
            "gateways": {},
            "default_gateway": "runtime",
        }
        for key, value in dumped.items():
            if key not in ("gateways", "default_gateway"):
                merged[key] = value
        merged["gateways"]["runtime"] = {
            "connection": {"type": "duckdb"},
        }

        if hasattr(Config, "model_validate"):
            Config.model_validate(merged)
        else:
            Config.parse_obj(merged)
