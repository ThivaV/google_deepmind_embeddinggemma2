"""{{PROJECT_TITLE}} -- {{PROJECT_DESCRIPTION}}

Importing this package configures the project-wide logger exactly once, so every
module can simply do::

    from {{PACKAGE_NAME}} import logger

    logger.info("training started")

Logs go to stdout and, when the directory is writable, to
``logs/running_logs.log`` (relative to the working directory, or to ``$LOG_DIR``
when that is set). On a read-only filesystem logging degrades to stdout instead
of failing at import time.

The rest of the package is laid out as follows:

* :mod:`{{PACKAGE_NAME}}.constants`   -- where ``config.yaml`` and ``params.yaml`` live
* :mod:`{{PACKAGE_NAME}}.entity`      -- frozen dataclasses describing each stage's config
* :mod:`{{PACKAGE_NAME}}.config`      -- ``ConfigurationManager``: YAML in, entities out
* :mod:`{{PACKAGE_NAME}}.components`  -- the classes that do the actual work
* :mod:`{{PACKAGE_NAME}}.utils`       -- small shared helpers
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

__version__ = "0.1.0"
__author__ = "{{AUTHOR_NAME}}"

PACKAGE_NAME = "{{PACKAGE_NAME}}"

LOG_DIR = Path(os.environ.get("LOG_DIR", "logs"))
LOG_FILE = LOG_DIR / "running_logs.log"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s (%(module)s:%(lineno)d): %(message)s"


def _resolve_level(name: str) -> int:
    """Translate ``$LOG_LEVEL`` into a logging level, falling back to INFO.

    ``logging.getLevelName`` answers with a string ("Level VERBOSE") for names it
    does not know, so a typo in the environment must not break the import.
    """
    level = logging.getLevelName(name)
    return level if isinstance(level, int) else logging.INFO


def _configure_package_logger() -> logging.Logger:
    """Attach a stdout handler -- and a file handler when possible -- exactly once."""
    package_logger = logging.getLogger(PACKAGE_NAME)
    if package_logger.handlers:  # already configured (e.g. re-import under the Flask reloader)
        return package_logger

    package_logger.setLevel(_resolve_level(LOG_LEVEL))
    package_logger.propagate = False
    formatter = logging.Formatter(LOG_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    package_logger.addHandler(stream_handler)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except OSError:
        package_logger.debug("File logging disabled: %s is not writable", LOG_DIR)
    else:
        file_handler.setFormatter(formatter)
        package_logger.addHandler(file_handler)

    return package_logger


logger = _configure_package_logger()


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the package logger, e.g. ``get_logger("data_ingestion")``."""
    if not name:
        return logger
    return logger.getChild(name)


__all__ = [
    "__version__",
    "__author__",
    "PACKAGE_NAME",
    "LOG_FILE",
    "logger",
    "get_logger",
]
