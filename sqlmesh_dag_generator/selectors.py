"""
Model selection in the style of ``dbt ls --select`` / ``sqlmesh plan --select-model``.

The point is to stop describing "which models belong to this DAG" as a hand-written
list of FQNs. A selection is a small expression evaluated against the model graph:

    tag:finance+          finance-tagged models and everything downstream
    +tag:finance          finance-tagged models and everything upstream
    @dwh.orders           orders, its children, and everything those children need
    path:models/marts     everything under models/marts
    kind:INCREMENTAL*     every incremental model kind
    tag:core,owner:dwh    intersection: core-tagged AND owned by dwh

Several expressions form a union (a list, or one whitespace-separated string);
a comma inside one expression is an intersection. This mirrors dbt's node
selection syntax closely enough that dbt muscle memory works here.

Supported methods
-----------------
``tag:``       SQLMesh model tag (wildcards allowed)
``path:``      model file path, relative to the project root
``fqn:``       fully qualified / display name (the default when no method is given)
``kind:``      model kind, e.g. ``FULL``, ``INCREMENTAL_BY_TIME_RANGE``
``owner:``     model owner
``project:``   SQLMesh ``project`` field (multi-repo projects)
``interval:``  interval unit, e.g. ``FIVE_MINUTE``, ``HOUR``, ``DAY``
``cron:``      the model cron string
``selector:``  a named selector defined in configuration

Graph operators
---------------
``+model`` / ``3+model``   ancestors (optionally depth-limited)
``model+`` / ``model+3``   descendants (optionally depth-limited)
``@model``                 model, its descendants, and the ancestors of those
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

SUPPORTED_METHODS = (
    "tag",
    "path",
    "fqn",
    "name",
    "kind",
    "owner",
    "project",
    "interval",
    "cron",
    "selector",
)

_ATOM_RE = re.compile(
    r"""
    ^
    (?P<at>@)?
    (?:(?P<ancestor_depth>\d*)\+)?
    (?P<body>.*?)
    (?:\+(?P<descendant_depth>\d*))?
    $
    """,
    re.VERBOSE,
)


class SelectionError(ValueError):
    """Raised for malformed selection expressions or unknown selector names."""


def normalize_name(name: str) -> str:
    """Drop the quoting SQLMesh puts around FQN parts (``"db"."sch"."tbl"``)."""
    return str(name).replace('"', "").replace("`", "")


@dataclass(frozen=True)
class SelectableModel:
    """The subset of model metadata a selection can match on."""

    key: str
    name: str = ""
    path: str = ""
    tags: Sequence[str] = ()
    kind: str = ""
    owner: str = ""
    project: str = ""
    interval_unit: str = ""
    cron: str = ""

    @property
    def names(self) -> Set[str]:
        """Every spelling of this model a user might reasonably type."""
        out = {normalize_name(self.key)}
        if self.name:
            out.add(normalize_name(self.name))
        out |= {n.split(".")[-1] for n in list(out)}
        return out


@dataclass
class SelectionGraph:
    """Model graph a selection is evaluated against."""

    models: Dict[str, SelectableModel]
    parents: Dict[str, Set[str]] = field(default_factory=dict)
    children: Dict[str, Set[str]] = field(default_factory=dict)

    @classmethod
    def from_model_infos(cls, model_infos: Mapping[str, Any]) -> SelectionGraph:
        """Build a graph from ``{key: SQLMeshModelInfo}`` (or anything alike)."""
        models: Dict[str, SelectableModel] = {}
        parents: Dict[str, Set[str]] = {}

        for key, info in model_infos.items():
            models[key] = SelectableModel(
                key=key,
                name=str(getattr(info, "display_name", "") or getattr(info, "name", "") or key),
                path=str(getattr(info, "path", "") or ""),
                tags=tuple(str(t) for t in (getattr(info, "tags", None) or [])),
                kind=str(getattr(info, "kind", "") or ""),
                owner=str(getattr(info, "owner", "") or ""),
                project=str(getattr(info, "project", "") or ""),
                interval_unit=str(getattr(info, "interval_unit", "") or ""),
                cron=str(getattr(info, "cron", "") or ""),
            )
            # Dependencies on tables that are not models in this project (raw
            # sources) are not selectable, so they are dropped from the graph.
            deps = set(getattr(info, "dependencies", None) or set())
            parents[key] = {d for d in deps if d in model_infos}

        children: Dict[str, Set[str]] = {key: set() for key in models}
        for key, deps in parents.items():
            for dep in deps:
                children.setdefault(dep, set()).add(key)

        return cls(models=models, parents=parents, children=children)

    def ancestors(self, key: str, depth: Optional[int] = None) -> Set[str]:
        return self._walk(key, self.parents, depth)

    def descendants(self, key: str, depth: Optional[int] = None) -> Set[str]:
        return self._walk(key, self.children, depth)

    def _walk(
        self,
        key: str,
        edges: Mapping[str, Set[str]],
        depth: Optional[int],
    ) -> Set[str]:
        seen: Set[str] = set()
        frontier = {key}
        level = 0
        while frontier and (depth is None or level < depth):
            nxt: Set[str] = set()
            for node in frontier:
                for neighbour in edges.get(node, set()):
                    if neighbour not in seen and neighbour != key:
                        seen.add(neighbour)
                        nxt.add(neighbour)
            frontier = nxt
            level += 1
        return seen


def _matches_glob(pattern: str, candidates: Iterable[str]) -> bool:
    lowered = pattern.lower()
    return any(fnmatch.fnmatchcase(str(c).lower(), lowered) for c in candidates if c)


def _match_path(pattern: str, model_path: str) -> bool:
    if not model_path:
        return False
    path = model_path.replace("\\", "/").lstrip("./")
    pattern = pattern.replace("\\", "/").rstrip("/")
    if any(ch in pattern for ch in "*?["):
        # A trailing /** is implied: "models/marts/*" should match nested files.
        return fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path, f"{pattern}/*")
    # Directory or exact-file prefix match, on segment boundaries.
    return path == pattern or path.endswith(f"/{pattern}") or f"/{path}".find(f"/{pattern}/") >= 0


def _kind_aliases(kind: str) -> Set[str]:
    """
    Every spelling of a model kind.

    SQLMesh hands us the kind object's repr (``IncrementalByTimeRangeKind<...>``),
    while people write the kind as it appears in the MODEL block
    (``INCREMENTAL_BY_TIME_RANGE``). Accept both.
    """
    if not kind:
        return set()
    base = kind.split("<")[0].strip()
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", base).upper()
    if snake.endswith("_KIND"):
        snake = snake[: -len("_KIND")]
    return {kind, base, snake}


def _match_method(model: SelectableModel, method: str, value: str) -> bool:
    if method == "tag":
        return _matches_glob(value, model.tags)
    if method == "path":
        return _match_path(value, model.path)
    if method in ("fqn", "name"):
        return _matches_glob(value, model.names)
    if method == "kind":
        return _matches_glob(value, _kind_aliases(model.kind))
    if method == "owner":
        return _matches_glob(value, [model.owner])
    if method == "project":
        return _matches_glob(value, [model.project])
    if method == "interval":
        interval = model.interval_unit.upper().replace("INTERVALUNIT.", "")
        return _matches_glob(value, [interval, model.interval_unit])
    if method == "cron":
        return _matches_glob(value, [model.cron])
    raise SelectionError(
        f"Unknown selection method '{method}:'. Supported methods: "
        f"{', '.join(SUPPORTED_METHODS)}"
    )


def _parse_depth(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    return int(raw) if raw else None


def _evaluate_atom(
    atom: str,
    graph: SelectionGraph,
    named_selectors: Mapping[str, Any],
    _stack: Sequence[str] = (),
) -> Set[str]:
    atom = atom.strip()
    if not atom:
        return set()

    match = _ATOM_RE.match(atom)
    if not match:  # pragma: no cover - the regex accepts everything non-empty
        raise SelectionError(f"Could not parse selection atom: {atom!r}")

    body = match.group("body").strip()
    if not body:
        raise SelectionError(f"Selection atom {atom!r} has no model expression")

    at_operator = bool(match.group("at"))
    want_ancestors = match.group("ancestor_depth") is not None
    want_descendants = match.group("descendant_depth") is not None
    ancestor_depth = _parse_depth(match.group("ancestor_depth"))
    descendant_depth = _parse_depth(match.group("descendant_depth"))

    method, _, value = body.partition(":")
    if not value:
        method, value = "fqn", body
    method = method.strip().lower()

    if method == "selector":
        matched = _evaluate_named_selector(value.strip(), graph, named_selectors, _stack)
    else:
        matched = {
            key
            for key, model in graph.models.items()
            if _match_method(model, method, value.strip())
        }

    selected = set(matched)
    for key in matched:
        if want_ancestors or at_operator:
            selected |= graph.ancestors(key, ancestor_depth)
        if want_descendants or at_operator:
            selected |= graph.descendants(key, descendant_depth)

    if at_operator:
        # dbt's @: also pull in whatever the descendants depend on.
        for key in list(selected):
            selected |= graph.ancestors(key)

    return selected


def _tokenize(expression: str) -> List[List[str]]:
    """
    Split an expression into union groups of intersection atoms.

    Whitespace unions, commas intersect - but neither applies inside quotes, so
    values that contain spaces or commas can be written as ``cron:"0 1,13 * * *"``.
    Quote characters themselves are dropped, which also lets people paste the
    quoted FQN SQLMesh prints (``"db"."schema"."table"``).
    """
    groups: List[List[str]] = []
    atoms: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None

    def end_atom() -> None:
        if current:
            atoms.append("".join(current))
            current.clear()

    def end_group() -> None:
        end_atom()
        if atoms:
            groups.append(list(atoms))
            atoms.clear()

    for char in str(expression):
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
            continue
        if char in "\"'":
            quote = char
        elif char.isspace():
            end_group()
        elif char == ",":
            end_atom()
        else:
            current.append(char)

    end_group()
    return groups


def _evaluate_expression(
    expression: str,
    graph: SelectionGraph,
    named_selectors: Mapping[str, Any],
    _stack: Sequence[str] = (),
) -> Set[str]:
    """Evaluate one expression: whitespace unions, commas intersect."""
    selected: Set[str] = set()
    for atoms in _tokenize(expression):
        if not atoms:
            continue
        intersected: Optional[Set[str]] = None
        for atom in atoms:
            result = _evaluate_atom(atom, graph, named_selectors, _stack)
            intersected = result if intersected is None else (intersected & result)
        selected |= intersected or set()
    return selected


def _evaluate_named_selector(
    name: str,
    graph: SelectionGraph,
    named_selectors: Mapping[str, Any],
    _stack: Sequence[str] = (),
) -> Set[str]:
    if name in _stack:
        raise SelectionError(
            f"Named selector '{name}' refers to itself: {' -> '.join([*_stack, name])}"
        )
    if name not in named_selectors:
        known = ", ".join(sorted(named_selectors)) or "(none defined)"
        raise SelectionError(f"Unknown named selector '{name}'. Defined selectors: {known}")

    definition = named_selectors[name]
    stack = [*_stack, name]

    if isinstance(definition, str):
        return _evaluate_expression(definition, graph, named_selectors, stack)
    if isinstance(definition, (list, tuple, set)):
        return _evaluate_expression(
            " ".join(str(d) for d in definition), graph, named_selectors, stack
        )
    if isinstance(definition, Mapping):
        union = definition.get("union") or definition.get("select") or []
        if isinstance(union, str):
            union = [union]
        intersection = definition.get("intersection") or []
        if isinstance(intersection, str):
            intersection = [intersection]
        exclude = definition.get("exclude") or []
        if isinstance(exclude, str):
            exclude = [exclude]

        selected: Set[str] = set()
        seeded = False
        for expression in union:
            selected |= _evaluate_expression(expression, graph, named_selectors, stack)
            seeded = True
        for expression in intersection:
            result = _evaluate_expression(expression, graph, named_selectors, stack)
            selected = result if not seeded else (selected & result)
            seeded = True
        if not seeded:
            raise SelectionError(
                f"Named selector '{name}' defines neither 'union' nor 'intersection'"
            )
        for expression in exclude:
            selected -= _evaluate_expression(expression, graph, named_selectors, stack)
        return selected

    raise SelectionError(
        f"Named selector '{name}' must be a string, a list, or a mapping "
        f"(got {type(definition).__name__})"
    )


def select_models(
    model_infos: Mapping[str, Any],
    select: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
    named_selectors: Optional[Mapping[str, Any]] = None,
) -> Set[str]:
    """
    Return the keys of ``model_infos`` matched by ``select`` minus ``exclude``.

    ``select=None`` (or an empty list) means "every model", which keeps the
    common case - one DAG for the whole project - free of ceremony.
    """
    graph = SelectionGraph.from_model_infos(model_infos)
    named = dict(named_selectors or {})

    if isinstance(select, str):
        select = [select]
    if isinstance(exclude, str):
        exclude = [exclude]

    if not select:
        selected = set(graph.models)
    else:
        selected = set()
        for expression in select:
            selected |= _evaluate_expression(expression, graph, named)

    for expression in exclude or []:
        selected -= _evaluate_expression(expression, graph, named)

    return selected


def explain_selection(
    model_infos: Mapping[str, Any],
    select: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
    named_selectors: Optional[Mapping[str, Any]] = None,
) -> List[str]:
    """Human-readable, sorted list of the selected models (handy in logs and CLI)."""
    selected = select_models(model_infos, select, exclude, named_selectors)
    return sorted(normalize_name(key) for key in selected)


__all__ = [
    "SUPPORTED_METHODS",
    "SelectableModel",
    "SelectionError",
    "SelectionGraph",
    "explain_selection",
    "normalize_name",
    "select_models",
]
