"""
SQLMesh maintenance tasks for Airflow: audits, unit tests, linting, janitor, restatement.

``sqlmesh run`` is only part of operating a SQLMesh project. The other commands
- ``audit``, ``test``, ``lint``, ``janitor``, restatement plans - usually end up
as hand-written BashOperators in every team's DAG folder. These helpers give
them a proper task with the same runtime connection handling, ``dag_run.conf``
overrides, and version tolerance as the rest of the package.

Each helper returns a plain ``PythonOperator``, so it composes with whatever
else lives in the DAG::

    with DAG("dwh_sqlmesh_deploy", schedule=None, ...) as dag:
        tests = generator.create_unit_test_task(dag)
        lint = generator.create_lint_task(dag)
        deploy = generator.create_plan_apply_task(dag)
        [tests, lint] >> deploy
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)


def supported_kwargs(func: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep only the kwargs a given SQLMesh callable actually accepts.

    SQLMesh moves fast: ``plan(min_intervals=...)`` and ``run(no_auto_upstream=...)``
    are recent, ``skip_audits`` came and went. Filtering against the real
    signature keeps one DAG file working across the versions in a fleet.
    """
    import inspect

    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins without signatures
        return dict(kwargs)

    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        # The callable takes **kwargs (or is a test double); nothing to filter.
        return dict(kwargs)

    accepted = {k: v for k, v in kwargs.items() if k in params}
    dropped = sorted(set(kwargs) - set(accepted))
    if dropped:
        logger.warning(
            "This SQLMesh version does not support %s for %s; ignoring.",
            ", ".join(dropped),
            getattr(func, "__name__", func),
        )
    return accepted


def _as_model_list(value: Union[str, Sequence[str], None]) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    models = [str(v) for v in value]
    return models or None


class SQLMeshOpsTasksMixin:
    """Maintenance-task factories mixed into :class:`SQLMeshDAGGenerator`."""

    # -- audits -------------------------------------------------------------

    def create_audit_task(
        self,
        dag,
        task_id: str = "sqlmesh_audit",
        models: Union[str, Sequence[str], None] = None,
        execution_timeout: Optional[timedelta] = None,
        blocking: bool = True,
    ):
        """
        Run SQLMesh audits for the DAG's data interval.

        Args:
            dag: Airflow DAG object.
            task_id: Task ID for the audit operator.
            models: Models to audit; defaults to every model in this generator.
            execution_timeout: Optional Airflow execution timeout.
            blocking: When False, a failed audit is logged instead of failing
                the task (the SQLMesh equivalent of a warn-level dbt test).

        Returns:
            PythonOperator running ``Context.audit``.
        """
        from sqlmesh import Context

        from sqlmesh_dag_generator.airflow_compat import PythonOperator

        selected = _as_model_list(models)

        def run_audits(**context):
            from airflow.exceptions import AirflowException

            dag_run = context.get("dag_run")
            conf = dag_run.conf if dag_run and dag_run.conf else {}
            audit_models = _as_model_list(conf.get("models")) or selected
            if audit_models is None:
                if not self.models:
                    self.extract_models()
                audit_models = [info.display_name for info in self.models.values()]

            start = conf.get("start") or context.get("data_interval_start")
            end = conf.get("end") or context.get("data_interval_end")
            if start is None or end is None:
                raise AirflowException(
                    "SQLMesh audits need a time interval; run this task in a scheduled "
                    "DAG or pass start/end in dag_run.conf."
                )

            if self.merged_config is None:
                self.load_sqlmesh_context()
            run_ctx = Context(**self._build_runtime_context_kwargs())

            logger.info("Auditing %s model(s) for %s -> %s", len(audit_models), start, end)
            kwargs = supported_kwargs(
                run_ctx.audit, {"start": start, "end": end, "models": audit_models}
            )
            passed = run_ctx.audit(**kwargs)
            # SQLMesh returns False when an audit failed but did not raise.
            if passed is False:
                message = f"SQLMesh audits failed for: {audit_models}"
                if blocking:
                    raise AirflowException(message)
                logger.warning("%s (non-blocking)", message)
            return {
                "status": "passed" if passed is not False else "failed",
                "models": audit_models,
                "start": str(start),
                "end": str(end),
            }

        return PythonOperator(
            task_id=task_id,
            python_callable=run_audits,
            execution_timeout=execution_timeout,
            dag=dag,
        )

    # -- unit tests ---------------------------------------------------------

    def create_unit_test_task(
        self,
        dag,
        task_id: str = "sqlmesh_unit_tests",
        match_patterns: Optional[Sequence[str]] = None,
        execution_timeout: Optional[timedelta] = None,
    ):
        """
        Run the project's SQLMesh unit tests (``sqlmesh test``) as a task.

        Belongs on the deploy DAG, upstream of plan/apply: it is the cheapest
        gate that stops a broken model from reaching production.
        """
        from sqlmesh import Context

        from sqlmesh_dag_generator.airflow_compat import PythonOperator

        patterns = list(match_patterns) if match_patterns else None

        def run_unit_tests(**context):
            from airflow.exceptions import AirflowException

            if self.merged_config is None:
                self.load_sqlmesh_context()
            run_ctx = Context(**self._build_runtime_context_kwargs())

            kwargs = supported_kwargs(run_ctx.test, {"match_patterns": patterns})
            result = run_ctx.test(**kwargs)

            failures = len(getattr(result, "failures", []) or [])
            errors = len(getattr(result, "errors", []) or [])
            total = getattr(result, "testsRun", None)
            logger.info(
                "SQLMesh unit tests: %s run, %s failed, %s errored", total, failures, errors
            )

            if failures or errors:
                raise AirflowException(
                    f"SQLMesh unit tests failed ({failures} failure(s), {errors} error(s)). "
                    f"See the task log for the failing assertions."
                )
            return {"status": "passed", "tests_run": total}

        return PythonOperator(
            task_id=task_id,
            python_callable=run_unit_tests,
            execution_timeout=execution_timeout,
            dag=dag,
        )

    # -- linter -------------------------------------------------------------

    def create_lint_task(
        self,
        dag,
        task_id: str = "sqlmesh_lint",
        models: Union[str, Sequence[str], None] = None,
        raise_on_error: bool = True,
        execution_timeout: Optional[timedelta] = None,
    ):
        """
        Run the SQLMesh linter (``sqlmesh lint``) against the project.

        Requires a SQLMesh version with ``Context.lint_models`` (0.150+). On
        older versions the task logs a warning and succeeds, so the same DAG
        file keeps working while a fleet upgrades.
        """
        from sqlmesh import Context

        from sqlmesh_dag_generator.airflow_compat import PythonOperator

        selected = _as_model_list(models)

        def run_lint(**context):
            from airflow.exceptions import AirflowException

            if self.merged_config is None:
                self.load_sqlmesh_context()
            run_ctx = Context(**self._build_runtime_context_kwargs())

            lint_models = getattr(run_ctx, "lint_models", None)
            if lint_models is None:
                logger.warning(
                    "This SQLMesh version has no linter (Context.lint_models); skipping."
                )
                return {"status": "skipped", "reason": "unsupported_sqlmesh_version"}

            kwargs = supported_kwargs(lint_models, {"models": selected, "raise_on_error": False})
            violations = lint_models(**kwargs) or []
            # violation_type is "error" or "warning" (SQLMesh linter rules can be
            # configured per project); only errors should stop a deploy.
            errors = [
                v for v in violations if str(getattr(v, "violation_type", "error")) == "error"
            ]
            for violation in violations:
                logger.warning("Lint: %s", violation)

            if errors and raise_on_error:
                raise AirflowException(
                    f"SQLMesh linter reported {len(errors)} error-level violation(s)."
                )
            return {
                "status": "passed" if not errors else "violations",
                "violations": len(violations),
                "errors": len(errors),
            }

        return PythonOperator(
            task_id=task_id,
            python_callable=run_lint,
            execution_timeout=execution_timeout,
            dag=dag,
        )

    # -- janitor ------------------------------------------------------------

    def create_janitor_task(
        self,
        dag,
        task_id: str = "sqlmesh_janitor",
        environment: Optional[str] = None,
        ignore_ttl: bool = False,
        execution_timeout: Optional[timedelta] = None,
    ):
        """
        Drop expired environments and orphaned physical tables (``sqlmesh janitor``).

        Worth its own nightly DAG on busy projects: development environments and
        their snapshot tables otherwise pile up in the warehouse forever.
        """
        from sqlmesh import Context

        from sqlmesh_dag_generator.airflow_compat import PythonOperator

        def run_janitor(**context):
            dag_run = context.get("dag_run")
            conf = dag_run.conf if dag_run and dag_run.conf else {}
            target_environment = conf.get("environment", environment)

            if self.merged_config is None:
                self.load_sqlmesh_context()
            run_ctx = Context(**self._build_runtime_context_kwargs())

            kwargs = supported_kwargs(
                run_ctx.run_janitor,
                {"ignore_ttl": ignore_ttl, "environment": target_environment},
            )
            logger.info("Running SQLMesh janitor (%s)", kwargs or "defaults")
            result = run_ctx.run_janitor(**kwargs)
            return {
                "status": "completed",
                "result": bool(result),
                "environment": target_environment,
            }

        return PythonOperator(
            task_id=task_id,
            python_callable=run_janitor,
            execution_timeout=execution_timeout,
            dag=dag,
        )

    # -- restatement --------------------------------------------------------

    def create_restate_task(
        self,
        dag,
        task_id: str = "sqlmesh_restate",
        default_models: Union[str, Sequence[str], None] = None,
        default_start: Optional[Union[str, datetime]] = None,
        default_end: Optional[Union[str, datetime]] = None,
        execution_timeout: Optional[timedelta] = None,
    ):
        """
        Restate (reprocess) a window of one or more models - dbt's ``--full-refresh``.

        Unlike :meth:`create_manual_backfill_task`, which replays intervals that
        SQLMesh considers missing, a restatement tells SQLMesh to *forget* what
        it has for that window and rebuild it, cascading to downstream models.

        ``dag_run.conf`` overrides: ``models``, ``start``, ``end``.
        """
        from sqlmesh import Context

        from sqlmesh_dag_generator.airflow_compat import PythonOperator

        preset_models = _as_model_list(default_models)

        def run_restate(**context):
            from airflow.exceptions import AirflowException

            dag_run = context.get("dag_run")
            conf = dag_run.conf if dag_run and dag_run.conf else {}

            models = _as_model_list(conf.get("models")) or preset_models
            if not models:
                raise AirflowException(
                    "Restatement needs models: pass default_models=... or "
                    "dag_run.conf={'models': ['schema.model']}."
                )

            start = conf.get("start", default_start)
            end = conf.get("end", default_end)
            if start is None:
                raise AirflowException(
                    "Restatement needs a start boundary (default_start or dag_run.conf['start'])."
                )
            if end is None:
                end = datetime.now(timezone.utc).replace(microsecond=0)

            if self.merged_config is None:
                self.load_sqlmesh_context()
            run_ctx = Context(**self._build_runtime_context_kwargs())

            logger.info("Restating %s for %s -> %s", models, start, end)
            kwargs = supported_kwargs(
                run_ctx.plan,
                {
                    "environment": self.config.sqlmesh.environment,
                    "restate_models": models,
                    "start": start,
                    "end": end,
                    "no_prompts": True,
                    "auto_apply": True,
                },
            )
            run_ctx.plan(**kwargs)
            return {
                "status": "restated",
                "models": models,
                "start": str(start),
                "end": str(end),
            }

        return PythonOperator(
            task_id=task_id,
            python_callable=run_restate,
            execution_timeout=execution_timeout,
            dag=dag,
        )


__all__ = ["SQLMeshOpsTasksMixin", "supported_kwargs"]
