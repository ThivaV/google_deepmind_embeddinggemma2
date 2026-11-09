#!/usr/bin/env python3
"""Bootstrap a project generated from the template.

Every placeholder value is derived automatically -- there is nothing to type.
The repository name drives everything else::

    churn-predictor  ->  package churn_predictor, title "Churn Predictor"

Run it once after generating a repo from the template::

    python bootstrap.py                  # master flavour, values auto-derived
    python bootstrap.py --flavor minimal # trim to a smaller structure
    python bootstrap.py --dry-run        # show the plan, change nothing

The script rewrites the placeholders, renames the package directory, prunes the
files the chosen flavour does not need, and finally deletes itself along with
the rest of the template-only scaffolding.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s]: %(message)s:")
log = logging.getLogger("bootstrap")

ROOT = Path(__file__).resolve().parent

# The literal directory/file names the template ships with, before renaming.
SENTINEL_PACKAGE = "project_name"

# Template-only scaffolding, removed once bootstrapping succeeds.
SELF_DESTRUCT = [
    "bootstrap.py",
    ".github/workflows/bootstrap.yml",
    "TEMPLATE_README.md",
]

# Never rewritten: binary payloads, VCS internals, and this script itself.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
SKIP_FILES = {"bootstrap.py"}

# GitHub refuses any push from GITHUB_TOKEN that creates, updates or deletes a file
# under .github/workflows/ -- there is no permission that grants it, so a commit
# touching this directory is rejected outright:
#
#   ! [remote rejected] HEAD -> main (refusing to allow a GitHub App to create or
#     update workflow `.github/workflows/ci.yml` without `workflows` permission)
#
# So when running inside Actions we leave that directory completely alone: ci.yml is
# deliberately placeholder-free, and bootstrap.yml disables itself through the API
# instead of deleting itself. Run this script locally and the restriction does not
# apply -- a personal token with the `workflow` scope cleans up properly.
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
PROTECTED_IN_ACTIONS = Path(".github") / "workflows"
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".whl", ".so", ".dylib", ".dll", ".pyc", ".parquet", ".pkl", ".joblib", ".onnx",
    ".h5", ".pt", ".pth", ".bin", ".npy", ".npz", ".xlsx",
}

# Paths each flavour drops. "master" keeps everything.
#
# INVARIANT -- read this before editing a flavour. main.py and app.py both import
# ConfigurationManager, which reads config/config.yaml and params.yaml and returns
# the dataclasses in <pkg>/entity. So any flavour that keeps EITHER entrypoint must
# also keep all of:
#
#     src/<pkg>/{config,constants,entity,utils}   config/   params.yaml
#
# Pruning that core while keeping an entrypoint is what makes a generated project
# die with ModuleNotFoundError on first run. validate() below re-checks this after
# pruning, so a mistake here surfaces as a loud warning rather than a broken repo.
#
# components/ and pipeline/ are imported by nothing -- they are scaffolding for the
# user's own code, and are always safe to drop. app.py and templates/ are a pair:
# drop them together or not at all.
FLAVORS: dict[str, list[str]] = {
    # Everything: config-driven pipeline, DVC, Flask app.
    "master": [],
    # Full pipeline and app, but no DVC and no empty stage scaffolding.
    "general": [
        "dvc.yaml",
        f"src/{SENTINEL_PACKAGE}/components",
        f"src/{SENTINEL_PACKAGE}/pipeline",
    ],
    # CLI pipeline only -- no web app, no DVC.
    "minimal": [
        "dvc.yaml", "app.py", "templates",
        f"src/{SENTINEL_PACKAGE}/components",
        f"src/{SENTINEL_PACKAGE}/pipeline",
    ],
    # Notebook-first competition work, served through the Flask app; no CLI pipeline.
    "kaggle": [
        "dvc.yaml", "main.py",
        f"src/{SENTINEL_PACKAGE}/components",
        f"src/{SENTINEL_PACKAGE}/pipeline",
    ],
    # Pure exploration: notebooks, data and models, nothing installable.
    "cookbook": [
        "config", "params.yaml", "dvc.yaml", "templates", "app.py", "main.py",
        "setup.py", "requirements.txt", "src", "tests", ".github/workflows/ci.yml",
    ],
}

# Extra dependencies a flavour adds to requirements-dev.txt.
FLAVOR_EXTRA_DEPS: dict[str, list[str]] = {"kaggle": ["kagglehub"]}


def run_git(*args: str) -> str:
    """Return trimmed stdout of a git command, or "" when git has nothing to say."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def parse_remote(url: str) -> tuple[str, str] | None:
    """Pull (owner, repo) out of an ssh or https GitHub remote URL."""
    if not url:
        return None
    url = url.removesuffix(".git")
    # git@github.com:Owner/repo  |  ssh://git@github.com/Owner/repo
    # https://github.com/Owner/repo
    match = re.search(r"[:/]([^/:]+)/([^/]+)$", url)
    if not match:
        return None
    return match.group(1), match.group(2)


def derive_repo(explicit: str | None) -> tuple[str, str]:
    """Resolve owner/repo from the CLI, the CI environment, git, then the folder name."""
    for candidate in (explicit, os.environ.get("GITHUB_REPOSITORY")):
        if candidate and "/" in candidate:
            owner, repo = candidate.split("/", 1)
            return owner, repo

    parsed = parse_remote(run_git("config", "--get", "remote.origin.url"))
    if parsed:
        return parsed

    # No remote yet -- fall back to the directory name and the local git identity.
    owner = os.environ.get("GITHUB_ACTOR") or run_git("config", "user.name") or "your-username"
    return owner, ROOT.name


def to_package(name: str) -> str:
    """Turn a repo name into an importable Python package name."""
    pkg = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    pkg = re.sub(r"_+", "_", pkg)
    if not pkg:
        pkg = "app"
    if pkg[0].isdigit():
        pkg = f"pkg_{pkg}"
    return pkg


def to_title(name: str) -> str:
    """Turn a repo name into a human-readable title."""
    words = [w for w in re.split(r"[^0-9a-zA-Z]+", name) if w]
    return " ".join(w if w.isupper() else w.capitalize() for w in words) or name


def build_context(args: argparse.Namespace) -> dict[str, str]:
    """Assemble every placeholder value, deriving what was not passed explicitly."""
    owner, repo = derive_repo(args.repo)
    package = to_package(repo)
    author = args.author or run_git("config", "user.name") or owner
    email = args.email or run_git("config", "user.email") or f"{owner}@users.noreply.github.com"
    description = args.description or f"{to_title(repo)}."

    return {
        "PROJECT_NAME": repo,
        "PACKAGE_NAME": package,
        "PROJECT_TITLE": to_title(repo),
        "PROJECT_DESCRIPTION": description,
        "GITHUB_OWNER": owner,
        "GITHUB_REPO": f"{owner}/{repo}",
        "AUTHOR_NAME": author,
        "AUTHOR_EMAIL": email,
        "YEAR": str(datetime.date.today().year),
    }


def iter_text_files() -> list[Path]:
    """Every file worth running a text substitution over."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if filename in SKIP_FILES or path.suffix.lower() in BINARY_SUFFIXES:
                continue
            if IN_ACTIONS and PROTECTED_IN_ACTIONS in path.relative_to(ROOT).parents:
                continue  # GITHUB_TOKEN may not push changes here
            found.append(path)
    return found


def substitute(context: dict[str, str], dry_run: bool) -> int:
    """Replace every {{TOKEN}} across the tree. Returns the number of files touched."""
    pattern = re.compile(r"\{\{\s*(" + "|".join(map(re.escape, context)) + r")\s*\}\}")
    touched = 0

    for path in iter_text_files():
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable -- leave it exactly as it is
        updated = pattern.sub(lambda m: context[m.group(1)], original)
        if updated == original:
            continue
        touched += 1
        log.info("Rewrote placeholders in: %s", path.relative_to(ROOT))
        if not dry_run:
            path.write_text(updated, encoding="utf-8")

    return touched


def rename_sentinels(package: str, dry_run: bool) -> None:
    """Rename the placeholder package directory and notebook to the real name."""
    renames = [
        (ROOT / "src" / SENTINEL_PACKAGE, ROOT / "src" / package),
        (ROOT / "notebooks" / f"{SENTINEL_PACKAGE}.ipynb", ROOT / "notebooks" / f"{package}.ipynb"),
    ]
    for source, target in renames:
        if not source.exists() or source == target:
            continue
        if target.exists():
            log.warning("Skipping rename, target already exists: %s", target.relative_to(ROOT))
            continue
        log.info("Renaming %s -> %s", source.relative_to(ROOT), target.relative_to(ROOT))
        if not dry_run:
            source.rename(target)


def prune(flavor: str, dry_run: bool) -> None:
    """Drop the paths the chosen flavour does not use, then tidy up empty directories."""
    for relative in FLAVORS[flavor]:
        target = ROOT / relative
        if not target.exists():
            continue
        log.info("Pruning (%s flavour): %s", flavor, relative)
        if dry_run:
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    if dry_run:
        return

    # Drop directories the pruning emptied out. Anything holding a .gitkeep is
    # deliberately empty (.data/, .models/, ...) and stays.
    for dirpath, dirnames, filenames in os.walk(ROOT, topdown=False):
        directory = Path(dirpath)
        if directory == ROOT or any(part in SKIP_DIRS for part in directory.parts):
            continue
        if not dirnames and not filenames:
            log.info("Removing emptied directory: %s", directory.relative_to(ROOT))
            directory.rmdir()


def apply_extra_deps(flavor: str, dry_run: bool) -> None:
    """Append the flavour-specific dependencies to requirements-dev.txt."""
    extras = FLAVOR_EXTRA_DEPS.get(flavor)
    requirements = ROOT / "requirements-dev.txt"
    if not extras or not requirements.exists():
        return

    existing = requirements.read_text(encoding="utf-8")
    missing = [dep for dep in extras if dep not in existing.split()]
    if not missing:
        return

    log.info("Adding %s dependencies to requirements-dev.txt: %s", flavor, ", ".join(missing))
    if not dry_run:
        separator = "" if existing.endswith("\n") or not existing else "\n"
        requirements.write_text(existing + separator + "\n".join(missing) + "\n", encoding="utf-8")


def validate(package: str) -> list[str]:
    """Re-check the FLAVORS invariant against what actually survived pruning.

    Walks the real import statements left in the tree and confirms each one still
    resolves on disk. This is the safety net for the invariant documented above
    FLAVORS: it turns "this flavour generates a repo that dies on first import"
    into a warning printed while the user is still looking at the output.
    """
    problems: list[str] = []
    package_root = ROOT / "src" / package
    if not package_root.is_dir():
        return problems  # cookbook and friends ship no package at all

    available = {
        entry.stem if entry.suffix == ".py" else entry.name
        for entry in package_root.iterdir()
        if entry.is_dir() or entry.suffix == ".py"
    }
    # Only inspect genuine import statements -- prose in a docstring that mentions a
    # pruned module is not a defect.
    import_re = re.compile(
        rf"^\s*(?:from|import)\s+{re.escape(package)}\.([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
    )

    for path in iter_text_files():
        if path.suffix != ".py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for submodule in set(import_re.findall(source)):
            if submodule not in available:
                problems.append(
                    f"{path.relative_to(ROOT)} imports {package}.{submodule}, which this flavour pruned"
                )

    # ConfigurationManager is useless without the YAML it reads.
    if "config" in available:
        for required in ("config/config.yaml", "params.yaml"):
            if not (ROOT / required).exists():
                problems.append(f"{package}.config was kept but {required} was pruned")

    return problems


def self_destruct(dry_run: bool) -> None:
    """Remove the template-only scaffolding, including this script."""
    for relative in SELF_DESTRUCT:
        target = ROOT / relative
        if not target.exists():
            continue
        if IN_ACTIONS and PROTECTED_IN_ACTIONS in Path(relative).parents:
            log.info(
                "Leaving %s in place: GITHUB_TOKEN cannot push workflow changes. "
                "It disables itself through the API instead, and is inert either way.",
                relative,
            )
            continue
        log.info("Removing template scaffolding: %s", relative)
        if not dry_run:
            target.unlink()


def main() -> int:
    """Derive the values, rewrite the tree, and step out of the way."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--flavor", choices=sorted(FLAVORS), default="master", help="structure to keep (default: master)")
    parser.add_argument("--repo", help="owner/repo; auto-detected from the git remote when omitted")
    parser.add_argument("--description", help="project description; defaults to the project title")
    parser.add_argument("--author", help="author name; defaults to git config user.name")
    parser.add_argument("--email", help="author email; defaults to git config user.email")
    parser.add_argument("--keep-scaffolding", action="store_true", help="do not delete bootstrap.py and friends")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without changing anything")
    args = parser.parse_args()

    context = build_context(args)

    log.info("Bootstrapping with the %s flavour:", args.flavor)
    for key, value in context.items():
        log.info("  %-20s %s", key, value)

    prune(args.flavor, args.dry_run)
    apply_extra_deps(args.flavor, args.dry_run)
    touched = substitute(context, args.dry_run)
    rename_sentinels(context["PACKAGE_NAME"], args.dry_run)

    if args.dry_run:
        log.info("Dry run finished -- nothing was written.")
        return 0

    problems = validate(context["PACKAGE_NAME"])
    if problems:
        log.error("The %s flavour left the project inconsistent:", args.flavor)
        for problem in problems:
            log.error("  %s", problem)
        log.error("Keeping bootstrap.py so this is fixable -- see FLAVORS in it.")
        return 1

    if not args.keep_scaffolding:
        self_destruct(args.dry_run)

    log.info("Done. %s files updated. Next: python -m venv .venv && pip install -r requirements.txt", touched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
