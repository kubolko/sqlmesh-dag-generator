"""
Command-line interface for SQLMesh DAG Generator
"""

import argparse
import logging
import sys
from pathlib import Path

from sqlmesh_dag_generator import SQLMeshDAGGenerator
from sqlmesh_dag_generator.config import DAGGeneratorConfig


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def list_models(generator) -> None:
    """Print the selected models with their schedule and tags (like `dbt ls`)."""
    generator.extract_models()
    if not generator.models:
        print("No models matched the selection.")
        return

    rows = sorted(
        (info.display_name, info.cron or "-", ",".join(info.tags or []) or "-")
        for info in generator.models.values()
    )
    width = max(len(name) for name, _, _ in rows)
    for name, cron, tags in rows:
        print(f"{name:<{width}}  {cron:<12}  {tags}")
    print(f"\n{len(rows)} model(s)")


def list_groups(generator) -> None:
    """Print the configured DAG groups and how they depend on each other."""
    from sqlmesh_dag_generator.dag_groups import describe_dag_groups

    if not generator.config.dag_groups:
        print("No dag_groups are configured.")
        return

    generator.extract_models()
    for group in describe_dag_groups(generator.config, generator.models):
        print(f"{group['dag_id']}  (schedule: {group['schedule']})")
        print(f"  select : {' '.join(group['select']) or '(everything)'}")
        if group["exclude"]:
            print(f"  exclude: {' '.join(group['exclude'])}")
        print(f"  models : {len(group['models'])}")
        for model in group["models"]:
            print(f"    - {model}")
        if group["external_upstreams"]:
            print(f"  waits for ({group['wait_for_upstream']}):")
            for model, owner in sorted(group["external_upstreams"].items()):
                print(f"    - {model} (from {owner})")
        print()


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Generate Airflow DAGs from SQLMesh projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate DAG from SQLMesh project
  sqlmesh-dag-gen --project-path /path/to/sqlmesh --dag-id my_dag

  # Generate with custom output directory
  sqlmesh-dag-gen --project-path /path/to/sqlmesh --output-dir /path/to/dags

  # Use configuration file
  sqlmesh-dag-gen --config config.yaml

  # Validate without generating
  sqlmesh-dag-gen --project-path /path/to/sqlmesh --validate-only

  # See what a selection matches before deploying it
  sqlmesh-dag-gen -p /path/to/sqlmesh --select "tag:finance+" --list-models

  # Inspect the configured DAG groups
  sqlmesh-dag-gen --config config.yaml --list-groups

  # Write an orchestration manifest for CI to diff
  sqlmesh-dag-gen --config config.yaml --manifest target/orchestration.json
        """,
    )

    # Configuration source
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument("--config", "-c", help="Path to configuration YAML file")
    config_group.add_argument("--project-path", "-p", help="Path to SQLMesh project")

    # SQLMesh options
    parser.add_argument(
        "--environment",
        "-e",
        default="",
        help=(
            "SQLMesh virtual environment. Leave empty (the default) for production "
            "runs and use --gateway to switch between dev/staging/prod."
        ),
    )
    parser.add_argument("--gateway", "-g", help="SQLMesh gateway name")

    # Airflow DAG options
    parser.add_argument("--dag-id", help="Airflow DAG ID")
    parser.add_argument("--schedule", help="Airflow schedule interval (cron expression or preset)")
    parser.add_argument("--tags", nargs="+", default=["sqlmesh"], help="Airflow DAG tags")

    # Generation options
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./dags",
        help="Output directory for generated DAG files (default: ./dags)",
    )
    parser.add_argument(
        "--operator-type",
        choices=["python", "bash", "kubernetes"],
        default="python",
        help="Airflow operator type to use (default: python)",
    )
    parser.add_argument("--include-models", nargs="+", help="Only include these models")
    parser.add_argument("--exclude-models", nargs="+", help="Exclude these models")
    parser.add_argument(
        "--select",
        "-s",
        nargs="+",
        help='dbt-style selection, e.g. "tag:finance+" "+path:models/marts"',
    )
    parser.add_argument(
        "--exclude", nargs="+", help='Selection to subtract from --select, e.g. "tag:deprecated"'
    )

    # Actions
    parser.add_argument(
        "--validate-only", action="store_true", help="Only validate, do not generate DAG"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Generate DAG code but do not write to file"
    )
    parser.add_argument(
        "--list-models",
        "-l",
        action="store_true",
        help='List the selected models and exit (the "dbt ls" of this package)',
    )
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="Show the configured DAG groups, their models and cross-group edges",
    )
    parser.add_argument(
        "--manifest",
        metavar="PATH",
        help="Write an orchestration manifest (JSON) describing every model task",
    )

    # Other options
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Load or build configuration
        if args.config:
            logger.info(f"Loading configuration from: {args.config}")
            config = DAGGeneratorConfig.from_file(args.config)
        else:
            if not args.project_path:
                parser.error("Either --config or --project-path must be provided")

            if not args.dag_id:
                # Generate DAG ID from project path
                project_name = Path(args.project_path).name
                args.dag_id = f"sqlmesh_{project_name}"

            logger.info("Building configuration from command-line arguments")
            config = DAGGeneratorConfig.from_dict(
                {
                    "sqlmesh": {
                        "project_path": args.project_path,
                        "environment": args.environment,
                        "gateway": args.gateway,
                    },
                    "airflow": {
                        "dag_id": args.dag_id,
                        "schedule_interval": args.schedule,
                        "tags": args.tags,
                    },
                    "generation": {
                        "output_dir": args.output_dir,
                        "operator_type": args.operator_type,
                        "include_models": args.include_models,
                        "exclude_models": args.exclude_models,
                        "select": args.select,
                        "exclude": args.exclude,
                        "dry_run": args.dry_run,
                    },
                }
            )

        # Command-line selection wins over the config file
        if args.select:
            config.generation.select = args.select
        if args.exclude:
            config.generation.exclude = args.exclude

        # Create generator
        generator = SQLMeshDAGGenerator(config=config)

        # Read-only commands run before validation writes anything
        if args.list_models:
            list_models(generator)
            sys.exit(0)

        if args.list_groups:
            list_groups(generator)
            sys.exit(0)

        if args.manifest:
            from sqlmesh_dag_generator.manifest import write_manifest

            path = write_manifest(generator, args.manifest)
            logger.info("Manifest written to: %s", path)
            sys.exit(0)

        # Validate
        logger.info("Validating SQLMesh project...")
        if not generator.validate():
            logger.error("Validation failed")
            sys.exit(1)

        logger.info("Validation passed")

        if args.validate_only:
            logger.info("Validation complete (--validate-only specified)")
            sys.exit(0)

        # Generate DAG
        logger.info(f"Generating Airflow DAG: {config.airflow.dag_id}")
        dag_code = generator.generate_dag()

        if args.dry_run:
            logger.info("=" * 60)
            logger.info("Generated DAG (dry-run mode):")
            logger.info("=" * 60)
            print(dag_code)
        else:
            output_path = generator._get_output_path()
            logger.info(f"DAG file generated: {output_path}")

        logger.info("Success!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
