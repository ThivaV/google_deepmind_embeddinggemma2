"""Pipeline stages: thin orchestration around the components.

A component knows how to do one job; a stage knows which component to build, what
config to hand it, and what to log around it. Stages are what ``main.py`` and
``dvc.yaml`` call, which keeps both of them free of wiring detail::

    from {{PACKAGE_NAME}} import logger
    from {{PACKAGE_NAME}}.config import ConfigurationManager


    class DataIngestionPipeline:
        def run(self) -> None:
            config = ConfigurationManager().get_data_ingestion_config()
            logger.info("Ingesting data into %s", config.root_dir)
            ...

Keep stages free of real work -- if a stage grows logic worth testing on its own,
that logic belongs in a component under :mod:`{{PACKAGE_NAME}}.components`.

This package ships empty on purpose. ``main.py`` currently drives its two shipped
stages directly through the ``STAGES`` mapping; move them here once you have more
than a couple, or once the same stage needs calling from both ``main.py`` and a
notebook.
"""
