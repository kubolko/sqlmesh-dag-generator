"""
Packaging invariants that are easy to break and annoying to discover on PyPI.
"""

import pathlib

import tomllib

import sqlmesh_dag_generator

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_version_matches_pyproject():
    assert sqlmesh_dag_generator.__version__ == PYPROJECT["project"]["version"]


def test_changelog_mentions_the_current_version():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert f"## [{sqlmesh_dag_generator.__version__}]" in changelog


def test_license_file_is_declared_and_present():
    assert PYPROJECT["project"]["license"] == "MIT"
    assert "LICENSE" in PYPROJECT["project"]["license-files"]
    assert (ROOT / "LICENSE").read_text().startswith("MIT License")


def test_public_api_is_importable():
    for name in sqlmesh_dag_generator.__all__:
        assert hasattr(sqlmesh_dag_generator, name), name
