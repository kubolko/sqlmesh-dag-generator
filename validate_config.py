#!/usr/bin/env python3
"""
SQLMesh DAG Generator Configuration Validator

This script helps validate your SQLMesh and Airflow configuration
before deployment to catch common issues.

Usage:
    python validate_config.py /path/to/sqlmesh/project [--gateway prod]
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple


def check_sqlmesh_project(project_path: str) -> Tuple[bool, List[str]]:
    """Check if SQLMesh project structure is valid"""
    issues = []
    project = Path(project_path)

    if not project.exists():
        issues.append(f"❌ Project path does not exist: {project_path}")
        return False, issues

    # Check for config.yaml
    config_path = project / "config.yaml"
    if not config_path.exists():
        issues.append(f"⚠️  config.yaml not found at {config_path}")
    else:
        issues.append(f"✅ Found config.yaml")

    # Check for models directory
    models_path = project / "models"
    if not models_path.exists():
        issues.append(f"⚠️  models directory not found at {models_path}")
    else:
        model_count = len(list(models_path.glob("**/*.sql")))
        issues.append(f"✅ Found models directory with {model_count} SQL files")

    return len([i for i in issues if i.startswith("❌")]) == 0, issues


def check_gateway_config(project_path: str, gateway: str) -> Tuple[bool, List[str]]:
    """Check if specified gateway exists in config"""
    issues = []

    try:
        import yaml
        config_path = Path(project_path) / "config.yaml"

        if not config_path.exists():
            issues.append(f"⚠️  Cannot validate gateway - config.yaml not found")
            return False, issues

        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Check default_gateway
        default_gateway = config.get("default_gateway")
        if default_gateway:
            issues.append(f"✅ Default gateway: {default_gateway}")
        else:
            issues.append(f"⚠️  No default_gateway set in config.yaml")

        # Check if specified gateway exists
        gateways = config.get("gateways", {})
        if gateway:
            if gateway in gateways:
                issues.append(f"✅ Gateway '{gateway}' found in config")

                # Check for required fields
                gw_config = gateways[gateway]
                if "connection" in gw_config:
                    conn_type = gw_config["connection"].get("type", "unknown")
                    issues.append(f"   Connection type: {conn_type}")
                else:
                    issues.append(f"⚠️  Gateway '{gateway}' missing 'connection' config")

            else:
                issues.append(f"❌ Gateway '{gateway}' not found in config.yaml")
                issues.append(f"   Available gateways: {', '.join(gateways.keys())}")
                return False, issues

        # Check for common gateway names
        recommended = ["docker_local", "local", "dev", "staging", "prod"]
        missing_common = [g for g in recommended if g not in gateways]
        if missing_common:
            issues.append(f"💡 Consider adding these gateways: {', '.join(missing_common)}")

        # Check for hardcoded credentials
        for gw_name, gw_config in gateways.items():
            conn = gw_config.get("connection", {})
            if "password" in conn:
                pwd_value = conn["password"]
                if not ("{{" in str(pwd_value) and "}}" in str(pwd_value)):
                    issues.append(f"⚠️  Gateway '{gw_name}' has hardcoded password - use env vars!")

        return True, issues

    except ImportError:
        issues.append("⚠️  PyYAML not installed - cannot validate config.yaml")
        return False, issues
    except Exception as e:
        issues.append(f"❌ Error reading config.yaml: {e}")
        return False, issues


def check_sqlmesh_context(project_path: str, gateway: str = None) -> Tuple[bool, List[str]]:
    """Try to load SQLMesh context"""
    issues = []

    try:
        from sqlmesh import Context

        ctx = Context(paths=project_path, gateway=gateway)
        issues.append(f"✅ SQLMesh context loaded successfully")

        model_count = len(ctx.models) if hasattr(ctx, 'models') else len(ctx._models)
        issues.append(f"✅ Found {model_count} models")

        if model_count == 0:
            issues.append(f"⚠️  No models found - is your models directory populated?")

        return True, issues

    except ImportError:
        issues.append("⚠️  SQLMesh not installed - cannot load context")
        return False, issues
    except Exception as e:
        issues.append(f"❌ Failed to load SQLMesh context: {e}")
        return False, issues


def check_environment_variables() -> Tuple[bool, List[str]]:
    """Check for common environment variables"""
    issues = []
    import os

    common_vars = [
        "POSTGRES_HOST",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "REDSHIFT_HOST",
        "REDSHIFT_USER",
        "REDSHIFT_PASSWORD",
        "SNOWFLAKE_ACCOUNT",
    ]

    found = []
    missing = []

    for var in common_vars:
        if os.getenv(var):
            found.append(var)
        else:
            missing.append(var)

    if found:
        issues.append(f"✅ Found {len(found)} environment variables: {', '.join(found[:3])}...")

    if missing:
        issues.append(f"💡 Not set (OK if not needed): {', '.join(missing[:3])}...")

    return True, issues


def check_dag_generator(project_path: str, gateway: str = None) -> Tuple[bool, List[str]]:
    """Check if DAG generator works"""
    issues = []

    try:
        from sqlmesh_dag_generator import SQLMeshDAGGenerator

        issues.append(f"✅ sqlmesh-dag-generator installed")

        generator = SQLMeshDAGGenerator(
            sqlmesh_project_path=project_path,
            gateway=gateway
        )

        issues.append(f"✅ Generator initialized successfully")

        # Try to extract models
        try:
            models = generator.extract_models()
            issues.append(f"✅ Extracted {len(models)} models")

            if models:
                sample_models = list(models.keys())[:3]
                issues.append(f"   Sample models: {', '.join(sample_models)}")
        except Exception as e:
            issues.append(f"❌ Failed to extract models: {e}")
            return False, issues

        return True, issues

    except ImportError as e:
        issues.append(f"❌ sqlmesh-dag-generator not installed: {e}")
        return False, issues
    except Exception as e:
        issues.append(f"❌ Error initializing generator: {e}")
        return False, issues


def main():
    parser = argparse.ArgumentParser(
        description="Validate SQLMesh DAG Generator configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate project with default gateway
  python validate_config.py /path/to/sqlmesh/project
  
  # Validate project with specific gateway
  python validate_config.py /path/to/sqlmesh/project --gateway prod
  
  # Quick check
  python validate_config.py . --gateway docker_local
        """
    )

    parser.add_argument(
        "project_path",
        help="Path to SQLMesh project directory"
    )

    parser.add_argument(
        "--gateway",
        "-g",
        help="Gateway name to validate (e.g., docker_local, prod)",
        default=None
    )

    args = parser.parse_args()

    print("=" * 80)
    print("SQLMesh DAG Generator Configuration Validator")
    print("=" * 80)
    print(f"\nProject: {args.project_path}")
    if args.gateway:
        print(f"Gateway: {args.gateway}")
    print()

    all_passed = True

    # Check 1: Project structure
    print("📁 Checking SQLMesh Project Structure...")
    passed, issues = check_sqlmesh_project(args.project_path)
    for issue in issues:
        print(f"  {issue}")
    print()
    all_passed = all_passed and passed

    # Check 2: Gateway configuration
    print("🌍 Checking Gateway Configuration...")
    passed, issues = check_gateway_config(args.project_path, args.gateway)
    for issue in issues:
        print(f"  {issue}")
    print()
    all_passed = all_passed and passed

    # Check 3: Environment variables
    print("🔐 Checking Environment Variables...")
    passed, issues = check_environment_variables()
    for issue in issues:
        print(f"  {issue}")
    print()

    # Check 4: SQLMesh context
    print("🔧 Checking SQLMesh Context...")
    passed, issues = check_sqlmesh_context(args.project_path, args.gateway)
    for issue in issues:
        print(f"  {issue}")
    print()
    all_passed = all_passed and passed

    # Check 5: DAG generator
    print("🚀 Checking DAG Generator...")
    passed, issues = check_dag_generator(args.project_path, args.gateway)
    for issue in issues:
        print(f"  {issue}")
    print()
    all_passed = all_passed and passed

    # Summary
    print("=" * 80)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Configuration looks good!")
        print("\nNext steps:")
        print("  1. Deploy your DAG to Airflow")
        print("  2. Set Airflow Variables (if using multi-environment)")
        print("  3. Monitor first DAG run")
        print("\nFor multi-environment setup, see: docs/MULTI_ENVIRONMENT.md")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Please fix the issues above")
        print("\nCommon solutions:")
        print("  - Check that config.yaml exists and is valid YAML")
        print("  - Verify gateway name matches config.yaml")
        print("  - Install SQLMesh: pip install sqlmesh")
        print("  - Install DAG Generator: pip install sqlmesh-dag-generator")
        print("  - Set required environment variables")
        print("\nFor help, see: docs/MULTI_ENVIRONMENT.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())

