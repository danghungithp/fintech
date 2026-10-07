"""Vercel serverless entrypoint.

The @vercel/python runtime loads this file and serves the Flask WSGI callable `app`.
All HTTP routes are rewritten here by vercel.json; Flask then serves both the
pages/templates and the REST API, including the /static assets.
"""
from __future__ import annotations

import os
import sys

# Make the project root importable (the fintech package lives one level up).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fintech import create_app  # noqa: E402

app = create_app()
