"""
Tests for dbt-style model selection.

The graph used throughout:

    raw.events  ->  stg.events  ->  marts.daily_events -> marts.exec_summary
    raw.users   ->  stg.users   ->  marts.user_profile
"""

import pytest

from sqlmesh_dag_generator.models import SQLMeshModelInfo
from sqlmesh_dag_generator.selectors import (
    SelectionError,
    explain_selection,
    select_models,
)


def model(name, deps=(), tags=(), kind="FULL", owner=None, path=None, interval=None, cron=None):
    return SQLMeshModelInfo(
        name=name,
        dependencies=set(deps),
        tags=list(tags),
        kind=kind,
        owner=owner,
        path=path,
        interval_unit=interval,
        cron=cron,
    )


@pytest.fixture
def graph():
    return {
        "raw.events": model("raw.events", tags=["bronze"], path="models/raw/events.sql"),
        "raw.users": model("raw.users", tags=["bronze"], path="models/raw/users.sql"),
        "stg.events": model(
            "stg.events",
            deps=["raw.events"],
            tags=["silver", "finance"],
            kind="INCREMENTAL_BY_TIME_RANGE",
            path="models/staging/events.sql",
            interval="IntervalUnit.FIVE_MINUTE",
            cron="*/5 * * * *",
        ),
        "stg.users": model(
            "stg.users",
            deps=["raw.users"],
            tags=["silver"],
            path="models/staging/users.sql",
            owner="analytics",
        ),
        "marts.daily_events": model(
            "marts.daily_events",
            deps=["stg.events"],
            tags=["gold", "finance"],
            path="models/marts/daily_events.sql",
            owner="finance-team",
            interval="IntervalUnit.DAY",
        ),
        "marts.user_profile": model(
            "marts.user_profile",
            deps=["stg.users", "stg.events"],
            tags=["gold", "marketing"],
            path="models/marts/user_profile.sql",
        ),
        "marts.exec_summary": model(
            "marts.exec_summary",
            deps=["marts.daily_events"],
            tags=["gold", "deprecated"],
            path="models/marts/exec_summary.sql",
        ),
    }


def test_no_selection_returns_everything(graph):
    assert select_models(graph) == set(graph)


def test_plain_name_matches_short_and_full_name(graph):
    assert select_models(graph, ["marts.daily_events"]) == {"marts.daily_events"}
    assert select_models(graph, ["daily_events"]) == {"marts.daily_events"}


def test_wildcards(graph):
    assert select_models(graph, ["marts.*"]) == {
        "marts.daily_events",
        "marts.user_profile",
        "marts.exec_summary",
    }


def test_tag_selection(graph):
    assert select_models(graph, ["tag:finance"]) == {"stg.events", "marts.daily_events"}


def test_tag_wildcard(graph):
    assert select_models(graph, ["tag:mark*"]) == {"marts.user_profile"}


def test_downstream_operator(graph):
    assert select_models(graph, ["tag:finance+"]) == {
        "stg.events",
        "marts.daily_events",
        "marts.exec_summary",
        "marts.user_profile",
    }


def test_upstream_operator(graph):
    assert select_models(graph, ["+marts.daily_events"]) == {
        "raw.events",
        "stg.events",
        "marts.daily_events",
    }


def test_depth_limited_operators(graph):
    assert select_models(graph, ["1+marts.daily_events"]) == {"stg.events", "marts.daily_events"}
    assert select_models(graph, ["stg.events+1"]) == {
        "stg.events",
        "marts.daily_events",
        "marts.user_profile",
    }


def test_at_operator_pulls_in_parents_of_children(graph):
    # user_profile also needs stg.users, which is not downstream of stg.events
    assert select_models(graph, ["@stg.events"]) == {
        "raw.events",
        "raw.users",
        "stg.events",
        "stg.users",
        "marts.daily_events",
        "marts.user_profile",
        "marts.exec_summary",
    }


def test_union_and_intersection(graph):
    assert select_models(graph, ["tag:gold tag:bronze"]) == {
        "marts.daily_events",
        "marts.user_profile",
        "marts.exec_summary",
        "raw.events",
        "raw.users",
    }
    assert select_models(graph, ["tag:gold,tag:finance"]) == {"marts.daily_events"}


def test_exclude(graph):
    assert select_models(graph, ["tag:gold"], exclude=["tag:deprecated"]) == {
        "marts.daily_events",
        "marts.user_profile",
    }


def test_path_selection(graph):
    assert select_models(graph, ["path:models/marts"]) == {
        "marts.daily_events",
        "marts.user_profile",
        "marts.exec_summary",
    }
    assert select_models(graph, ["path:models/raw/events.sql"]) == {"raw.events"}


def test_kind_owner_and_interval_selection(graph):
    assert select_models(graph, ["kind:INCREMENTAL*"]) == {"stg.events"}
    assert select_models(graph, ["owner:finance-team"]) == {"marts.daily_events"}
    assert select_models(graph, ["interval:FIVE_MINUTE"]) == {"stg.events"}
    # A value with spaces has to be quoted: whitespace is the union operator.
    assert select_models(graph, ['cron:"*/5 * * * *"']) == {"stg.events"}


def test_named_selectors(graph):
    selectors = {
        "finance_core": {
            "union": ["tag:finance+"],
            "exclude": ["tag:deprecated"],
        },
        "gold_only": "tag:gold",
    }
    assert select_models(graph, ["selector:finance_core"], named_selectors=selectors) == {
        "stg.events",
        "marts.daily_events",
        "marts.user_profile",
    }
    assert select_models(graph, ["selector:gold_only"], named_selectors=selectors) == {
        "marts.daily_events",
        "marts.user_profile",
        "marts.exec_summary",
    }


def test_named_selector_intersection(graph):
    selectors = {"gold_finance": {"intersection": ["tag:gold", "tag:finance"]}}
    assert select_models(graph, ["selector:gold_finance"], named_selectors=selectors) == {
        "marts.daily_events"
    }


def test_unknown_selector_and_method_raise(graph):
    with pytest.raises(SelectionError, match="Unknown named selector"):
        select_models(graph, ["selector:nope"])
    with pytest.raises(SelectionError, match="Unknown selection method"):
        select_models(graph, ["nonsense:value"])


def test_self_referencing_selector_raises(graph):
    selectors = {"loop": {"union": ["selector:loop"]}}
    with pytest.raises(SelectionError, match="refers to itself"):
        select_models(graph, ["selector:loop"], named_selectors=selectors)


def test_selection_ignores_dependencies_outside_the_project(graph):
    graph["stg.events"].dependencies.add("external.kafka_topic")
    assert select_models(graph, ["+stg.events"]) == {"raw.events", "stg.events"}


def test_explain_selection_is_sorted_and_unquoted():
    models = {
        '"db"."schema"."b"': model('"db"."schema"."b"', deps=['"db"."schema"."a"']),
        '"db"."schema"."a"': model('"db"."schema"."a"'),
    }
    assert explain_selection(models, ["db.schema.a+"]) == ["db.schema.a", "db.schema.b"]


def test_quoted_fqn_pattern_is_accepted(graph):
    # People paste the quoted FQN that SQLMesh prints; the quotes are dropped.
    assert select_models(graph, ['"marts"."daily_events"']) == {"marts.daily_events"}


def test_list_of_expressions_is_a_union(graph):
    assert select_models(graph, ["tag:bronze", "tag:gold,tag:marketing"]) == {
        "raw.events",
        "raw.users",
        "marts.user_profile",
    }


def test_kind_matches_both_sqlmesh_reprs_and_model_block_spelling():
    models = {
        "a": model("a", kind="IncrementalByTimeRangeKind<dialect: duckdb, time_column: ds>"),
        "b": model("b", kind="FullKind<>"),
    }
    assert select_models(models, ["kind:INCREMENTAL_BY_TIME_RANGE"]) == {"a"}
    assert select_models(models, ["kind:IncrementalByTimeRangeKind"]) == {"a"}
    assert select_models(models, ["kind:FULL"]) == {"b"}
    assert select_models(models, ["kind:INCREMENTAL*"]) == {"a"}
