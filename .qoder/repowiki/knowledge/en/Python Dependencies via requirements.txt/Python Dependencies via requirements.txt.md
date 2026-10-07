---
kind: dependency_management
name: Python Dependencies via requirements.txt
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
---

## Dependency Management Approach

This repository is a Python Flask application and uses the standard `pip` ecosystem for dependency management. There are no other package managers present (no `setup.py`, `pyproject.toml`, `Pipfile`, `poetry.lock`, or vendored third-party code under a `vendor/` directory).

### Key Files

- `requirements.txt` — the sole dependency manifest, declaring only one runtime dependency: `flask>=3.0`.

### Observed Conventions

- **Single manifest file**: All dependencies are declared in `requirements.txt` at the repository root; there is no per-package or per-environment split.
- **Loose version pinning**: The only entry uses a lower-bound constraint (`flask>=3.0`) rather than an exact pin (e.g., `==3.x.y`). This means installs resolve to the latest compatible Flask release available from PyPI at install time, which can lead to non-reproducible builds across environments.
- **No lockfile**: There is no `requirements.lock`, `Pipfile.lock`, `poetry.lock`, or equivalent artifact committed alongside `requirements.txt`. Dependency resolution is not pinned to specific transitive versions.
- **No private registry configuration**: No `pip.conf`, `~/.pip/pip.conf`, `PYPI_URL`, `--index-url`, or `--extra-index-url` usage was found in the codebase. Dependencies are resolved against the default PyPI index.
- **No vendoring**: Third-party packages are expected to be installed into the active Python environment's site-packages; no vendored copies of libraries exist under `fintech/`, `static/`, or elsewhere.
- **Runtime imports**: The application code imports directly from `flask` and standard-library modules throughout `app.py`, `fintech/routes.py`, `fintech/config.py`, etc., with no abstraction layer around dependency loading.

### Constraints

- The project has exactly one external runtime dependency: `flask` (version 3.0 or newer). No other third-party packages are imported by the application code observed in this branch.