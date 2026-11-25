from datetime import timedelta
from pathlib import Path

import os
import dj_database_url
from corsheaders.defaults import default_headers
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Env:
    __call__ = staticmethod(os.getenv)

    @staticmethod
    def bool(key, default=False):
        return os.getenv(key, str(default)).lower() in {"true","1","yes"}

    @staticmethod
    def list(key, default=None):
        value = os.getenv(key)
        return default if value is None else [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def int(key, default):
        return int(os.getenv(key, default))

env = Env()
DEBUG = env.bool("DEBUG", default=False)
SECRET_KEY = env("SECRET_KEY", default="local-development-key-only-change-before-deployment")
if not DEBUG and SECRET_KEY.startswith("local-development"):
    raise ImproperlyConfigured("Set a production SECRET_KEY or enable DEBUG for local use.")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
render_hostname = env("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
CORS_ALLOW_HEADERS = (*default_headers, "x-flat-id")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
TIME_ZONE = env("TIME_ZONE", default="Asia/Kolkata")
USE_TZ = True
LANGUAGE_CODE = "en-in"
ROOT_URLCONF = "core.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "corsheaders", "rest_framework", "rest_framework_simplejwt.token_blacklist", "core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request",
                 "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
DATABASES = {"default": dj_database_url.parse(os.getenv("DATABASE_URL", "sqlite:///db.sqlite3"))}
if not os.getenv("DATABASE_URL"):
    DATABASES["default"]["NAME"] = BASE_DIR / "db.sqlite3"
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    DATABASES["default"]["OPTIONS"] = {"timeout": 20, "transaction_mode": "IMMEDIATE"}
    DATABASES["default"]["TEST"] = {"NAME": BASE_DIR / "test_broshare.sqlite3"}
AUTH_PASSWORD_VALIDATORS = [{"NAME": f"django.contrib.auth.password_validation.{name}"} for name in (
    "UserAttributeSimilarityValidator", "MinimumLengthValidator", "CommonPasswordValidator", "NumericPasswordValidator")]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {"auth": "20/min"},
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_TOKEN_LIFETIME", default=7)),
    "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True,
}
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
if env.bool("TRUST_HTTPS_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DEMO_ENABLED = env.bool("DEMO_ENABLED", default=False)


