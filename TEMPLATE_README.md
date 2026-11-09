# ml-project-template

A GitHub template repository for Python / ML projects: a `src/` layout, config-driven
pipeline stages, notebooks, DVC wiring, a Flask serving stub, and a pytest suite — with
every project-specific value filled in automatically the first time you push.

Packaging is plain `pip` with `requirements.txt`, and the target Python is 3.11.

> **This file documents the template itself.** `bootstrap.py` deletes it from generated
> repositories, along with itself and the bootstrap workflow, so the project you end up
> with keeps only its own `README.md` and `TEMPLATE_GUIDE.md`.

---

## Generate a repository from the template

Any of these three routes produces the same result.

**1. The "Use this template" button.** Open
[github.com/ThivaV/ml-project-template](https://github.com/ThivaV/ml-project-template),
click **Use this template → Create a new repository**, and give the new repository a name.

**2. The new-repository page.** Go to [github.com/new](https://github.com/new) and pick
`ThivaV/ml-project-template` from the **Repository template** dropdown at the top.

**3. The `gh` CLI.**

```bash
gh repo create my-new-repo --template ThivaV/ml-project-template --private --clone
```

Swap `--private` for `--public` if you want the repository visible, and drop `--clone` if
you would rather not check it out straight away.

**Name the repository well** — the name is the only input the bootstrapper needs.
`churn-predictor` becomes the package `churn_predictor` and the title `Churn Predictor`.
Add a repository description while you are there; it is picked up as the project
description.

---

## What happens next

The `Bootstrap template` workflow (`.github/workflows/bootstrap.yml`) runs on the first
push to `main` or `master` in the generated repository and does the whole setup for you:

1. Prunes the files the chosen flavour does not need, and drops any directory the pruning
   emptied out (a directory holding a `.gitkeep` is deliberately empty and stays).
2. Fills in every placeholder token, deriving the values from the repository name, owner,
   and description.
3. Renames `src/project_name/` to `src/<your_package>/`, and the starter notebook to match.
4. Commits the result, deleting `bootstrap.py` and `TEMPLATE_README.md` — they have done
   their job — and then disables itself through the API.

### Why the workflow disables itself instead of deleting itself

GitHub refuses *any* push from `GITHUB_TOKEN` that creates, updates or deletes a file
under `.github/workflows/`, and there is no permission that grants it:

```
! [remote rejected] HEAD -> main (refusing to allow a GitHub App to create or
  update workflow `.github/workflows/ci.yml` without `workflows` permission)
```

One rejected file rejects the whole push, so a bootstrap commit that touched anything in
that directory would fail and leave the repository sitting on the raw template. Two things
keep that from happening, and both matter:

- **`ci.yml` contains no placeholder tokens.** It finds the package directory at run time
  instead. If you ever add a `{{TOKEN}}` to a file under `.github/workflows/`, you break
  unattended bootstrapping — that is why the comment in `ci.yml` says not to.
- **`bootstrap.py` skips that directory entirely when `GITHUB_ACTIONS=true`**, so it does
  not delete `bootstrap.yml` there. The workflow calls the API to disable itself instead.

Run the script locally and neither restriction applies: a personal token carrying the
`workflow` scope deletes `bootstrap.yml` properly. So if the leftover file bothers you,
`git rm .github/workflows/bootstrap.yml` at any time — it is already inert, since the job
exits early once `bootstrap.py` is gone.

The workflow is guarded by `if: github.event.repository.is_template == false`, so it never
rewrites the template repository, only repositories generated from it. It also checks
whether `bootstrap.py` is still present, so a second push cannot bootstrap an already
bootstrapped project. Generating a repository from the template does fire it: the initial
commit counts as a push, so the run starts within seconds of the repository appearing.

If it ever fails or you skipped it, open the **Actions** tab, select **Bootstrap template**,
and hit **Run workflow** — or just run the script locally, as below. Check
**Settings → Actions → General → Workflow permissions** is set to **Read and write
permissions** if the run fails at the commit step; the workflow cannot push otherwise.

Then follow the generated project's `TEMPLATE_GUIDE.md`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Running the bootstrapper by hand

Everything the Action does lives in `bootstrap.py`, and the script is happy to run on your
machine. Clone the generated repository and run:

```bash
python bootstrap.py
```

With no arguments it derives the owner and repository name from the `origin` remote (or,
failing that, the directory name), the author and email from `git config`, and the year
from today's date. Preview the plan before committing to it:

```bash
python bootstrap.py --dry-run
```

The options:

| Option | Effect |
| --- | --- |
| `--flavor <name>` | Structure to keep: `master`, `minimal`, `general`, `kaggle`, `cookbook` (default `master`) |
| `--repo owner/repo` | Override the auto-detected repository |
| `--description "..."` | Project description; defaults to the derived title |
| `--author "..."` | Author name; defaults to `git config user.name` |
| `--email "..."` | Author email; defaults to `git config user.email` |
| `--keep-scaffolding` | Do not delete `bootstrap.py` and friends afterwards |
| `--dry-run` | Print the plan and change nothing |

Once it has run, commit the result and carry on with the generated project's
`TEMPLATE_GUIDE.md`.

---

## Flavours

A flavour decides how much scaffolding survives bootstrapping. `master` is the full
template; the rest trim it down for smaller jobs.

Every flavour except `cookbook` keeps the same working core — `src/<package>/` with its
`config`, `constants`, `entity` and `utils` subpackages, plus `config/config.yaml` and
`params.yaml`. That is not padding: `main.py` and `app.py` both import
`ConfigurationManager`, which reads those two YAML files and returns the dataclasses in
`entity`. Pruning that core while keeping an entrypoint produces a project that dies with
`ModuleNotFoundError` on the first run, so what the flavours actually vary is the DVC
pipeline, the web app, and the empty stage scaffolding.

| Flavour | Drops | Left with |
| --- | --- | --- |
| `master` | — | Everything: config-driven stages, DVC pipeline, `main.py`, `app.py`, `templates/`, full `src/<package>/`, `tests/` |
| `general` | `dvc.yaml`, and the `components/` + `pipeline/` subpackages | Both entrypoints and the config core, without DVC or empty stage scaffolding |
| `minimal` | `dvc.yaml`, `app.py`, `templates/`, and `components/` + `pipeline/` | A CLI-only project: `main.py`, the config core, `tests/` |
| `kaggle` | `dvc.yaml`, `main.py`, and `components/` + `pipeline/` | Notebook-first work served through `app.py`; also appends `kagglehub` to `requirements-dev.txt` |
| `cookbook` | `src/`, `tests/`, `setup.py`, `requirements.txt`, `main.py`, `app.py`, `config/`, `params.yaml`, `dvc.yaml`, `templates/`, `ci.yml` | A pure exploration workspace: `notebooks/`, `.data/`, `docs/`, `.models/`, `scripts/`, `requirements-dev.txt` |

Pick `master` when in doubt: deleting a directory later is easier than reconstructing one.
Note that `cookbook` drops `requirements.txt` along with the package, so its setup is a
single `pip install -r requirements-dev.txt`, and it drops the CI workflow too since
there is no package left to lint or test.

If you edit `FLAVORS` in `bootstrap.py`, the invariant above is enforced for you:
`validate()` re-walks the surviving import statements after pruning and, if any of them
no longer resolve, prints what broke, leaves `bootstrap.py` in place and exits non-zero
so the CI step does not commit a broken tree.

### Choosing a flavour

Three ways, in order of precedence:

1. **The workflow_dispatch input.** Actions → **Bootstrap template** → **Run workflow** →
   pick a flavour from the dropdown. This wins over everything else.
2. **The `TEMPLATE_FLAVOR` repository variable.** Settings → Secrets and variables →
   Actions → **Variables** → **New repository variable**, named `TEMPLATE_FLAVOR` with a
   value of `master`, `minimal`, `general`, `kaggle`, or `cookbook`. The workflow reads it
   as `vars.TEMPLATE_FLAVOR`, so no file needs editing. The variable has to exist *before*
   the push that triggers bootstrapping — if the repository already exists, set the
   variable and then re-run the workflow manually.
3. **Nothing at all.** The workflow falls back to `master`.

When you run the script locally, `--flavor` decides.

---

## Placeholder tokens

`bootstrap.py` rewrites these across every text file in the tree, skipping binaries, VCS
internals, and itself. Use the exact spelling — double curly braces, uppercase — anywhere
you add new template content. They are shown here literally, for reference.

| Token | Derived from | Example |
| --- | --- | --- |
| `{{PROJECT_NAME}}` | the repository name, as-is | `churn-predictor` |
| `{{PACKAGE_NAME}}` | the repository name, made importable | `churn_predictor` |
| `{{PROJECT_TITLE}}` | the repository name, title-cased | `Churn Predictor` |
| `{{PROJECT_DESCRIPTION}}` | the GitHub repository description | `Predicts subscriber churn.` |
| `{{GITHUB_OWNER}}` | the repository owner | `ThivaV` |
| `{{GITHUB_REPO}}` | owner and repository | `ThivaV/churn-predictor` |
| `{{AUTHOR_NAME}}` | the owner, or `git config user.name` | `ThivaV` |
| `{{AUTHOR_EMAIL}}` | `git config user.email`, or the GitHub noreply address | `thivav@users.noreply.github.com` |
| `{{YEAR}}` | the current year | `2026` |

One sentinel is not a token: the package directory ships on disk as the literal
`src/project_name/`, and `bootstrap.py` renames it. So when you add a file *inside* the
package, put it under `src/project_name/`; when you *write about* the package — in prose,
in a path, or in an import statement — use the `PACKAGE_NAME` token.

---

## Working on the template itself

Clone this repository directly — do not generate a repository from it:

```bash
git clone https://github.com/ThivaV/ml-project-template.git
cd ml-project-template
python bootstrap.py --dry-run     # confirm the plan still looks right
```

A repository created with **Use this template** starts from a single commit and shares no
history with the template. Git treats the two as unrelated, so changes made in a generated
repository **cannot be opened as a pull request back to the template** — GitHub refuses the
comparison. Fixes and improvements belong in a branch of this repository.

When adding files here, keep two things true: placeholders use the token spellings above,
and the content stays complete and runnable rather than a stub, because whatever ships is
what every generated project starts from.

Every generated project gets two documents, and they split the same way. `README.md` is
about the project itself: it ships with only the title, badges, description and licence,
for the project's owner to fill in. `TEMPLATE_GUIDE.md` explains how the scaffold works
— layout, setup, configuration, pipeline, DVC and tests — and is identical across
projects apart from the placeholders. So when you change the scaffold, document it in
`TEMPLATE_GUIDE.md` and leave the README alone.

Despite the shared prefix, `TEMPLATE_GUIDE.md` is not scaffolding like this file:
`bootstrap.py` deletes only the paths listed in `SELF_DESTRUCT`, so the guide stays in
every generated project.

---

## Licence

MIT. The `LICENSE` file carries the placeholder tokens, so each generated project ends up
with its own copyright line.
