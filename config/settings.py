"""
Backward-compatible entry point for local development.

Production (PythonAnywhere) uses config.settings.production via WSGI.
"""

from config.settings.development import *  # noqa: F401,F403
