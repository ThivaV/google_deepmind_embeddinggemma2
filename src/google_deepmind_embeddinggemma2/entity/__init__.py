"""Typed configuration entities.

Every pipeline stage receives one of these frozen dataclasses instead of a raw
dictionary, so a typo in ``config/config.yaml`` fails in ``ConfigurationManager``
rather than three stages later. They are built by
:mod:`google_deepmind_embeddinggemma2.config.configuration` and consumed by the components in
:mod:`google_deepmind_embeddinggemma2.components`.

Field names mirror the YAML keys they come from. Add one entity per stage as the
pipeline grows -- ``DataValidationConfig``, ``DataTransformationConfig``,
``ModelEvaluationConfig`` -- following the same shape: paths as ``Path``,
hyperparameters as a read-only ``Mapping``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

__all__ = ["EMPTY_PARAMS", "DataIngestionConfig", "ModelTrainerConfig"]

#: Immutable stand-in for "no parameters", safe as a frozen-dataclass default.
EMPTY_PARAMS: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class DataIngestionConfig:
    """Where the source data comes from and where it lands on disk.

    Built from the ``data_ingestion`` section of ``config/config.yaml``. An empty
    ``source_url`` means "the file is provided by hand", and the stage only
    checks that ``local_data_file`` is present.
    """

    root_dir: Path
    source_url: str
    local_data_file: Path
    unzip_dir: Path


@dataclass(frozen=True)
class ModelTrainerConfig:
    """Inputs, outputs and hyperparameters for the training stage.

    Paths come from the ``model_trainer`` section of ``config/config.yaml``;
    ``target_column``, ``random_state`` and ``n_jobs`` come from the shared
    top-level keys in ``params.yaml``, and ``model_params`` is the parameter
    block named by ``model_trainer.model_type``.
    """

    root_dir: Path
    train_data_path: Path
    test_data_path: Path
    preprocessor_path: Path
    model_path: Path
    feature_importance_file: Path
    training_summary_file: Path
    target_column: str
    model_type: str = "random_forest"
    random_state: int = 42
    n_jobs: int = -1
    model_params: Mapping[str, Any] = field(default=EMPTY_PARAMS)
    cross_validation: Mapping[str, Any] = field(default=EMPTY_PARAMS)
