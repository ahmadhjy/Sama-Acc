"""
WSGI config for config project.

On PythonAnywhere, set DJANGO_SETTINGS_MODULE=config.settings.production
in the Web tab WSGI file (see deploy/pythonanywhere_wsgi.py.example).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
