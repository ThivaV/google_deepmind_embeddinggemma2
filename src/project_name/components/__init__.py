"""Pipeline components: the units that actually do the work.

Each component is a small class that takes exactly one config entity from
:mod:`{{PACKAGE_NAME}}.entity` and exposes a single public method, e.g.::

    from pathlib import Path

    from {{PACKAGE_NAME}}.entity import DataIngestionConfig


    class DataIngestion:
        def __init__(self, config: DataIngestionConfig) -> None:
            self.config = config

        def run(self) -> Path:
            ...
            return self.config.local_data_file

Keeping components free of YAML parsing and path building -- that all happens in
:class:`{{PACKAGE_NAME}}.config.configuration.ConfigurationManager` -- is what
makes them easy to unit test and to drive from a notebook. ``main.py`` wires the
manager to the components, one stage at a time.
"""
