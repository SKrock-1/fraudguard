import os
import sys
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-fraudguard-dev-secret-key-change-in-production")

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# Any host in development; in production only what is configured (plus Render's hostname below)
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "*" if DEBUG else "").split(",") if host.strip()]

if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("Set a real SECRET_KEY when DEBUG is off.")

# Render (and most PaaS) terminate TLS at a proxy and forward X-Forwarded-Proto
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]

# Render sets RENDER_EXTERNAL_HOSTNAME (e.g. fraudguard.onrender.com) on every web service
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if "*" not in ALLOWED_HOSTS:
    # In-container probes (Docker HEALTHCHECK) and the platform's internal hostname
    for host in ("127.0.0.1", "localhost", RENDER_EXTERNAL_HOSTNAME, os.getenv("RENDER_INTERNAL_HOSTNAME", "").strip()):
        if host and host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)
if RENDER_EXTERNAL_HOSTNAME:
    if f"https://{RENDER_EXTERNAL_HOSTNAME}" not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() in ("true", "1", "yes")
    # The platform's health probe talks plain HTTP to the container
    SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Short by default: raise it once HTTPS is confirmed working end to end
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
    # Shared platform domains (*.onrender.com) must not claim subdomains or preload
    SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

INSTALLED_APPS = [
    *(["daphne"] if "pytest" not in sys.modules and "test" not in sys.argv else []),
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "accounts.apps.AccountsConfig",
    "transactions.apps.TransactionsConfig",
    "risk.apps.RiskConfig",
    "alerts.apps.AlertsConfig",
    "audit.apps.AuditConfig",
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

ROOT_URLCONF = "fraudguard.urls"

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

WSGI_APPLICATION = "fraudguard.wsgi.application"
ASGI_APPLICATION = "fraudguard.asgi.application"

# Database configuration
# Neon provides two URLs for the same database: DATABASE_URL (pooled, PgBouncer in
# transaction mode) for application traffic, and DATABASE_URL_UNPOOLED (direct) for
# schema migrations and other session-level work. Django has one connection setting,
# so management commands that change schema or need a session use the direct URL.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE_URL_UNPOOLED = os.getenv("DATABASE_URL_UNPOOLED", "").strip()
_DIRECT_DB_COMMANDS = {"migrate", "makemigrations", "sqlmigrate", "showmigrations", "dbshell", "flush", "test"}
_wants_direct_db = (
    (len(sys.argv) > 1 and sys.argv[1] in _DIRECT_DB_COMMANDS)
    or "pytest" in sys.modules
    or os.getenv("DB_USE_DIRECT", "").lower() in ("true", "1", "yes")
)
if DATABASE_URL_UNPOOLED and _wants_direct_db:
    DATABASE_URL = DATABASE_URL_UNPOOLED

if DATABASE_URL:
    import urllib.parse
    parsed = urllib.parse.urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": urllib.parse.unquote(parsed.path.lstrip("/")),
            "USER": urllib.parse.unquote(parsed.username or ""),
            "PASSWORD": urllib.parse.unquote(parsed.password or ""),
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
            # Pass query params (e.g. Neon's ?sslmode=require) through to libpq
            "OPTIONS": dict(urllib.parse.parse_qsl(parsed.query)),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
            "CONN_HEALTH_CHECKS": True,
            # Neon's pooled endpoint (host "...-pooler...") is PgBouncer in transaction
            # mode, where server-side cursors (used by QuerySet.iterator()) don't survive
            # between statements. Disable them there; override with DB_SERVER_SIDE_CURSORS.
            "DISABLE_SERVER_SIDE_CURSORS": os.getenv(
                "DB_SERVER_SIDE_CURSORS", "false" if "-pooler" in (parsed.hostname or "") else "true"
            ).lower() not in ("true", "1", "yes"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "ingestion": os.getenv("INGESTION_THROTTLE_RATE", "100/minute"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "accounts.serializers.FraudGuardTokenObtainPairSerializer",
}

# Redis URL (used by risk/redis_client.py and Celery)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery configuration
if REDIS_URL.startswith("fakeredis://"):
    # No Redis server (local dev): Celery's in-memory transport, eager tasks only
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
else:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "True").lower() in ("true", "1", "yes")
CELERY_TASK_EAGER_PROPAGATES = True

# Upstash (and other managed Redis) only accepts TLS, via rediss:// URLs.
# Celery refuses a rediss:// broker unless SSL options are given explicitly.
if REDIS_URL.startswith("rediss://") and "ssl_cert_reqs" not in REDIS_URL:
    import ssl
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED}

# Synthetic live-traffic button on the dashboard (POST /api/demo/simulate/)
DEMO_TOOLS_ENABLED = (os.getenv("DEMO_TOOLS_ENABLED") or str(DEBUG)).lower() in ("true", "1", "yes")

# Risk scoring threshold for alert creation (used in Phase 5)
RISK_SCORE_ALERT_THRESHOLD = float(os.getenv("RISK_SCORE_ALERT_THRESHOLD", "0.6"))

# ML Anomaly Detection Model
ML_MODEL_PATH = os.getenv("ML_MODEL_PATH", str(BASE_DIR / "risk" / "ml_models" / "isolation_forest.joblib"))

# ASGI & Channels
ASGI_APPLICATION = "fraudguard.asgi.application"

# Channel Layers
# Use InMemoryChannelLayer for tests/eager mode or when explicitly set;
# RedisChannelLayer for production / live services.
_use_inmemory_channels = (
    os.getenv("CHANNEL_LAYERS_BACKEND", "").lower() == "inmemory"
    or "pytest" in sys.modules
    or "test" in sys.argv
)

if _use_inmemory_channels:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }
