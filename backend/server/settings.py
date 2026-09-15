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
    "imslp_downloader",
]

# Root directory downloaded PDFs are stored under; the DB stores paths
# relative to this (e.g. "scores/Beethoven/Moonlight_Sonata/piano.pdf").
STORAGE_ROOT = BASE_DIR / "storage"

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "server.urls"

WSGI_APPLICATION = "server.wsgi.application"

# PostgreSQL is the single source of truth for all catalog + pipeline data.
# Only the PDFs (and rendered page/debug PNGs) live on disk under
# STORAGE_ROOT; everything else -- IMSLP works/versions, download records,
# and the OMR pipeline's structured output (notes, markings, piece_data,
# bar_boxes, MusicXML) -- is stored here.
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
