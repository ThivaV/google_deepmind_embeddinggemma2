# {{PROJECT_TITLE}} guide

How the project is laid out and how to work on it: setup, configuration, running the
pipeline and the app, DVC, and testing. What the project itself is about lives in
[README.md](README.md).

---

## Project structure

```text
{{PROJECT_NAME}}/
├── config/
│   └── config.yaml              # paths, artefact locations, stage wiring
├── .data/                       # medallion data layers (DVC-tracked)
│   ├── bronze/                  # raw data, exactly as ingested
│   ├── silver/                  # validated and cleaned
│   └── gold/                    # model-ready train/test splits
├── docs/
│   ├── doc/                     # written notes and design docs
│   └── img/                     # figures used by the docs and the README
├── .models/                     # trained model artefacts (DVC-tracked)
├── notebooks/
│   └── {{PACKAGE_NAME}}.ipynb   # exploration scratchpad
├── scripts/                     # one-off and operational scripts
├── src/
│   └── {{PACKAGE_NAME}}/
│       ├── components/          # one module per pipeline step
│       ├── config/              # configuration manager
│       ├── constants/           # config/params file locations
│       ├── entity/              # typed config objects
│       ├── pipeline/            # stages wired into runnable pipelines
│       ├── utils/               # shared helpers
│       └── __init__.py          # package logger and version
├── tests/                       # pytest suite
├── templates/                   # HTML templates served by app.py
├── app.py                       # web entrypoint (serves the trained model)
├── main.py                      # pipeline entrypoint (runs the stages in order)
├── params.yaml                  # tunable parameters and hyperparameters
├── dvc.yaml                     # pipeline stage definitions
├── requirements.txt             # runtime dependencies
├── requirements-dev.txt         # development and notebook dependencies
├── setup.py                     # packaging metadata for src/{{PACKAGE_NAME}}
├── README.md                    # what this project is, its data and its results
├── TEMPLATE_GUIDE.md            # this guide: layout, setup, pipeline, DVC, testing
├── .github/workflows/ci.yml     # lint and test on every push and pull request
└── .env.example                 # template for the local .env file
```

Two directories are created on demand and are git-ignored: `artifacts/`, which holds
each stage's outputs, and `logs/`, where the package logger writes
`logs/running_logs.log` alongside its stdout output.

`.data/` and `.models/` are dot-prefixed on purpose: their contents are DVC's business
rather than git's, and hiding them keeps the project root about the code. The trade-off
is that hidden directories are filtered out by default in some places — Jupyter's file
browser and a plain `ls` among them — so reach for `ls -a`, and set
`c.ContentsManager.allow_hidden = True` in your Jupyter config if you want to browse the
data from a notebook. Their locations are not hard-coded: `data_root` and `models_root`
in `config/config.yaml` drive every path, so renaming them back is a two-line change.

Data moves through `.data/` in three medallion layers, each written by one pipeline
stage: `data_ingestion` lands the source in `bronze/` exactly as it arrived,
`data_validation` writes the schema-checked, cleaned dataset to `silver/`, and
`data_transformation` writes the model-ready train/test splits to `gold/`. Each layer
is built only from the one before it, so `bronze/` stays a faithful copy of the source
and everything in `silver/` and `gold/` can be rebuilt from it with `dvc repro`.

---

## Setup

Python 3.11 is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

`requirements.txt` holds the runtime dependencies — everything the pipeline and the
app need in production. `requirements-dev.txt` adds the development extras: the
test runner, the linters, and the notebook stack. Install both while developing;
install only the first one when deploying. Neither file pins versions, so pip
installs the newest release of each package that supports Python 3.11.

The importable package lives under `src/`, and both entrypoints add that directory to
`sys.path` themselves, so a fresh clone runs without an install step. Install the
package in editable mode when you want `import {{PACKAGE_NAME}}` to resolve from
anywhere — a notebook in another directory, say:

```bash
pip install -e .
```

Finally, copy the environment template and fill in whatever your setup needs:

```bash
cp .env.example .env
```

`.env` is git-ignored. Load it with `python-dotenv` (`load_dotenv()`) before reading
anything out of `os.environ`.

---

## Configuration

Two YAML files drive the project, and neither of them is code:

| File | Holds |
| --- | --- |
| `config/config.yaml` | the stable wiring — paths, directory layout, artefact names, data sources |
| `params.yaml` | the experiment knobs — split ratios, hyperparameters, thresholds |

Stages read them through the configuration manager instead of hard-coding values:

```python
from {{PACKAGE_NAME}}.config.configuration import ConfigurationManager

manager = ConfigurationManager()
config = manager.get_model_trainer_config()
```

The split matters for reproducibility: DVC tracks `params.yaml` value by value, so
changing one parameter invalidates exactly the stages that depend on it, while a path
change in `config/config.yaml` re-runs the stages whose inputs actually moved.

---

## Usage

Run every wired-up stage, in order:

```bash
python main.py
```

On a fresh project this ingests the sample dataset and then stops at `model_trainer`,
which needs a transformed training set that `data_transformation` would produce — and
that stage is deliberately left for you to write. The error names the stage to
implement first, which is the intended starting point rather than a failure.

Run a single stage by name while you iterate on it:

```bash
python main.py data_ingestion
```

`python main.py --list` prints the stages that are currently wired up, and `--help` shows
them too. Stages live in the `STAGES` mapping near the bottom of `main.py`; add one by
writing a component under `src/{{PACKAGE_NAME}}/components/` and registering it there.

Two stages ship with the template — `data_ingestion` and `model_trainer` — while
`dvc.yaml` declares the full five-stage graph, so `data_validation`,
`data_transformation` and `model_evaluation` are yours to fill in.

Serve the trained model with the Flask app:

```bash
python app.py
```

It listens on <http://127.0.0.1:8080> (override with the `HOST` and `PORT` environment
variables) and exposes three routes:

```bash
curl -s localhost:8080/health
curl -s localhost:8080/predict -H 'Content-Type: application/json' -d '{"features": [1, 2, 3]}'
```

`/` renders `templates/index.html`, `/health` reports the version along with the resolved
model path and whether that artefact is available, and `/predict` returns a prediction —
or a 503 while the model artefact has not been built yet. `/predict` also accepts a named
payload such as `{"features": {"alcohol": 9.4}}`, which is reordered to match the
estimator's own feature order, and the urlencoded form that `templates/index.html` posts.

---

## Data and pipelines with DVC

[DVC](https://dvc.org/) versions the data and models that are too large for git, and
turns `dvc.yaml` into a reproducible dependency graph.

Initialise it once, in a clone that has never used DVC:

```bash
dvc init
dvc remote add -d storage <your-remote-url>
```

Day to day:

```bash
dvc repro                 # re-run only the stages whose inputs or params changed
dvc repro model_trainer   # re-run one stage, plus whatever it depends on
dvc dag                   # print the stage graph
dvc metrics show          # print the metrics the stages wrote
dvc params diff           # see which parameters changed since the last run
dvc push                  # upload data and models to the remote
dvc pull                  # fetch them back on another machine
```

`dvc repro` is the reproducible counterpart of `python main.py`: it hashes each
stage's dependencies and parameters, skips everything already up to date, and re-runs
only what is stale. Each stage shells out to `python main.py <stage>`, so a stage
reproduces only once it is registered in `STAGES` — `dvc repro` walks the whole
five-stage graph and will stop at the first stage you have not implemented yet.

Track the data and model directories with DVC rather than git:

```bash
dvc add .data/bronze/raw.csv
git add .data/bronze/raw.csv.dvc .data/bronze/.gitignore
```

---

## Testing

```bash
pytest
```

Useful variations:

```bash
pytest -v                                  # show individual test names
pytest tests/test_smoke.py                 # a single file
pytest -k ingestion                        # tests matching a keyword
pytest --cov=src/{{PACKAGE_NAME}} --cov-report=term-missing
```

The suite ships with smoke tests that pass on a fresh checkout: they assert that the
package imports and that the directory layout is intact. Add real tests under `tests/`
as the project grows — CI (`.github/workflows/ci.yml`) runs `ruff` and `pytest` on
every push and pull request against `main`.
