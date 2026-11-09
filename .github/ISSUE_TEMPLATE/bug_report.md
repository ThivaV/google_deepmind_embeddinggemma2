---
name: Bug report
about: "Report something in Google Deepmind Embeddinggemma2 that does not behave as expected"
title: "[bug] "
labels: ["bug", "triage"]
assignees: ""
---

## What happened

<!-- A clear description of the incorrect behaviour, including the full error or traceback. -->

```text
paste the traceback or log output here
```

## What you expected

<!-- What should have happened instead. -->

## How to reproduce

1.
2.
3.

Minimal command or snippet:

```bash
python main.py
```

## Environment

- `google_deepmind_embeddinggemma2` version / commit:
- Python version: <!-- the project targets 3.11 -->
- Operating system:
- Installed with:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  pip install -r requirements-dev.txt
  ```
- Relevant dependency versions (`pip freeze | grep -i <package>`):

## Data, config, and models

<!-- Delete anything that does not apply. Never paste credentials or private data. -->

- Config or params changed from the defaults (`config/config.yaml`, `params.yaml`):
- Dataset or DVC stage involved (`dvc repro <stage>`):
- Model or artifact involved:
- Reproducible with the sample data? yes / no

## Anything else

<!-- Screenshots, notebook cell output, a first guess at the cause, or a workaround you found. -->
