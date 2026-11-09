## Summary

<!-- What changes, and why. One or two sentences is usually enough. -->

Closes #

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Data, model, or pipeline change
- [ ] Documentation
- [ ] Build, CI, or tooling

## Checklist

- [ ] `ruff check --select E4,E7,E9,F .` passes (the same rules CI runs)
- [ ] `pytest` passes locally
- [ ] Tests added or updated for the behaviour that changed
- [ ] New dependencies added to `requirements.txt` (runtime) or `requirements-dev.txt` (dev)
- [ ] Config (`config/config.yaml`, `params.yaml`) updated instead of hard-coding new values
- [ ] Docs / docstrings updated where the public behaviour changed
- [ ] No data, secrets, credentials, or large artifacts committed (tracked with DVC instead)

## ML impact

<!-- Delete this section if the change does not touch data, features, or models. -->

- Data or feature changes:
- Metrics before / after:
- Retraining or `dvc repro` required: yes / no

## Notes for the reviewer

<!-- Anything worth calling out: trade-offs, follow-ups, areas you want scrutinised. -->
