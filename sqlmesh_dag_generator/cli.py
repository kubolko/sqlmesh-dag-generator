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
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


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
        """
    )

    # Configuration source
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        '--config', '-c',
        help='Path to configuration YAML file'
    )
    config_group.add_argument(
        '--project-path', '-p',
        help='Path to SQLMesh project'
    )

    # SQLMesh options
    parser.add_argument(
        '--environment', '-e',
        default='prod',
        help='SQLMesh environment (default: prod)'
    )
    parser.add_argument(
        '--gateway', '-g',
        help='SQLMesh gateway name'
    )

    # Airflow DAG options
    parser.add_argument(
        '--dag-id',
        help='Airflow DAG ID'
    )
    parser.add_argument(
        '--schedule',
        help='Airflow schedule interval (cron expression or preset)'
    )
    parser.add_argument(
        '--tags',
        nargs='+',
        default=['sqlmesh'],
        help='Airflow DAG tags'
    )

    # Generation options
    parser.add_argument(
        '--output-dir', '-o',
        default='./dags',
        help='Output directory for generated DAG files (default: ./dags)'
    )
    parser.add_argument(
        '--operator-type',
        choices=['python', 'bash', 'kubernetes'],
        default='python',
        help='Airflow operator type to use (default: python)'
    )
    parser.add_argument(
        '--include-models',
        nargs='+',
        help='Only include these models'
    )
    parser.add_argument(
        '--exclude-models',
        nargs='+',
        help='Exclude these models'
    )

    # Actions
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate, do not generate DAG'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate DAG code but do not write to file'
    )

    # Other options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

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
            config = DAGGeneratorConfig.from_dict({
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
                    "dry_run": args.dry_run,
                },
            })

        # Create generator
        generator = SQLMeshDAGGenerator(config=config)

        # Validate
        logger.info("Validating SQLMesh project...")
        if not generator.validate():
            logger.error("Validation failed")
            sys.exit(1)

        logger.info("✓ Validation passed")

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
            logger.info(f"✓ DAG file generated: {output_path}")

        logger.info("Success!")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()

