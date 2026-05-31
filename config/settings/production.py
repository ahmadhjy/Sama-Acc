"""Production settings for PythonAnywhere and other hosts."""

from config.settings.base import *  # noqa: F401,F403

DEBUG = env_bool("DJANGO_DEBUG", False)

if not ALLOWED_HOSTS:
    raise ValueError(
        "Set DJANGO_ALLOWED_HOSTS in the environment, e.g. "
        "yourusername.pythonanywhere.com"
    )

if SECRET_KEY in (
    "",
    "django-insecure-dev-only-change-before-production",
):
    raise ValueError(
        "Set DJANGO_SECRET_KEY to a long random string before running in production."
    )

# HTTPS on PythonAnywhere
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", True)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [
        f"https://{host}" for host in ALLOWED_HOSTS if host and not host.startswith(".")
    ]

if env_bool("DJANGO_ENABLE_HSTS", False):
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# PythonAnywhere terminates HTTPS; do not force SECURE_SSL_REDIRECT here.

# Do not expose debug context in production templates
TEMPLATES[0]["OPTIONS"]["context_processors"] = [
    p
    for p in TEMPLATES[0]["OPTIONS"]["context_processors"]
    if p != "django.template.context_processors.debug"
]
