"""Configuration layer: YAML in, typed entities out.

The only thing you normally need from here is the manager, importable either way::

    from {{PACKAGE_NAME}}.config import ConfigurationManager
    from {{PACKAGE_NAME}}.config.configuration import ConfigurationManager
"""

from {{PACKAGE_NAME}}.config.configuration import ConfigurationManager

__all__ = ["ConfigurationManager"]
