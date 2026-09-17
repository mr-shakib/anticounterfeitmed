"""Django settings for the medicine verification backend.

Development defaults live here; every value that differs in staging or pilot is
read from the environment. Nothing secret has a usable default -- a missing
SECRET_KEY or database password should fail loudly rather than silently run with
a well-known value.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)

# A generated development key is acceptable only while DEBUG is on.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or (
    "dev-insecure-key-not-for-deployment" if DEBUG else env("DJANGO_SECRET_KEY")
)

ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

# Django checks the Origin header on cookie-authenticated writes. In production
# the portal and the API share an origin behind nginx, so the check passes on
# its own. In development they run on different ports, so the portal's origin
# has to be named here -- otherwise every staff write fails CSRF with a message
# that reads like a permissions problem.
CSRF_TRUSTED_ORIGINS = [
    o for o in env(
        "CSRF_TRUSTED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:3100,http://localhost:3100"
        if DEBUG
        else "",
    ).split(",")
    if o
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.organizations",
    "apps.catalog",
    "apps.serialization",
    "apps.qc",
    "apps.trust",
    "apps.activation",
    "apps.verification",
    "apps.reports",
    "apps.audit",
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
WSGI_APPLICATION = "config.wsgi.application"

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
            ]
        },
    }
]

# PostgreSQL only. SQLite cannot exercise row locks or partial unique indexes,
# so it would give a false pass on the guarantees this system depends on.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "acm"),
        "USER": env("POSTGRES_USER", "acm"),
        "PASSWORD": env("POSTGRES_PASSWORD", "acm_dev_only"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "55432"),
        "ATOMIC_REQUESTS": False,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Endpoints declare their own authentication explicitly. There is no global
    # default, so a new view cannot inherit consumer authority by accident.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_RATES": {
        # Pilot starting values (docs/05). Tune against real networks.
        "consumer_prepare": env("RATE_LIMIT_PREPARE", "30/min"),
        "consumer_confirm": env("RATE_LIMIT_CONFIRM", "10/min"),
    },
}

# Throttling needs a shared cache in a deployed environment; per-process memory
# would let each worker grant its own allowance.
CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_CACHE_URL", "redis://127.0.0.1:56379/1"),
        }
        if env_bool("USE_REDIS_CACHE", False)
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "acm-local",
        }
    )
}

# --- app attestation --------------------------------------------------------
APP_CHECK_MODE = env("APP_CHECK_MODE", "accept-any")  # "accept-any" | "firebase"
APP_CHECK_ALLOW_INSECURE = env_bool("APP_CHECK_ALLOW_INSECURE", False)
APP_CHECK_PROJECT_NUMBER = os.environ.get("APP_CHECK_PROJECT_NUMBER", "")
APP_CHECK_ALLOWED_APP_IDS = [
    a for a in os.environ.get("APP_CHECK_ALLOWED_APP_IDS", "").split(",") if a
]

# --- verification policy (docs/05 pilot starting values) -------------------
# These are pilot settings to be tuned against real network measurements, not
# properties of the cryptography.
CHALLENGE_TTL_SECONDS = int(env("CHALLENGE_TTL_SECONDS", "120"))
STATUS_ENVELOPE_TTL_SECONDS = int(env("STATUS_ENVELOPE_TTL_SECONDS", "120"))
TRUST_MANIFEST_CACHE_SECONDS = int(env("TRUST_MANIFEST_CACHE_SECONDS", str(24 * 3600)))

# --- signing service --------------------------------------------------------
# In development the backend may sign in-process. Staging and pilot must point
# at the isolated signer, which is the only component holding private keys.
SIGNER_MODE = env("SIGNER_MODE", "local")  # "local" | "service"

# In-process signing is refused outside DEBUG. The test suite sets this
# explicitly; nothing else should. It exists so the DEBUG guard stays strict
# rather than being loosened to accommodate tests.
SIGNER_ALLOW_INSECURE_LOCAL = env_bool("SIGNER_ALLOW_INSECURE_LOCAL", False)
SIGNER_URL = os.environ.get("SIGNER_URL", "")

# Development keystore. Real deployments populate the signing service's own
# store from a secret manager; the backend never reads this path in "service"
# mode and never holds key material itself.
SIGNER_KEYSTORE_PATH = env("SIGNER_KEYSTORE_PATH", str(BASE_DIR.parent / ".keys"))

CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://127.0.0.1:56379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
