"""Smoke tests for Google Deepmind Embeddinggemma2.

These pass on a freshly generated repository, before a single line of project
code has been written, and they keep passing whichever flavour was bootstrapped.
They check the handful of things that are always true: the package imports, it
advertises a version, and the directory layout is intact.

Run them with::

    pytest -q
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# The importable package name. Written as a string so this file stays valid
# Python both before and after the template placeholders are substituted.
PACKAGE_NAME = "google_deepmind_embeddinggemma2"

# The directory name the template ships with, before bootstrap.py renames it.
SENTINEL_PACKAGE = "project_name"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

# Make `pytest` work straight after `git clone`, without `pip install -e .` first.
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Present in every flavour of the template. .data/ is checked layer by layer:
# the bronze, silver and gold medallion layers the pipeline stages write to.
REQUIRED_DIRS = (
    ".data/bronze",
    ".data/silver",
    ".data/gold",
    ".models",
    "notebooks",
    "src",
    "tests",
)

# Trimmed away by some flavours -- asserted only when they are actually there.
OPTIONAL_DIRS = ("config", "docs", "scripts", "templates")


@pytest.fixture(scope="module")
def package():
    """The project package, imported once for the whole module."""
    return importlib.import_module(PACKAGE_NAME)


def test_package_is_importable(package):
    """Importing google_deepmind_embeddinggemma2 works and resolves to the expected module."""
    assert package.__name__ == PACKAGE_NAME


def test_package_exposes_a_version(package):
    """The package advertises a usable ``__version__`` string."""
    version = getattr(package, "__version__", None)
    assert isinstance(version, str), f"{PACKAGE_NAME}.__version__ must be a string"
    assert version.strip(), f"{PACKAGE_NAME}.__version__ must not be empty"
    assert version == version.strip(), "__version__ must not carry surrounding whitespace"


def test_package_lives_under_src():
    """The src/ layout is in place, so editable installs behave predictably."""
    assert (SRC_DIR / PACKAGE_NAME / "__init__.py").is_file()


@pytest.mark.parametrize("name", REQUIRED_DIRS)
def test_required_directory_exists(name):
    """Core project directories survive in every flavour."""
    assert (PROJECT_ROOT / name).is_dir(), f"missing required directory: {name}/"


@pytest.mark.parametrize("name", OPTIONAL_DIRS)
def test_optional_directory_is_well_formed(name):
    """Flavour-specific directories, when present, are real directories."""
    path = PROJECT_ROOT / name
    if not path.exists():
        pytest.skip(f"{name}/ is not part of this flavour")
    assert path.is_dir(), f"{name} exists but is not a directory"


def test_sentinel_package_was_renamed():
    """Bootstrapping leaves no template sentinel package behind."""
    if PACKAGE_NAME == SENTINEL_PACKAGE:
        pytest.skip("the project is genuinely named after the sentinel")
    assert not (SRC_DIR / SENTINEL_PACKAGE).exists(), (
        f"src/{SENTINEL_PACKAGE}/ still exists -- did bootstrap.py run?"
    )
