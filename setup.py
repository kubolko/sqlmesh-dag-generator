"""
Setup configuration for sqlmesh-dag-generator
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip()
        for line in requirements_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="sqlmesh-dag-generator",
    version="0.1.0",
    description="Open-source Airflow DAG generator for SQLMesh projects",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/sqlmesh-dag-generator",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "docs"]),
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "sqlmesh-dag-gen=sqlmesh_dag_generator.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Code Generators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    keywords="sqlmesh airflow dag generator etl data-engineering",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/sqlmesh-dag-generator/issues",
        "Source": "https://github.com/yourusername/sqlmesh-dag-generator",
        "Documentation": "https://github.com/yourusername/sqlmesh-dag-generator/docs",
    },
)

