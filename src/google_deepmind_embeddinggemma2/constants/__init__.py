"""Filesystem constants shared by the configuration layer.

The repository root is discovered by walking up from this file until a directory
containing ``params.yaml`` (or ``config/config.yaml``, or ``setup.py``) is found,
so the pipeline resolves the same paths whether it is started from the repository
root, from ``notebooks/``, or from an editable install. Set the ``PROJECT_ROOT``
environment variable to override the search -- useful inside containers where the
package is installed outside the repository.

This module deliberately depends on nothing but the standard library: everything
else in the package is free to import it.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "PROJECT_ROOT",
    "CONFIG_FILE_PATH",
    "PARAMS_FILE_PATH",
    "ARTIFACTS_ROOT",
]

_ROOT_MARKERS = ("params.yaml", "config/config.yaml", "setup.py")


def _discover_project_root(start: Path) -> Path:
    """Return the nearest ancestor of ``start`` that looks like the repository root."""
    for candidate in (start, *start.parents):
        if any((candidate / marker).exists() for marker in _ROOT_MARKERS):
            return candidate
    return Path.cwd()


_ENV_ROOT = os.environ.get("PROJECT_ROOT")

#: Repository root. constants/ -> google_deepmind_embeddinggemma2/ -> src/ -> root, in a checkout.
PROJECT_ROOT: Path = (
    Path(_ENV_ROOT).expanduser().resolve()
    if _ENV_ROOT
    else _discover_project_root(Path(__file__).resolve().parent)
)

#: Stable pipeline wiring: which stage reads and writes what.
CONFIG_FILE_PATH: Path = PROJECT_ROOT / "config" / "config.yaml"

#: Experiment knobs tracked by DVC: split ratios, hyperparameters, thresholds.
PARAMS_FILE_PATH: Path = PROJECT_ROOT / "params.yaml"

#: Default output directory; ``config.yaml`` may override it via ``artifacts_root``.
ARTIFACTS_ROOT: Path = PROJECT_ROOT / "artifacts"
