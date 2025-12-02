# Contributing to SQLMesh DAG Generator

We love your input! We want to make contributing to SQLMesh DAG Generator as easy and transparent as possible.

## Development Setup

1. **Fork and clone the repository**

```bash
git clone https://github.com/yourusername/sqlmesh-dag-generator.git
cd sqlmesh-dag-generator
```

2. **Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install development dependencies**

```bash
pip install -e ".[dev]"
```

4. **Install pre-commit hooks** (optional but recommended)

```bash
pip install pre-commit
pre-commit install
```

## Development Workflow

1. **Create a branch** for your feature or bugfix

```bash
git checkout -b feature/my-new-feature
```

2. **Make your changes** and write tests

3. **Run tests**

```bash
pytest
pytest --cov=sqlmesh_dag_generator  # with coverage
```

4. **Format code**

```bash
black sqlmesh_dag_generator tests
ruff check sqlmesh_dag_generator tests --fix
```

5. **Type checking** (optional)

```bash
mypy sqlmesh_dag_generator
```

6. **Commit your changes**

```bash
git add .
git commit -m "Add feature: description of changes"
```

7. **Push to your fork and submit a Pull Request**

## Pull Request Guidelines

- **Write clear commit messages** describing what changed and why
- **Add tests** for new features or bug fixes
- **Update documentation** if you're changing functionality
- **Follow the existing code style** (we use Black for formatting)
- **Keep PRs focused** - one feature/fix per PR
- **Link related issues** in the PR description

## Code Style

- We use **Black** for code formatting (line length: 100)
- We use **Ruff** for linting
- Follow **PEP 8** guidelines
- Use **type hints** where appropriate
- Write **docstrings** for all public functions and classes

## Testing Guidelines

- Write tests for all new features
- Maintain or improve code coverage
- Use pytest fixtures for common setup
- Mock external dependencies (SQLMesh, Airflow)

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_config.py

# Run with coverage
pytest --cov=sqlmesh_dag_generator --cov-report=html

# Run with verbose output
pytest -v
```

## Documentation

- Update README.md for user-facing changes
- Add docstrings to all public APIs
- Update examples if adding new features
- Keep documentation clear and concise

## Issue Reporting

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce (be specific!)
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening)

## Feature Requests

We welcome feature requests! Please:

- Explain the use case
- Describe the desired behavior
- Provide examples if possible
- Consider whether this fits the project's scope

## Code of Conduct

- Be respectful and inclusive
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards others

## Questions?

Feel free to open an issue with the `question` label or reach out to the maintainers.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

