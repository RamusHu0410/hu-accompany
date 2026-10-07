import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-in-production")

DEBUG = os.environ.get("DEBUG", "True") == "True"

ALLOWED_HOSTS = ["*"]

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

MIDDLEWARE = [
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
