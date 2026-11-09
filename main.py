"""Pipeline entrypoint for Google Deepmind Embeddinggemma2.

Run the whole pipeline, or a single stage by name::

    python main.py                     # every registered stage, in order
    python main.py data_ingestion      # one stage (the form dvc.yaml uses)
    python main.py --list              # show the registered stages

Every stage resolves its configuration through
:class:`google_deepmind_embeddinggemma2.config.configuration.ConfigurationManager`, which reads
``config/config.yaml`` (paths and wiring) and ``params.yaml`` (experiment knobs).
Nothing in here parses YAML itself.

Two stages ship with the template: ``data_ingestion`` and ``model_trainer``. The
other stages declared in ``dvc.yaml`` -- data_validation, data_transformation,
model_evaluation -- follow the same four steps: add an entity in
``src/google_deepmind_embeddinggemma2/entity/``, a getter on ``ConfigurationManager``, a
component in ``src/google_deepmind_embeddinggemma2/components/``, then a function here plus one
line in :data:`STAGES`.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

# Make the package importable straight from a checkout, without `pip install -e .`.
SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from google_deepmind_embeddinggemma2 import __version__, logger  # noqa: E402
from google_deepmind_embeddinggemma2.config import ConfigurationManager  # noqa: E402
from google_deepmind_embeddinggemma2.entity import DataIngestionConfig, ModelTrainerConfig  # noqa: E402
from google_deepmind_embeddinggemma2.utils import save_json  # noqa: E402

Stage = Callable[[ConfigurationManager], None]

#: ``params.yaml -> model_trainer.model_type`` selects one of these estimators.
ESTIMATORS: dict[str, tuple[str, str]] = {
    "random_forest": ("sklearn.ensemble", "RandomForestClassifier"),
    "gradient_boosting": ("sklearn.ensemble", "GradientBoostingClassifier"),
    "logistic_regression": ("sklearn.linear_model", "LogisticRegression"),
}


# ---------------------------------------------------------------------------
# Stage 1 -- data ingestion
# ---------------------------------------------------------------------------


def _download(url: str, destination: Path) -> None:
    """Fetch ``url`` into ``destination``, refusing anything but http(s)."""
    scheme = urllib.parse.urlparse(url).scheme
    if scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported source_url scheme '{scheme}': {url}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s -> %s", url, destination)
    urllib.request.urlretrieve(url, destination)  # noqa: S310 - scheme checked above
    logger.info("Downloaded %.1f KiB", destination.stat().st_size / 1024)


def data_ingestion_stage(manager: ConfigurationManager) -> None:
    """Fetch the source dataset and unpack it when it is an archive."""
    config: DataIngestionConfig = manager.get_data_ingestion_config()

    if config.local_data_file.exists():
        logger.info("Source already present, skipping download: %s", config.local_data_file)
    elif config.source_url:
        _download(config.source_url, config.local_data_file)
    else:
        raise FileNotFoundError(
            f"No 'source_url' in config/config.yaml -> data_ingestion, and {config.local_data_file} "
            "does not exist. Set a URL, or drop the dataset there by hand and rerun."
        )

    if not zipfile.is_zipfile(config.local_data_file):
        logger.info("Source is not an archive; nothing to extract")
        return

    config.unzip_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(config.local_data_file) as archive:
        archive.extractall(config.unzip_dir)
        members = [name for name in archive.namelist() if not name.endswith("/")]
    logger.info("Extracted %d file(s) into %s: %s", len(members), config.unzip_dir, members)


# ---------------------------------------------------------------------------
# Stage 4 -- model training
# ---------------------------------------------------------------------------


def _build_estimator(config: ModelTrainerConfig) -> Any:
    """Instantiate the estimator named by ``params.yaml -> model_trainer.model_type``."""
    try:
        module_name, class_name = ESTIMATORS[config.model_type]
    except KeyError:
        raise ValueError(
            f"Unknown model_type '{config.model_type}'. Known: {', '.join(sorted(ESTIMATORS))}. "
            "Add yours to ESTIMATORS in main.py."
        ) from None

    estimator_class = getattr(importlib.import_module(module_name), class_name)
    kwargs = dict(config.model_params)

    # Only pass the shared knobs this estimator actually accepts.
    accepted = inspect.signature(estimator_class).parameters
    if "random_state" in accepted:
        kwargs.setdefault("random_state", config.random_state)
    if "n_jobs" in accepted:
        kwargs.setdefault("n_jobs", config.n_jobs)

    logger.info("Building %s with %s", class_name, kwargs)
    return estimator_class(**kwargs)


def _save_feature_importance(estimator: Any, features: list[str], destination: Path) -> None:
    """Write a ``feature,importance`` CSV -- the plot dvc.yaml renders -- when available."""
    import numpy as np
    import pandas as pd

    if hasattr(estimator, "feature_importances_"):
        importance = np.asarray(estimator.feature_importances_, dtype=float)
    elif hasattr(estimator, "coef_"):
        coefficients = np.abs(np.asarray(estimator.coef_, dtype=float))
        importance = coefficients.reshape(-1, len(features)).mean(axis=0)
    else:
        logger.info("%s exposes no feature importances; skipping", type(estimator).__name__)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"feature": features, "importance": importance})
    frame.sort_values("importance", ascending=False).to_csv(destination, index=False)
    logger.info("Saved feature importances to %s", destination)


def model_trainer_stage(manager: ConfigurationManager) -> None:
    """Fit the configured estimator on the processed training split and persist it."""
    import joblib
    import pandas as pd

    config: ModelTrainerConfig = manager.get_model_trainer_config()

    if not config.train_data_path.exists():
        raise FileNotFoundError(
            f"Training data not found: {config.train_data_path}. Run the data_transformation "
            "stage first, or point model_trainer.train_data_path at an existing split."
        )

    frame = pd.read_csv(config.train_data_path)
    if config.target_column not in frame.columns:
        raise KeyError(
            f"Target column '{config.target_column}' is not in {config.train_data_path}. "
            f"Columns: {list(frame.columns)}"
        )

    features = frame.drop(columns=[config.target_column]).select_dtypes(include="number")
    if features.empty:
        raise ValueError(
            f"No numeric feature columns in {config.train_data_path}; encode them in the "
            "data_transformation stage first."
        )

    usable = features.notna().all(axis=1) & frame[config.target_column].notna()
    dropped = int((~usable).sum())
    if dropped:
        logger.warning("Dropping %d row(s) with missing values before fitting", dropped)

    x_train = features.loc[usable]
    y_train = frame.loc[usable, config.target_column]

    estimator = _build_estimator(config)
    estimator.fit(x_train, y_train)
    logger.info("Fitted %s on %s rows", type(estimator).__name__, f"{len(x_train):,}")

    summary: dict[str, Any] = {
        "model_type": config.model_type,
        "estimator": type(estimator).__name__,
        "params": {key: str(value) for key, value in config.model_params.items()},
        "target_column": config.target_column,
        "features": list(x_train.columns),
        "n_rows": int(len(x_train)),
        "n_features": int(x_train.shape[1]),
        "rows_dropped": dropped,
        "train_score": float(estimator.score(x_train, y_train)),
    }

    if config.cross_validation.get("enabled"):
        from sklearn.model_selection import cross_val_score

        folds = int(config.cross_validation.get("folds", 5))
        scoring = str(config.cross_validation.get("scoring", "f1_weighted"))
        scores = cross_val_score(
            estimator, x_train, y_train, cv=folds, scoring=scoring, n_jobs=config.n_jobs
        )
        summary["cross_validation"] = {
            "folds": folds,
            "scoring": scoring,
            "scores": [float(score) for score in scores],
            "mean": float(scores.mean()),
            "std": float(scores.std()),
        }
        logger.info("Cross-validated %s: %.4f (+/- %.4f)", scoring, scores.mean(), scores.std())

    config.model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(estimator, config.model_path)
    logger.info("Saved model to %s", config.model_path)

    _save_feature_importance(estimator, list(x_train.columns), config.feature_importance_file)
    save_json(config.training_summary_file, summary)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

#: Stage name -> callable. The names must match the stage names in dvc.yaml.
STAGES: dict[str, Stage] = {
    "data_ingestion": data_ingestion_stage,
    "model_trainer": model_trainer_stage,
}


def run_pipeline(only: str | None = None) -> None:
    """Run every registered stage in order, or just the one named by ``only``."""
    if only is not None and only not in STAGES:
        raise SystemExit(f"Unknown stage '{only}'. Available: {', '.join(STAGES)}")

    manager = ConfigurationManager()

    for name, stage in STAGES.items():
        if only is not None and name != only:
            continue
        logger.info(">>>>>> stage %s started <<<<<<", name)
        stage(manager)
        logger.info(">>>>>> stage %s completed <<<<<<\n", name)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        prog="main.py", description="Run the Google Deepmind Embeddinggemma2 pipeline."
    )
    parser.add_argument(
        "stage",
        nargs="?",
        choices=list(STAGES),
        help="run a single stage instead of the whole pipeline",
    )
    parser.add_argument("--list", action="store_true", help="list the registered stages and exit")
    return parser


def main() -> int:
    """Parse the arguments, run the pipeline, and turn failures into an exit code."""
    args = build_parser().parse_args()

    if args.list:
        for name in STAGES:
            print(name)
        return 0

    logger.info("Google Deepmind Embeddinggemma2 v%s -- starting pipeline", __version__)
    try:
        run_pipeline(args.stage)
    except Exception:
        logger.exception("Pipeline failed")
        return 1

    logger.info("Pipeline finished successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
