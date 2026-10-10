import os
from pathlib import Path
from dotenv import load_dotenv

from server.config import build_settings

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Development by default; production when DJANGO_ENV=production or on Cloud Run (K_SERVICE).
# See server/config.py for what each mode requires.
_config = build_settings(os.environ)
IS_PRODUCTION = _config["IS_PRODUCTION"]
SECRET_KEY = _config["SECRET_KEY"]
DEBUG = _config["DEBUG"]
ALLOWED_HOSTS = _config["ALLOWED_HOSTS"]
SECURE_PROXY_SSL_HEADER = _config["SECURE_PROXY_SSL_HEADER"]
# The shared key the app sends in X-App-Key, and the per-minute limits (0 = off).
APP_API_KEY = _config["APP_API_KEY"]
RATE_LIMIT_HUM_PER_MINUTE = _config["RATE_LIMIT_HUM_PER_MINUTE"]
RATE_LIMIT_DEFAULT_PER_MINUTE = _config["RATE_LIMIT_DEFAULT_PER_MINUTE"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "api",
    "scores",
    "hum",
]

# Root directory score files are stored under; the DB stores paths
# relative to this (e.g. "musicxml/Qm....musicxml").
STORAGE_ROOT = BASE_DIR / "storage"

# Hummed recordings and the songs made from them (hum app). Kept out of STORAGE_ROOT, which
# server/urls.py serves publicly.
HUM_DATA_DIR = Path(os.environ.get("HUM_DATA_DIR", BASE_DIR / "hum_data"))

# Order matters (server/middleware.py): health check, rate limit, app key, then Django.
MIDDLEWARE = [
    "server.middleware.HealthCheckMiddleware",
    "server.middleware.RateLimitMiddleware",
    "server.middleware.AppKeyMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "server.urls"

WSGI_APPLICATION = "server.wsgi.application"

# PostgreSQL is the single source of truth for all catalog + pipeline data.
# Only score files (MusicXML, plus legacy PDFs and page PNGs) live on disk
# under STORAGE_ROOT; everything else -- the score catalog and the legacy
# OMR pipeline's structured output -- is stored here.
#
# Defaults match backend/docker-compose.yml's postgres service; override any
# of them via the environment (e.g. in .env).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "music_catalog"),
        "USER": os.environ.get("POSTGRES_USER", "app"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "local_dev_password"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
