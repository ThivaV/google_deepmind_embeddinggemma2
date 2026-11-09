"""Reads ``config/config.yaml`` and ``params.yaml`` and hands back typed entities.

This is the single place that knows about YAML keys and path layout. Everything
downstream -- components, pipeline stages, notebooks -- asks the manager for a
frozen dataclass and never touches the raw files::

    from {{PACKAGE_NAME}}.config import ConfigurationManager

    manager = ConfigurationManager()
    ingestion = manager.get_data_ingestion_config()
    trainer = manager.get_model_trainer_config()

Relative paths in the YAML are anchored at the repository root
(:data:`{{PACKAGE_NAME}}.constants.PROJECT_ROOT`), so a stage resolves the same
files whether it is launched by ``python main.py``, by ``dvc repro``, or from a
notebook in ``notebooks/``. Missing keys fall back to the documented defaults and
log a warning instead of raising, so a half-filled config still runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from {{PACKAGE_NAME}} import logger
from {{PACKAGE_NAME}}.constants import (
    ARTIFACTS_ROOT,
    CONFIG_FILE_PATH,
    PARAMS_FILE_PATH,
    PROJECT_ROOT,
)
from {{PACKAGE_NAME}}.entity import DataIngestionConfig, ModelTrainerConfig
from {{PACKAGE_NAME}}.utils import create_directories, read_yaml

__all__ = ["ConfigurationManager"]


class ConfigurationManager:
    """Loads the YAML configuration once and builds one entity per pipeline stage."""

    def __init__(
        self,
        config_filepath: str | Path = CONFIG_FILE_PATH,
        params_filepath: str | Path = PARAMS_FILE_PATH,
        project_root: str | Path = PROJECT_ROOT,
    ) -> None:
        self.project_root = Path(project_root)
        self.config = read_yaml(config_filepath)
        self.params = read_yaml(params_filepath)

        # Roots (config/config.yaml) ...
        self.artifacts_root = self._path(self.config.get("artifacts_root"), ARTIFACTS_ROOT)
        self.data_root = self._path(self.config.get("data_root"), self.project_root / ".data")
        self.models_root = self._path(self.config.get("models_root"), self.project_root / ".models")

        # ... and the knobs every stage shares (params.yaml).
        self.random_state = int(self.params.get("random_state", 42))
        self.target_column = str(self.params.get("target_column") or "target")
        self.n_jobs = int(self.params.get("n_jobs", -1))

        create_directories([self.artifacts_root])

    # -- helpers ------------------------------------------------------------

    def _path(self, value: Any, default: str | Path) -> Path:
        """Make a configured path absolute, anchoring relative values at the repo root."""
        path = Path(value) if value else Path(default)
        return path if path.is_absolute() else self.project_root / path

    @staticmethod
    def _section(source: Any, key: str) -> Mapping[str, Any]:
        """Return ``source[key]`` as a mapping, or an empty mapping when it is absent."""
        try:
            value = source[key]
        except (KeyError, TypeError):
            logger.warning("Missing '%s' section in configuration; using defaults", key)
            return {}
        if not isinstance(value, Mapping):
            logger.warning("Configuration key '%s' is not a mapping; using defaults", key)
            return {}
        return value

    # -- stage configurations ----------------------------------------------

    def get_data_ingestion_config(self) -> DataIngestionConfig:
        """Build the configuration for stage 1, ``data_ingestion``."""
        section = self._section(self.config, "data_ingestion")

        root_dir = self._path(section.get("root_dir"), self.artifacts_root / "data_ingestion")
        bronze = self.data_root / "bronze"
        create_directories([root_dir])

        config = DataIngestionConfig(
            root_dir=root_dir,
            source_url=str(section.get("source_url") or ""),
            local_data_file=self._path(section.get("local_data_file"), bronze / "data.zip"),
            unzip_dir=self._path(section.get("unzip_dir"), bronze / "extracted"),
        )
        logger.info("data_ingestion config resolved: local_data_file=%s", config.local_data_file)
        return config

    def get_model_trainer_config(self) -> ModelTrainerConfig:
        """Build the configuration for stage 4, ``model_trainer``."""
        section = self._section(self.config, "model_trainer")
        trainer_params = self._section(self.params, "model_trainer")

        root_dir = self._path(section.get("root_dir"), self.artifacts_root / "model_trainer")
        model_path = self._path(section.get("model_path"), self.models_root / "model.joblib")
        create_directories([root_dir, model_path.parent])

        model_type = str(trainer_params.get("model_type") or "random_forest")
        gold = self.data_root / "gold"
        transformation_root = self.artifacts_root / "data_transformation"

        config = ModelTrainerConfig(
            root_dir=root_dir,
            train_data_path=self._path(section.get("train_data_path"), gold / "train.csv"),
            test_data_path=self._path(section.get("test_data_path"), gold / "test.csv"),
            preprocessor_path=self._path(
                section.get("preprocessor_path"), transformation_root / "preprocessor.joblib"
            ),
            model_path=model_path,
            feature_importance_file=self._path(
                section.get("feature_importance_file"), root_dir / "feature_importance.csv"
            ),
            training_summary_file=self._path(
                section.get("training_summary_file"), root_dir / "training_summary.json"
            ),
            # config.yaml may pin the target; otherwise use the DVC-tracked default.
            target_column=str(section.get("target_column") or self.target_column),
            model_type=model_type,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
            model_params=dict(self._section(trainer_params, model_type)),
            cross_validation=dict(self._section(trainer_params, "cross_validation")),
        )
        logger.info(
            "model_trainer config resolved: model_type=%s target=%s model_path=%s",
            config.model_type,
            config.target_column,
            config.model_path,
        )
        return config
