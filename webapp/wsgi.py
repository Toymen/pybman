"""Production WSGI entry point, e.g. ``gunicorn webapp.wsgi:app``."""

from __future__ import annotations

from webapp.app import build_app

app = build_app()
