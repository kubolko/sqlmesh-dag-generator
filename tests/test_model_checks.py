"""Model-contract checks. No warehouse connection."""

from types import SimpleNamespace

import pytest

from sqlmesh_dag_generator.config import ModelChecksConfig
from sqlmesh_dag_generator.validation import (
    engine_runs_merge,
    model_contract_errors,
    validate_loaded_models,
)

OFF = ModelChecksConfig()
ON = ModelChecksConfig(require_explicit_start=True, full_min_interval="day")


def _kind(**flags):
    kind = SimpleNamespace(
        is_view=False,
        is_seed=False,
        is_external=False,
        is_symbolic=False,
        is_embedded=False,
        is_full=False,
        model_kind_name="INCREMENTAL_BY_TIME_RANGE",
    )
    for name, value in flags.items():
        setattr(kind, name, value)
    return kind


def _model(tmp_path, body, **attrs):
    path = tmp_path / "model.sql"
    path.write_text(body, encoding="utf-8")
    values = {
        "_path": path,
        "when_matched": None,
        "interval_unit": "day",
        "kind": _kind(),
        "gateway": None,
    }
    values.update(attrs)
    return SimpleNamespace(**values)


INCREMENTAL = """MODEL (
  name dwh.foo,
  kind INCREMENTAL_BY_TIME_RANGE,
  cron '@daily',
  start '2026-09-30'
);
SELECT 1 AS id
"""

FULL_FINE = """MODEL (
  name dwh.rt_fraud_da_set,
  kind FULL,
  cron '*/10 * * * *'
);
SELECT start_date
"""

NO_START = """MODEL (
  name dwh.foo,
  kind INCREMENTAL_BY_TIME_RANGE,
  cron '@daily'
);
SELECT start AS start_date
"""


def test_when_matched_follows_the_engine():
    model = SimpleNamespace(when_matched=object(), kind=_kind(), interval_unit="day", _path=None)

    redshift = model_contract_errors("dwh.foo", model, {"type": "redshift"}, OFF)
    assert redshift == ["This engine does not run MERGE. Remove `when_matched` from `dwh.foo`."]

    enabled = model_contract_errors(
        "dwh.foo", model, {"type": "redshift", "enable_merge": True}, OFF
    )
    assert enabled == []

    snowflake = model_contract_errors("dwh.foo", model, {"type": "snowflake"}, OFF)
    assert snowflake == []

    duckdb = model_contract_errors("dwh.foo", model, {"type": "duckdb"}, OFF)
    assert any("does not run MERGE" in err for err in duckdb)

    postgres = model_contract_errors("dwh.foo", model, {"type": "postgres"}, OFF)
    assert postgres == []

    assert engine_runs_merge({"type": "postgres"}) is None
    assert engine_runs_merge({"type": "redshift"}) is False
    assert engine_runs_merge({"type": "snowflake"}) is True


def test_opt_in_checks_reject_fine_full_and_missing_start(tmp_path):
    fine = _model(tmp_path, FULL_FINE, interval_unit="five_minute", kind=_kind(is_full=True))
    assert model_contract_errors("dwh.rt_fraud_da_set", fine, {"type": "snowflake"}, OFF) == []

    errors = model_contract_errors("dwh.rt_fraud_da_set", fine, {"type": "snowflake"}, ON)
    assert any("Set cron to `day`" in err for err in errors)
    assert any("Set `start` on `dwh.rt_fraud_da_set`" in err for err in errors)

    missing = _model(tmp_path, NO_START)
    missing_errors = model_contract_errors("dwh.foo", missing, {"type": "snowflake"}, ON)
    assert missing_errors == [
        "Set `start` on `dwh.foo`. Without it, backfill begins at the project default."
    ]

    ready = _model(tmp_path, INCREMENTAL)
    assert model_contract_errors("dwh.foo", ready, {"type": "snowflake"}, ON) == []


def test_start_inside_a_comment_or_the_query_does_not_count(tmp_path):
    commented = _model(
        tmp_path,
        """MODEL (
  name dwh.foo,
  kind FULL,
  cron '@daily',
  -- start '2020-01-01'
);
SELECT 1
""",
        kind=_kind(is_full=True),
    )
    errors = model_contract_errors("dwh.foo", commented, {"type": "duckdb"}, ON)
    assert any(err.startswith("Set `start`") for err in errors)


def test_view_seed_and_external_skip_the_policy_checks(tmp_path):
    body = "MODEL (\n  name dwh.v,\n  kind VIEW\n);\nSELECT 1\n"
    for flags in ({"is_view": True}, {"is_seed": True}, {"is_external": True}):
        model = _model(tmp_path, body, kind=_kind(**flags), interval_unit="five_minute")
        assert model_contract_errors("dwh.v", model, {"type": "duckdb"}, ON) == []


def test_validate_loaded_models_reads_the_gateway_connection(tmp_path):
    model = _model(tmp_path, INCREMENTAL, when_matched=object(), gateway="sf")
    context = SimpleNamespace(
        models={"dwh.foo": model},
        config=SimpleNamespace(
            default_gateway="prod",
            gateways={
                "prod": SimpleNamespace(connection={"type": "redshift"}),
                "sf": SimpleNamespace(connection={"type": "snowflake"}),
            },
        ),
    )
    validate_loaded_models(context, gateway="prod", checks=ON)

    model.gateway = None
    with pytest.raises(ValueError, match="does not run MERGE"):
        validate_loaded_models(context, gateway="prod", checks=ON)
