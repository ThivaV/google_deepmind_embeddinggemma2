"""Small, dependency-light helpers shared across the project.

Usage::

    from google_deepmind_embeddinggemma2.utils import read_yaml, create_directories, save_json

``read_yaml`` returns a ``ConfigBox`` when `python-box` is installed (so you can
write ``config.data_ingestion.root_dir``) and a plain ``dict`` otherwise. Both
support ordinary ``config["data_ingestion"]`` and ``config.get(...)`` access,
which is what the rest of the project uses -- keeping the helpers usable either
way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import yaml

try:  # optional: nicer dotted access when python-box is available
    from box import ConfigBox
except ImportError:  # pragma: no cover - exercised only without python-box
    ConfigBox = None

from google_deepmind_embeddinggemma2 import logger

__all__ = ["read_yaml", "create_directories", "save_json"]


def read_yaml(path: str | Path) -> Any:
    """Load a YAML file and return its contents.

    Args:
        path: Location of the YAML file.

    Returns:
        A ``ConfigBox`` (dotted access) when python-box is installed, otherwise
        the plain object PyYAML produced -- usually a ``dict``.

    Raises:
        FileNotFoundError: The file does not exist.
        ValueError: The file exists but is empty.
        yaml.YAMLError: The file is not valid YAML.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle)

    if content is None:
        raise ValueError(f"YAML file is empty: {path}")

    logger.info("Loaded YAML file: %s", path)
    if ConfigBox is not None and isinstance(content, dict):
        return ConfigBox(content)
    return content


def create_directories(paths: Iterable[str | Path], verbose: bool = True) -> list[Path]:
    """Create every directory in ``paths`` (including parents), ignoring existing ones.

    Args:
        paths: Directories to create.
        verbose: Log one line per directory.

    Returns:
        The directories, as ``Path`` objects, in the order they were given.
    """
    created: list[Path] = []
    for raw_path in paths:
        directory = Path(raw_path)
        directory.mkdir(parents=True, exist_ok=True)
        created.append(directory)
        if verbose:
            logger.info("Directory ready: %s", directory)
    return created


def save_json(path: str | Path, data: Any, indent: int = 4) -> Path:
    """Write ``data`` to ``path`` as UTF-8 JSON, creating parent directories as needed.

    Args:
        path: Destination file, e.g. ``artifacts/model_evaluation/metrics.json``.
        data: Any JSON-serialisable object. ``Path`` and numpy scalars are
            stringified by ``default=str`` rather than raising.
        indent: Indentation passed to ``json.dump``.

    Returns:
        The path that was written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=indent, ensure_ascii=False, default=str)
        handle.write("\n")

    logger.info("Saved JSON file: %s", path)
    return path
