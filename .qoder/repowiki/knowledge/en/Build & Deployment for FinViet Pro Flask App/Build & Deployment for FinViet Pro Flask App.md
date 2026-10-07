---
kind: build_system
name: Build & Deployment for FinViet Pro Flask App
category: build_system
scope:
    - '**'
source_files:
    - run.bat
    - requirements.txt
    - app.py
    - api/index.py
    - vercel.json
    - .vercelignore
---

## Build System Overview

FinViet Pro is a Python Flask application with no compiled artifacts. The build system is minimal and consists of:

1. **Local development** via `run.bat` (Windows) or direct `python app.py` invocation.
2. **Dependency management** via a flat `requirements.txt` pinned only to `flask>=3.0`.
3. **Serverless deployment** on Vercel using the `@vercel/python` runtime, configured through `vercel.json` and `.vercelignore`.

There are no Makefiles, Dockerfiles, CI pipelines, cross-compilation steps, or release automation scripts in this repository.

## Key Files

- `run.bat` — Windows launcher that checks for Python 3.10+ on PATH, auto-installs dependencies if Flask is missing, opens `http://127.0.0.1:5000`, then runs `app.py`.
- `requirements.txt` — declares only `flask>=3.0`; all other packages (`sqlite3`, `requests`, etc.) are imported directly from the standard library or vendored at runtime.
- `app.py` — local entry point; calls `fintech.create_app()` and runs the Flask dev server with `threaded=True`.
- `api/index.py` — Vercel serverless entrypoint; prepends the project root to `sys.path` so the sibling `fintech/` package is importable under Vercel's isolated function directory.
- `vercel.json` — declares the `api/index.py` function with `runtime: "python3.12"`, `maxDuration: 60`, includes `fintech/**`, and rewrites every incoming route to `/api/index`.
- `.vercelignore` — excludes `data/`, `tools/`, `.vercel-tmp/`, `__pycache__/`, `*.pyc`, and `*.log` from the Vercel bundle.

## Architecture & Conventions

- **Single-package layout**: The entire application lives in the `fintech/` package; there is no packaging step (`setup.py`, `pyproject.toml`, wheel/sdist). Distribution is by copying source files.
- **Two run modes** share one factory: `create_app()` in `fintech/__init__.py` is called both by `app.py` (local dev) and `api/index.py` (Vercel serverless). This avoids duplicating app wiring.
- **Runtime detection**: `run.bat` uses `where python` and `python -m pip install -r requirements.txt` as a fallback when Flask is not already installed — it does not use virtual environments.
- **Vercel-specific path hack**: Because Vercel functions execute from `api/`, `api/index.py` inserts `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` into `sys.path` so `from fintech import create_app` resolves against the repo root.
- **Static assets**: Under Vercel, static files under `fintech/static/` are served by Flask itself (the rewrite rule sends everything to `/api/index`); they are not served by Vercel's CDN.

## Conventions & Constraints

- **Python version**: `run.bat` requires Python 3.10+ (error message: "Vui long cai Python 3.10+ va them vao PATH"). Vercel runtime is explicitly set to `python3.12` in `vercel.json`.
- **Flask dependency**: `requirements.txt` pins only `flask>=3.0`; no lockfile exists, so installs are non-deterministic beyond that lower bound.
- **No virtualenvs**: `run.bat` installs directly into the active interpreter rather than creating or activating a virtual environment.
- **Bundle size control**: `.vercelignore` enforces exclusion of `data/`, `tools/`, cache files, and logs from the deployed artifact.
- **Function timeout**: Vercel functions are limited to 60 seconds (`maxDuration: 60`) per `vercel.json`.
- **Route rewriting**: Every URL is rewritten to `/api/index` via the `rewrites` array in `vercel.json`, so Flask handles both page templates and REST endpoints under a single serverless function.