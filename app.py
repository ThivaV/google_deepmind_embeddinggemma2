"""Minimal Flask app for {{PROJECT_TITLE}}.

Serves ``templates/index.html`` and a small JSON API::

    python app.py                       # http://127.0.0.1:8080
    curl -s localhost:8080/health
    curl -s localhost:8080/predict -H 'Content-Type: application/json' \
         -d '{"features": [7.4, 0.7, 0.0]}'
    curl -s localhost:8080/predict -H 'Content-Type: application/json' \
         -d '{"features": {"alcohol": 9.4, "ph": 3.51}}'

The model is loaded lazily from the path resolved by
:class:`{{PACKAGE_NAME}}.config.configuration.ConfigurationManager` -- the same
``.models/model.joblib`` that ``python main.py`` writes. Until that artifact
exists, ``/predict`` answers 503 rather than pretending to have an answer.

The HTML form in ``templates/index.html`` posts urlencoded fields to the same
endpoint, so both the browser and the API path are covered. Rename its inputs to
your real feature names once the model is trained: named payloads are reordered
to match the estimator's ``feature_names_in_`` automatically.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

from flask import Flask, jsonify, render_template, request
from jinja2 import TemplateNotFound

# Make the package importable straight from a checkout, without `pip install -e .`.
SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from {{PACKAGE_NAME}} import __version__, logger  # noqa: E402
from {{PACKAGE_NAME}}.config import ConfigurationManager  # noqa: E402

app = Flask(__name__)

_model: Any | None = None
_model_path: Path | None = None


def resolve_model_path() -> Path:
    """Resolve (and cache) the trained model's location from the project config."""
    global _model_path

    if _model_path is None:
        try:
            _model_path = ConfigurationManager().get_model_trainer_config().model_path
        except Exception:  # a missing or invalid config must not stop the app from booting
            logger.exception("Could not read the project configuration; falling back to .models/")
            _model_path = Path(".models") / "model.joblib"
    return _model_path


def get_model() -> Any | None:
    """Load and cache the trained model, returning ``None`` when it is not built yet."""
    global _model

    if _model is not None:
        return _model

    path = resolve_model_path()
    if not path.exists():
        logger.warning("Model artifact not found: %s -- run `python main.py` first", path)
        return None

    import joblib  # imported lazily so the app still boots without a model

    _model = joblib.load(path)
    logger.info("Loaded model from %s", path)
    return _model


def _feature_names(model: Any) -> list[str]:
    """The feature order the estimator was fitted with, when scikit-learn recorded it."""
    names = getattr(model, "feature_names_in_", None)
    return [str(name) for name in names] if names is not None else []


def _row_from_mapping(mapping: Mapping[str, Any], names: list[str]) -> list[float]:
    """Order a ``{feature: value}`` payload, falling back to insertion order."""
    if names:
        missing = [name for name in names if name not in mapping]
        if missing:
            raise ValueError(f"Missing features: {', '.join(missing)}")
        return [float(mapping[name]) for name in names]
    return [float(value) for value in mapping.values()]


def _to_rows(features: Any, names: list[str]) -> list[list[float]]:
    """Normalise the accepted payload shapes into a list of numeric rows."""
    if isinstance(features, Mapping):
        return [_row_from_mapping(features, names)]

    if isinstance(features, list) and features:
        if all(isinstance(item, Mapping) for item in features):
            return [_row_from_mapping(item, names) for item in features]
        if all(isinstance(item, list) for item in features):
            return [[float(value) for value in item] for item in features]
        return [[float(value) for value in features]]

    raise ValueError('Send {"features": [1, 2, 3]} or {"features": {"name": value}}')


def _as_model_input(rows: list[list[float]], names: list[str]) -> Any:
    """Label the rows when the estimator knows its feature names, so sklearn stays quiet."""
    if not names or len(rows[0]) != len(names):
        return rows

    import pandas as pd

    return pd.DataFrame(rows, columns=names)


@app.get("/")
def index() -> str:
    """Render the landing page."""
    try:
        return render_template("index.html", title="{{PROJECT_TITLE}}", version=__version__)
    except TemplateNotFound:
        return "<h1>{{PROJECT_TITLE}}</h1><p>Add templates/index.html to customise this page.</p>"


@app.get("/health")
def health() -> Any:
    """Liveness probe that also reports whether a model artifact is available."""
    path = resolve_model_path()
    return jsonify(
        status="ok",
        version=__version__,
        model_path=str(path),
        model_available=_model is not None or path.exists(),
    )


@app.post("/predict")
def predict() -> Any:
    """Return a prediction for the posted features (JSON body or HTML form)."""
    payload: Any = request.get_json(silent=True)
    if payload is None and request.form:
        payload = dict(request.form)

    if isinstance(payload, Mapping) and "features" in payload:
        features = payload["features"]
    elif isinstance(payload, (Mapping, list)) and payload:
        features = payload  # a bare list of values, or a flat {feature: value} mapping
    else:
        return jsonify(error='Send JSON like {"features": [1, 2, 3]}'), 400

    model = get_model()
    if model is None:
        return jsonify(error=f"No model at {resolve_model_path()}. Run `python main.py` first."), 503

    try:
        names = _feature_names(model)
        model_input = _as_model_input(_to_rows(features, names), names)
        raw = model.predict(model_input)
    except Exception as exc:  # wrong shape, non-numeric values, unknown feature names, ...
        logger.exception("Prediction failed")
        return jsonify(error=f"Prediction failed: {exc}"), 400

    prediction = raw.tolist() if hasattr(raw, "tolist") else list(raw)
    response: dict[str, Any] = {
        "prediction": prediction,
        "model": type(model).__name__,
        "version": __version__,
    }

    if hasattr(model, "predict_proba"):
        try:
            probabilities = model.predict_proba(model_input)
            response["probabilities"] = probabilities.tolist()
            response["classes"] = [str(label) for label in getattr(model, "classes_", [])]
        except Exception:  # not every estimator supports it for every input
            logger.debug("predict_proba unavailable for this input", exc_info=True)

    return jsonify(response)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
