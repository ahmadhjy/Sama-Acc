"""
Shared Django settings for Sama Accounting (dev + production).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_bool(key, default=False):
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def env_list(key, default=None):
    raw = os.environ.get(key, "")
    if not raw.strip():
        return list(default or [])
    return [part.strip() for part in raw.split(",") if part.strip()]


def load_dotenv(path=None):
    """Load KEY=VALUE lines from a .env file into os.environ (only unset keys)."""
    dotenv_path = Path(path) if path else BASE_DIR / ".env"
    if not dotenv_path.is_file():
        return
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-before-production",
)

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts_core.apps.AccountsCoreConfig",
    "catalog",
    "sales",
    "purchases",
    "treasury",
    "reporting",
    "expenses",
    "auditlog",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts_core.context_processors.pdf_branding",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_db_engine = os.environ.get("DJANGO_DB_ENGINE", "sqlite").lower()
if _db_engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ["DJANGO_DB_NAME"],
            "USER": os.environ["DJANGO_DB_USER"],
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    db_path = os.environ.get("DJANGO_DB_PATH")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(db_path) if db_path else BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Beirut")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

COMPANY_LEGAL_NAME = os.environ.get("COMPANY_LEGAL_NAME", "Sama Tours")
COMPANY_ADDRESS = os.environ.get(
    "COMPANY_ADDRESS",
    "Gallerie Semaan Crossroad, Hazmieh Highway, "
    "Hyundai Car Showroom Building, 1st Floor, Hazmieh",
)
COMPANY_PHONE = os.environ.get("COMPANY_PHONE", "+961 25 450 473 | +961 76 832 813")
COMPANY_EMAIL = os.environ.get("COMPANY_EMAIL", "info@samatourslb.com")
COMPANY_FINANCIAL_ACCOUNT = os.environ.get("COMPANY_FINANCIAL_ACCOUNT", "")
COMPANY_FOOTER_TEXT = os.environ.get(
    "COMPANY_FOOTER_TEXT", "© 2026 Sama Tours. All rights reserved."
)
COMPANY_TAGLINE = os.environ.get(
    "COMPANY_TAGLINE", "Travel beyond your imagination, with Sama Tours!"
)
COMPANY_DEFAULT_CURRENCY = os.environ.get("COMPANY_DEFAULT_CURRENCY", "USD")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
