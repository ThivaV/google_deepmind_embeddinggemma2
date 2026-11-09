"""Packaging for {{PROJECT_TITLE}}.

The project uses a ``src/`` layout, so the importable package lives at
``src/{{PACKAGE_NAME}}/``. Install it in editable mode while developing::

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
    pip install -e .

Runtime dependencies are not duplicated here: ``install_requires`` is read
straight out of requirements.txt, which stays the single source of truth.
"""

import re
from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).resolve().parent

REPO_URL = "https://github.com/{{GITHUB_REPO}}"

FALLBACK_VERSION = "0.1.0"


def read_version() -> str:
    """Read ``__version__`` from the package, keeping one source of truth.

    The package is the authority: app.py, main.py and the tests all import
    ``__version__`` from it, so bumping it there is enough.
    """
    for init in sorted((ROOT / "src").glob("*/__init__.py")):
        match = re.search(
            r"^__version__\s*=\s*[\"']([^\"']+)[\"']",
            init.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            return match.group(1)
    return FALLBACK_VERSION


def read_long_description() -> str:
    """Use README.md as the long description, falling back to the one-liner."""
    readme = ROOT / "README.md"
    if readme.exists():
        return readme.read_text(encoding="utf-8")
    return "{{PROJECT_DESCRIPTION}}"


def read_requirements(filename: str = "requirements.txt") -> list[str]:
    """Read runtime requirements, ignoring comments, blank lines and pip options."""
    path = ROOT / filename
    if not path.exists():
        return []

    requirements: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        # Skip pip flags (-e, -r, --index-url, ...) -- they are not requirements.
        if not line or line.startswith("-"):
            continue
        requirements.append(line)
    return requirements


setup(
    name="{{PACKAGE_NAME}}",
    version=read_version(),
    author="{{AUTHOR_NAME}}",
    author_email="{{AUTHOR_EMAIL}}",
    description="{{PROJECT_DESCRIPTION}}",
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    url=REPO_URL,
    project_urls={
        "Source": REPO_URL,
        "Issue Tracker": f"{REPO_URL}/issues",
    },
    license="MIT",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.11",
    install_requires=read_requirements(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
