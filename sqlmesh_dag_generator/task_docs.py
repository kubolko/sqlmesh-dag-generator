"""
What a task tells you about its table, in the Airflow UI.

Every task this package creates stands for a table: a SQLMesh model, or a source
table a model reads from. Airflow only knows the task id, which after
sanitising and prefixing looks like ``snowflake__source__API_ODS_DS_LOGS_EVENT_HUB``.
This module turns the model graph into the three places Airflow can show more:

- ``task_display_name`` - the real table name, shown in the graph, the grid and
  the task instance header instead of the id (Airflow 2.9+).
- ``doc_md`` - a card with the table, its lineage and its columns. Airflow 2
  shows it on the task instance details page; Airflow 3 under the
  "Documentation" button on the task page (``/dags/<dag>/tasks/<task>``).
- a short summary logged when a model task starts, so the task instance's own
  log says which table it built and from what.

Everything here is pure string building over :class:`SQLMeshModelInfo`, so it is
cheap at DAG parse time and testable without Airflow or a warehouse.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from sqlmesh_dag_generator.selectors import canonical_kind_name

# doc_md is stored in the serialized DAG; a wide table should not bloat it.
MAX_DOC_COLUMNS = 200
MAX_DOC_LINEAGE = 50


def _unquote(name: str) -> str:
    return str(name).replace('"', "").replace("`", "")


def _cell(value: object) -> str:
    """Make a value safe for a one-line Markdown table cell."""
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def _bullets(names: Sequence[str], limit: int = MAX_DOC_LINEAGE) -> List[str]:
    lines = [f"- `{name}`" for name in names[:limit]]
    if len(names) > limit:
        lines.append(f"- ... and {len(names) - limit} more")
    return lines


def _columns_table(
    columns: Dict[str, str],
    descriptions: Optional[Dict[str, str]] = None,
) -> List[str]:
    descriptions = descriptions or {}
    with_descriptions = any(descriptions.get(name) for name in columns)
    if with_descriptions:
        lines = ["| Column | Type | Description |", "|---|---|---|"]
    else:
        lines = ["| Column | Type |", "|---|---|"]

    names = list(columns)
    for name in names[:MAX_DOC_COLUMNS]:
        data_type = str(columns[name] or "")
        type_cell = "" if data_type.upper() in ("", "UNKNOWN") else f"`{_cell(data_type)}`"
        row = f"| `{_cell(name)}` | {type_cell} |"
        if with_descriptions:
            row += f" {_cell(descriptions.get(name) or '')} |"
        lines.append(row)
    if len(names) > MAX_DOC_COLUMNS:
        lines.append("")
        lines.append(f"... and {len(names) - MAX_DOC_COLUMNS} more columns.")
    return lines


def display_label(name: str, *, source: bool = False, prefix: Optional[str] = None) -> str:
    """
    Human label for a task: the table name, not the sanitised task id.

    ``prefix`` is ``generation.task_id_prefix``; with several SQLMesh projects in
    one DAG two of them can own a table with the same name, so the label keeps
    the project visible.
    """
    label = _unquote(name)
    if source:
        label = f"{label} (source)"
    if prefix:
        label = f"[{prefix}] {label}"
    return label


def model_doc_md(
    info,
    *,
    reads_models: Sequence[str] = (),
    reads_sources: Sequence[str] = (),
    read_by: Sequence[str] = (),
) -> str:
    """
    Documentation card for a model task.

    Args:
        info: the model's :class:`SQLMeshModelInfo`.
        reads_models: display names of the upstream models.
        reads_sources: names of the source tables the model reads directly.
        read_by: display names of the models that read this one.
    """
    lines = [f"### `{info.display_name}`", ""]
    if info.description:
        lines += [info.description.strip(), ""]

    kind = f"`{canonical_kind_name(info.kind) or info.kind}`"
    if getattr(info, "time_column", None):
        kind = f"{kind} on `{info.time_column}`"

    facts = [("Table", f"`{info.display_name}`"), ("Kind", kind)]
    if info.cron:
        schedule = f"`{info.cron}`"
        if info.cron_tz:
            schedule += f" ({info.cron_tz})"
        facts.append(("Cron", schedule))
    if info.owner:
        facts.append(("Owner", _cell(info.owner)))
    if getattr(info, "grains", None):
        facts.append(("Grain", ", ".join(f"`{g}`" for g in info.grains)))
    if info.tags:
        facts.append(("Tags", _cell(", ".join(info.tags))))
    if info.audits:
        facts.append(("Audits", _cell(", ".join(info.audits))))
    if info.project:
        facts.append(("Project", _cell(info.project)))
    if info.path:
        facts.append(("File", f"`{info.path}`"))

    lines += ["| | |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in facts]

    if reads_models or reads_sources:
        lines += ["", "#### Reads from", ""]
        lines += _bullets(sorted(reads_models))
        lines += [f"{line} (source)" for line in _bullets(sorted(reads_sources))]

    if read_by:
        lines += ["", "#### Read by", ""]
        lines += _bullets(sorted(read_by))

    columns = getattr(info, "columns", None) or {}
    if columns:
        lines += ["", f"#### Columns ({len(columns)})", ""]
        lines += _columns_table(columns, getattr(info, "column_descriptions", None))

    return "\n".join(lines)


def source_doc_md(table: str, *, read_by: Sequence[str] = (), external=None) -> str:
    """
    Documentation card for a source-table task.

    ``external`` is the table's :class:`SQLMeshModelInfo` when the project declares
    it in ``external_models.yaml``; its description and columns go on the card.
    Without it the table is one SQLMesh reads but knows nothing about.
    """
    name = getattr(external, "display_name", None) or _unquote(table)
    lines = [f"### `{name}` (source)", ""]

    description = getattr(external, "description", None)
    if description:
        lines += [description.strip(), ""]
    lines += [
        "A table the SQLMesh models read but do not build.",
        "This task only marks where the data enters the pipeline; it runs nothing.",
        "",
    ]

    full_name = _unquote(table)
    parts = full_name.split(".")
    facts = [("Table", f"`{full_name}`")]
    if len(parts) == 3:
        facts += [("Catalog", f"`{parts[0]}`"), ("Schema", f"`{parts[1]}`")]
    elif len(parts) == 2:
        facts.append(("Schema", f"`{parts[0]}`"))
    if external is not None:
        facts.append(("Declared in", "`external_models.yaml`"))
        if getattr(external, "owner", None):
            facts.append(("Owner", _cell(external.owner)))

    lines += ["| | |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in facts]

    if read_by:
        lines += ["", "#### Read by", ""]
        lines += _bullets(sorted(read_by))

    columns = getattr(external, "columns", None) or {}
    if columns:
        lines += ["", f"#### Columns ({len(columns)})", ""]
        lines += _columns_table(columns, getattr(external, "column_descriptions", None))
    elif external is None:
        lines += [
            "",
            "Declare it as a SQLMesh external model (`sqlmesh create_external_models`)",
            "to get its columns and types documented here.",
        ]
    return "\n".join(lines)


def model_run_summary(
    info,
    *,
    reads_models: Iterable[str] = (),
    reads_sources: Iterable[str] = (),
    read_by: Iterable[str] = (),
) -> str:
    """One short block for the task log: what this run builds, and from what."""

    def _short(names: Iterable[str]) -> str:
        names = sorted(names)
        if not names:
            return "-"
        shown = ", ".join(names[:5])
        return shown if len(names) <= 5 else f"{shown} (+{len(names) - 5} more)"

    kind = canonical_kind_name(info.kind) or str(info.kind)
    return (
        f"Model {info.display_name} [{kind}]\n"
        f"  reads models : {_short(reads_models)}\n"
        f"  reads sources: {_short(reads_sources)}\n"
        f"  read by      : {_short(read_by)}"
    )


__all__ = [
    "MAX_DOC_COLUMNS",
    "display_label",
    "model_doc_md",
    "model_run_summary",
    "source_doc_md",
]
