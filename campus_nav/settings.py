"""Django settings for the campus_nav project."""
import os
import tempfile
from pathlib import Path

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

# SECURITY: keep the secret key out of source control in real projects.
SECRET_KEY = "django-insecure-campus-nav-dev-key-change-me-in-production"

# Allow all hosts during local development.
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "navigation",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [],
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

# SQLite is fine for local development. Keep it outside OneDrive by default
# because cloud-synced reparse files can cause sqlite3 disk I/O errors.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(
            os.environ.get("CAMPUS_NAV_DB_PATH", DEFAULT_DATA_DIR / "db.sqlite3")
        ),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS: allow the dev server to call the API from any origin.
CORS_ALLOW_ALL_ORIGINS = True
