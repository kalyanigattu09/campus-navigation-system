"""Django settings for the campus_nav project."""
import os
import tempfile
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _runtime_data_dir() -> Path:
    """Return a writable directory for the local SQLite database."""
    configured = os.environ.get("CAMPUS_NAV_DATA_DIR")
    candidates = (
        [Path(configured)]
        if configured
        else [
            Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
            / "CampusNavigation",
            Path(tempfile.gettempdir()) / "CampusNavigation",
        ]
    )
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return candidate
    return BASE_DIR


DEFAULT_DATA_DIR = _runtime_data_dir()

# SECURITY: Secret key configuration with environment variable override
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-campus-nav-dev-key-change-me-in-production",
)

# Debug mode flag controlled via environment
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

# Allowed hosts configuration (supports Render domain and local environments)
hosts_env = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1,::1,.onrender.com,*",
)
ALLOWED_HOSTS = [h.strip() for h in hosts_env.split(",") if h.strip()]

# CSRF trusted origins for HTTPS deployments (required for form submissions on public domains)
csrf_env = os.environ.get(
    "CSRF_TRUSTED_ORIGINS",
    "https://*.onrender.com,http://localhost:8000,http://127.0.0.1:8000",
)
CSRF_TRUSTED_ORIGINS = [orig.strip() for orig in csrf_env.split(",") if orig.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "corsheaders",
    "navigation",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "campus_nav.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "navigation" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "campus_nav.wsgi.application"

# Database configuration:
# Uses PostgreSQL on Render via DATABASE_URL; falls back to SQLite for local development.
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(
                os.environ.get("CAMPUS_NAV_DB_PATH", DEFAULT_DATA_DIR / "db.sqlite3")
            ),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
] if not DEBUG else []

LOGIN_URL = "/admin-login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images) with WhiteNoise production strategy
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS configuration
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True
