"""Tests for mixed-cadence skip_if_not_due helpers."""
from datetime import datetime, timezone

from sqlmesh_dag_generator.config import GenerationConfig
from sqlmesh_dag_generator.utils import (
    interval_end_matches_cron,
    interval_end_matches_minutes,
    not_due_skip_result,
    should_skip_model_for_tick,
)


def test_generation_config_skip_if_not_due_default():
    assert GenerationConfig().skip_if_not_due is True


def test_interval_end_matches_cron():
    end_5 = datetime(2026, 8, 10, 12, 5, tzinfo=timezone.utc)
    end_hour = datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc)
    end_off = datetime(2026, 8, 10, 12, 7, tzinfo=timezone.utc)

    assert interval_end_matches_cron("*/5 * * * *", end_5)
    assert not interval_end_matches_cron("0 * * * *", end_5)
    assert interval_end_matches_cron("0 * * * *", end_hour)
    assert interval_end_matches_cron("@hourly", end_hour)
    assert not interval_end_matches_cron("*/5 * * * *", end_off)


def test_interval_end_matches_minutes_fallback():
    end = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    mid = datetime(2026, 8, 10, 12, 5, tzinfo=timezone.utc)
    assert interval_end_matches_minutes(60, end)
    assert not interval_end_matches_minutes(60, mid)
    assert interval_end_matches_minutes(5, mid)
    assert not interval_end_matches_minutes(5, datetime(2026, 8, 10, 12, 7, tzinfo=timezone.utc))


def test_should_skip_same_cadence_never_skips():
    end = datetime(2026, 8, 10, 12, 7, tzinfo=timezone.utc)
    assert not should_skip_model_for_tick(
        cron_expr="*/5 * * * *",
        model_interval_minutes=5,
        dag_tick_minutes=5,
        data_interval_end=end,
        skip_if_not_due=True,
    )


def test_should_skip_coarser_when_not_due():
    end = datetime(2026, 8, 10, 12, 5, tzinfo=timezone.utc)
    assert should_skip_model_for_tick(
        cron_expr="0 * * * *",
        model_interval_minutes=60,
        dag_tick_minutes=5,
        data_interval_end=end,
        skip_if_not_due=True,
    )


def test_should_not_skip_coarser_when_due():
    end = datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc)
    assert not should_skip_model_for_tick(
        cron_expr="0 * * * *",
        model_interval_minutes=60,
        dag_tick_minutes=5,
        data_interval_end=end,
        skip_if_not_due=True,
    )


def test_skip_if_not_due_false_never_skips():
    end = datetime(2026, 8, 10, 12, 5, tzinfo=timezone.utc)
    assert not should_skip_model_for_tick(
        cron_expr="0 * * * *",
        model_interval_minutes=60,
        dag_tick_minutes=5,
        data_interval_end=end,
        skip_if_not_due=False,
    )


def test_not_due_skip_result_shape():
    payload = not_due_skip_result("db.schema.model", "0 * * * *")
    assert payload["status"] == "skipped"
    assert payload["reason"] == "not_due"
    assert payload["model"] == "db.schema.model"
    assert payload["cron"] == "0 * * * *"
