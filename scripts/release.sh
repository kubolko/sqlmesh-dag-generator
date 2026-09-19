#!/usr/bin/env bash
# Build and publish sqlmesh-dag-generator.
#
#   scripts/release.sh            # build + check only
#   scripts/release.sh testpypi   # build + upload to TestPyPI
#   scripts/release.sh pypi       # build + upload to PyPI
#
# The version comes from pyproject.toml; sqlmesh_dag_generator/__init__.py must
# agree with it (tests/test_packaging.py checks that).
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET="${1:-none}"
VERSION="$(python -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")"

echo "Releasing sqlmesh-dag-generator ${VERSION} (target: ${TARGET})"

echo "==> Cleaning previous builds"
rm -rf build dist ./*.egg-info
find . -type d -name __pycache__ -prune -exec rm -rf {} +

echo "==> Running tests"
python -m pytest -q

echo "==> Building"
python -m build

echo "==> Checking metadata"
python -m twine check dist/*

case "${TARGET}" in
  testpypi)
    python -m twine upload --repository testpypi dist/*
    echo "Installed from TestPyPI with:"
    echo "  pip install --index-url https://test.pypi.org/simple/ \\"
    echo "    --extra-index-url https://pypi.org/simple sqlmesh-dag-generator==${VERSION}"
    ;;
  pypi)
    python -m twine upload dist/*
    echo "Now tag the release:"
    echo "  git tag -a v${VERSION} -m 'Release v${VERSION}' && git push origin v${VERSION}"
    ;;
  none)
    echo "Build only. Artifacts:"
    ls -lh dist/
    ;;
  *)
    echo "Unknown target '${TARGET}' (expected: testpypi, pypi, or nothing)" >&2
    exit 1
    ;;
esac
