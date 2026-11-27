"""Configuração do Django para a Catraca.

Todos os valores vêm de variáveis de ambiente. Os valores de desenvolvimento ficam no
compose.yaml (não há .env). DEBUG fica desligado no modo padrão.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "dominio",
    "web",
    "api_parceiros",
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

ROOT_URLCONF = "catraca.urls"

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

WSGI_APPLICATION = "catraca.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "NAME": os.environ.get("POSTGRES_DB", "catraca"),
        "USER": os.environ.get("POSTGRES_USER", "catraca"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        # Conexão por requisição: com gunicorn workers × threads, cada thread usa no
        # máximo uma conexão e a devolve ao fim da requisição.
        "CONN_MAX_AGE": 0,
    }
}

AUTH_USER_MODEL = "dominio.Usuario"

# Contas e acesso (F01): login próprio em /contas/entrar/; falha de CSRF com a página 403.
LOGIN_URL = "/contas/entrar/"
CSRF_FAILURE_VIEW = "web.views.falha_csrf"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Chave da API de parceiros (consumida pela F04). Valor de desenvolvimento no compose.yaml.
CATRACA_CHAVE_PARCEIRO = os.environ.get("CATRACA_CHAVE_PARCEIRO", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simples": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simples"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
