"""
Réglages Django de Chess Coach.

Les valeurs importantes peuvent être surchargées par variables d'environnement
(voir README.md) : STOCKFISH_PATH, ANALYSIS_WORKERS, ANALYSIS_TIME_BULK, etc.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None, cast=str):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    if cast is bool:
        return value.lower() in ("1", "true", "yes", "on", "oui")
    return cast(value)


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-change-me-chesscoach")
DEBUG = env("DJANGO_DEBUG", True, bool)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "analyzer",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "analyzer.context_processors.appearance",
                "analyzer.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("CHESSCOACH_DB", str(BASE_DIR / "db.sqlite3")),
        # Les analyses écrivent depuis un thread d'arrière-plan : on laisse
        # SQLite attendre un peu au lieu de lever "database is locked".
        "OPTIONS": {"timeout": 30},
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = env("TIME_ZONE", "Africa/Abidjan")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Taille max d'un upload PGN (en octets) : 50 Mo.
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

# --------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------
# Chemin vers l'exécutable Stockfish. Vide = détection automatique
# (PATH, /usr/games, Homebrew, C:\Program Files\stockfish...).
STOCKFISH_PATH = env("STOCKFISH_PATH", "")
# Nombre de moteurs lancés en parallèle pour analyser un export.
ANALYSIS_WORKERS = env("ANALYSIS_WORKERS", max(1, (os.cpu_count() or 2) - 1), int)
# Temps de réflexion par position (secondes) pour l'analyse d'un export complet.
ANALYSIS_TIME_BULK = env("ANALYSIS_TIME_BULK", 0.05, float)
# Temps par position pour l'analyse approfondie d'une seule partie.
ANALYSIS_TIME_SINGLE = env("ANALYSIS_TIME_SINGLE", 0.3, float)
STOCKFISH_HASH_MB = env("STOCKFISH_HASH_MB", 64, int)

# Notation affichée : "fr" (R D T F C) ou "en" (K Q R B N).
NOTATION = env("CHESSCOACH_NOTATION", "fr")

# --------------------------------------------------------------------------
# Chess.com (API publique gratuite, sans clé)
# --------------------------------------------------------------------------
# Chess.com demande un User-Agent identifiable ; ajoute ton contact si tu veux
# (ex. "chesscoach/1.0 (contact: moi@exemple.com)").
CHESSCOM_USER_AGENT = env("CHESSCOM_USER_AGENT", "chesscoach-django/1.0")
# Synchro automatique à l'ouverture d'un compte Chess.com si la dernière date
# de plus de N heures (0 = désactivé).
CHESSCOM_AUTO_SYNC_HOURS = env("CHESSCOM_AUTO_SYNC_HOURS", 12, int)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"analyzer": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")}},
}
