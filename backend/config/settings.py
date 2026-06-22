import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

from config.private_env import load_private_env

load_private_env(REPO_ROOT)

from apps.vault.app_secrets import load_app_secrets_into_environ

load_app_secrets_into_environ(backend_dir=BASE_DIR)

RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
ON_RAILWAY = bool(os.environ.get("RAILWAY_ENVIRONMENT") or RAILWAY_PUBLIC_DOMAIN)


def _public_app_url() -> str:
    for key in ("APP_PUBLIC_URL", "SAAS_BILLING_RETURN_URL"):
        val = os.environ.get(key, "").strip().rstrip("/")
        if val:
            return val
    if RAILWAY_PUBLIC_DOMAIN:
        return f"https://{RAILWAY_PUBLIC_DOMAIN}".rstrip("/")
    return "http://localhost:5173"


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if "railway" in url and "sslmode=" not in url:
        url += "&sslmode=require" if "?" in url else "?sslmode=require"
    return url


if os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = _normalize_database_url(os.environ["DATABASE_URL"])

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
    "apps.stripe_installer",
    "apps.diagnostics",
    "apps.runs",
    "apps.billing",
    "apps.deploy",
    "apps.api_transfer",
    "apps.ai_assistant",
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
    db = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": url.path[1:],
        "USER": url.username,
        "PASSWORD": url.password,
        "HOST": url.hostname,
        "PORT": url.port or 5432,
    }
    qs = urlparse.parse_qs(url.query)
    sslmode = (qs.get("sslmode") or [None])[0]
    if sslmode or "railway" in (url.hostname or ""):
        db["OPTIONS"] = {"sslmode": sslmode or "require"}
    DATABASES["default"] = db

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
if RAILWAY_PUBLIC_DOMAIN:
    _co = f"https://{RAILWAY_PUBLIC_DOMAIN}"
    if _co not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_co)
for _co in (_public_app_url(),):
    if _co.startswith("http") and _co not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_co)
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
}

# Vault master key: local dev persists in ~/.stripe-installer/vault-master-key.
# Railway: set VAULT_MASTER_KEY in Variables (64-char hex) — env wins over ephemeral disk.
from apps.vault.master_key import resolve_vault_master_key

VAULT_MASTER_KEY = resolve_vault_master_key()

# Optional path to legacy Node CLI (legacy/node/dist/cli.js) — Python codegen works without this
STRIPE_INSTALLER_CLI = os.environ.get("STRIPE_INSTALLER_CLI", "")

# Platform billing (Stripe Installer SaaS — dogfood our own integration)
# Pricing: $79/mo flat rate per customer (7900 cents)
SAAS_STRIPE_SECRET_KEY = os.environ.get("SAAS_STRIPE_SECRET_KEY", "")
SAAS_STRIPE_WEBHOOK_SECRET = os.environ.get("SAAS_STRIPE_WEBHOOK_SECRET", "")
SAAS_STRIPE_PRICE_STARTER = os.environ.get("SAAS_STRIPE_PRICE_STARTER", "")
SAAS_STRIPE_PRICE_PRO = os.environ.get("SAAS_STRIPE_PRICE_PRO", "")
SAAS_STRIPE_PRICE_ENTERPRISE = os.environ.get("SAAS_STRIPE_PRICE_ENTERPRISE", "")
SAAS_BILLING_RETURN_URL = os.environ.get("SAAS_BILLING_RETURN_URL") or _public_app_url()

# Public app URL (invites, billing return, license validation server default)
APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL") or _public_app_url()

# License enforcement settings
LICENSE_ENFORCEMENT_ENABLED = os.environ.get("LICENSE_ENFORCEMENT_ENABLED", "false").lower() == "true"
LICENSE_ENFORCEMENT_MODE = os.environ.get("LICENSE_ENFORCEMENT_MODE", "readonly")
LICENSE_READ_ONLY_MESSAGE = os.environ.get("LICENSE_READ_ONLY_MESSAGE", "License invalid - running in read-only mode")
LICENSE_VALIDATION_SERVER = os.environ.get("STRIPE_INSTALLER_VALIDATION_SERVER", "")
LICENSE_EMAIL_ENABLED = os.environ.get("LICENSE_EMAIL_ENABLED", "true").lower() == "true"

if LICENSE_ENFORCEMENT_ENABLED:
    MIDDLEWARE.append("apps.licenses.middleware.LicenseEnforcementMiddleware")

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


def _is_local_redis(url: str) -> bool:
    return "127.0.0.1" in url or "localhost" in url


# Pasted dev .env often sets REDIS_URL=127.0.0.1 — treat as no Redis on Railway.
RAILWAY_SINGLE_CONTAINER = ON_RAILWAY and (
    not os.environ.get("REDIS_URL") or _is_local_redis(REDIS_URL)
)

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_EAGER", "").lower() == "true"

if RAILWAY_SINGLE_CONTAINER:
    # Single-service Railway deploy: no Redis addon required for the web process
    CELERY_TASK_ALWAYS_EAGER = True

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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API_BASE_URL = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")

# API Transfer provider credentials (private_env/*.env or Railway env)
FLY_API_TOKEN = os.environ.get("FLY_API_TOKEN", "")
FLY_API_BASE_URL = os.environ.get("FLY_API_BASE_URL", "https://api.machines.dev")
FLY_ORG_SLUG = os.environ.get("FLY_ORG_SLUG", "personal")

RENDER_API_TOKEN = os.environ.get("RENDER_API_TOKEN", "")
RENDER_API_BASE_URL = os.environ.get("RENDER_API_BASE_URL", "https://api.render.com")
RENDER_OWNER_ID = os.environ.get("RENDER_OWNER_ID", "")
RENDER_DEFAULT_REGION = os.environ.get("RENDER_DEFAULT_REGION", "oregon")
RENDER_DEFAULT_PLAN = os.environ.get("RENDER_DEFAULT_PLAN", "starter")

RAILWAY_API_TOKEN = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_API_BASE_URL = os.environ.get("RAILWAY_API_BASE_URL", "https://backboard.railway.app")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID", "")
RAILWAY_ENVIRONMENT_ID = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")

SUPABASE_ACCESS_TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
SUPABASE_ORG_ID = os.environ.get("SUPABASE_ORG_ID", "")
SUPABASE_DEFAULT_REGION = os.environ.get("SUPABASE_DEFAULT_REGION", "us-east-1")

CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ZONE_ID = os.environ.get("CLOUDFLARE_ZONE_ID", "")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "") or os.environ.get("SAAS_STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "") or os.environ.get("SAAS_STRIPE_WEBHOOK_SECRET", "")

ORENA_API_TOKEN = os.environ.get("ORENA_API_TOKEN", "")
ORENA_API_BASE_URL = os.environ.get("ORENA_API_BASE_URL", "https://api.orena.cloud")
ORENA_PROJECT_ID = os.environ.get("ORENA_PROJECT_ID", "")
ORENA_DEFAULT_REGION = os.environ.get("ORENA_DEFAULT_REGION", "nairobi")

TRANSFER_WORKER_LIMIT = int(os.environ.get("TRANSFER_WORKER_LIMIT", "5"))
TRANSFER_WORKER_POLL_INTERVAL_SECONDS = int(os.environ.get("TRANSFER_WORKER_POLL_INTERVAL_SECONDS", "5"))
TRANSFER_WORKER_LEASE_TTL_SECONDS = int(os.environ.get("TRANSFER_WORKER_LEASE_TTL_SECONDS", "120"))
TRANSFER_ORG_CONCURRENCY_CAP = int(os.environ.get("TRANSFER_ORG_CONCURRENCY_CAP", "1"))
TRANSFER_QUEUE_AGING_WINDOW_SECONDS = int(os.environ.get("TRANSFER_QUEUE_AGING_WINDOW_SECONDS", "300"))
TRANSFER_QUEUE_MAX_AGING_BOOST = int(os.environ.get("TRANSFER_QUEUE_MAX_AGING_BOOST", "10"))


# Org billing free tier (when SAAS_STRIPE_* is configured)
ORG_FREE_MEMBER_LIMIT = os.environ.get("ORG_FREE_MEMBER_LIMIT", "3")
ORG_FREE_PROJECT_LIMIT = os.environ.get("ORG_FREE_PROJECT_LIMIT", "5")

# Public app URL (invites, billing return). Set APP_PUBLIC_URL or SAAS_BILLING_RETURN_URL in production.
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
elif RAILWAY_SINGLE_CONTAINER:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }

if ON_RAILWAY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
