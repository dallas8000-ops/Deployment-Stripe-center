import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

_env_hosts = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
ALLOWED_HOSTS = _env_hosts or ["localhost", "127.0.0.1"]
for _h in [".railway.app", ".up.railway.app"]:
    if _h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)
if os.environ.get("RAILWAY_PUBLIC_DOMAIN") and os.environ["RAILWAY_PUBLIC_DOMAIN"] not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(os.environ["RAILWAY_PUBLIC_DOMAIN"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "channels",
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.projects",
    "apps.vault",
    "apps.stripe_engine",
    "apps.runs",
    "apps.billing",
    "apps.deploy",
    "apps.ai",
    "apps.licenses",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

if os.environ.get("DATABASE_URL"):
    # postgres://user:pass@host:5432/dbname
    import urllib.parse as urlparse

    url = urlparse.urlparse(os.environ["DATABASE_URL"])
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": url.path[1:],
        "USER": url.username,
        "PASSWORD": url.password,
        "HOST": url.hostname,
        "PORT": url.port or 5432,
    }

AUTH_USER_MODEL = "accounts.User"

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
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    STATICFILES_DIRS = [FRONTEND_DIST]
else:
    STATICFILES_DIRS = []

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

PROJECT_CLONE_ROOT = os.environ.get("PROJECT_CLONE_ROOT", str(BASE_DIR / "clones"))
GIT_SSH_KEY_PATH = os.environ.get("GIT_SSH_KEY_PATH", "")
GIT_CREDENTIALS_PATH = os.environ.get("GIT_CREDENTIALS_PATH", "")

_cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
for _co in ["https://stripe-installer-production.up.railway.app"]:
    if _co not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_co)
if os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
    _co = f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
    if _co not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_co)
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
}

# 32-byte master key — hex (64 chars) or base64. Generate: python -c "import secrets; print(secrets.token_hex(32))"
VAULT_MASTER_KEY = os.environ.get("VAULT_MASTER_KEY", "")

# Optional path to legacy Node CLI (legacy/node/dist/cli.js) — Python codegen works without this
STRIPE_INSTALLER_CLI = os.environ.get("STRIPE_INSTALLER_CLI", "")

# Platform billing (Stripe Installer SaaS — dogfood our own integration)
# Pricing: $79/mo flat rate per customer (7900 cents)
SAAS_STRIPE_SECRET_KEY = os.environ.get("SAAS_STRIPE_SECRET_KEY", "")
SAAS_STRIPE_WEBHOOK_SECRET = os.environ.get("SAAS_STRIPE_WEBHOOK_SECRET", "")
SAAS_STRIPE_PRICE_STARTER = os.environ.get("SAAS_STRIPE_PRICE_STARTER", "")
SAAS_STRIPE_PRICE_PRO = os.environ.get("SAAS_STRIPE_PRICE_PRO", "")
SAAS_STRIPE_PRICE_ENTERPRISE = os.environ.get("SAAS_STRIPE_PRICE_ENTERPRISE", "")
SAAS_BILLING_RETURN_URL = os.environ.get("SAAS_BILLING_RETURN_URL", "http://localhost:5173")

# License enforcement settings
LICENSE_ENFORCEMENT_ENABLED = os.environ.get("LICENSE_ENFORCEMENT_ENABLED", "false").lower() == "true"
LICENSE_ENFORCEMENT_MODE = os.environ.get("LICENSE_ENFORCEMENT_MODE", "readonly")
LICENSE_READ_ONLY_MESSAGE = os.environ.get("LICENSE_READ_ONLY_MESSAGE", "License invalid - running in read-only mode")
LICENSE_VALIDATION_SERVER = os.environ.get("STRIPE_INSTALLER_VALIDATION_SERVER", "")
LICENSE_EMAIL_ENABLED = os.environ.get("LICENSE_EMAIL_ENABLED", "true").lower() == "true"

if LICENSE_ENFORCEMENT_ENABLED:
    MIDDLEWARE.append("apps.licenses.middleware.LicenseEnforcementMiddleware")

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_EAGER", "").lower() == "true"

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "check-all-projects-drift": {
        "task": "stripe_engine.check_all_projects_drift",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "auto-heal-all-projects": {
        "task": "stripe_engine.auto_heal_all_projects",
        "schedule": crontab(minute=30, hour="*/12"),
    },
    "health-monitor-all-projects": {
        "task": "stripe_engine.health_monitor_all_projects",
        "schedule": crontab(minute="*/30"),
    },
    "anomaly-detection-all-projects": {
        "task": "stripe_engine.anomaly_detection_all_projects",
        "schedule": crontab(minute=0, hour="*/4"),
    },
    "auto-backup-all-projects": {
        "task": "stripe_engine.auto_backup_all_projects",
        "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM UTC
    },
}

# GitHub App (optional — PR check runs + webhooks)
GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
GITHUB_APP_SLUG = os.environ.get("GITHUB_APP_SLUG", "")
GITHUB_APP_SETUP_URL = os.environ.get("GITHUB_APP_SETUP_URL", "")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

# Org billing free tier (when SAAS_STRIPE_* is configured)
ORG_FREE_MEMBER_LIMIT = os.environ.get("ORG_FREE_MEMBER_LIMIT", "3")
ORG_FREE_PROJECT_LIMIT = os.environ.get("ORG_FREE_PROJECT_LIMIT", "5")

# Public app URL (invites, billing return). Defaults to SAAS_BILLING_RETURN_URL.
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
ORG_INVITE_EXPIRY_DAYS = os.environ.get("ORG_INVITE_EXPIRY_DAYS", "14")
INVITE_EMAIL_ENABLED = os.environ.get("INVITE_EMAIL_ENABLED", "true").lower() == "true"
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@stripe-installer.local")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

if os.environ.get("CHANNEL_LAYER_INMEMORY", "").lower() == "true":
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
