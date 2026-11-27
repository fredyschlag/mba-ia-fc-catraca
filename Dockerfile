# Estágios:
#   base    — Python + uv (usado também por scripts/lock.sh para gerar o uv.lock)
#   runtime — dependências de produção (uv sync --frozen --no-dev); serviços migrar, web e gateway
#   dev     — runtime + dependências de teste (pytest, pytest-django, ruff); serviço gates

FROM ghcr.io/astral-sh/uv:0.13.10 AS uv

FROM python:3.13.16-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/tmp/uv-cache \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app

FROM base AS runtime
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN useradd --create-home --uid 1000 app
USER app
EXPOSE 8000
CMD ["gunicorn", "catraca.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM runtime AS dev
USER root
RUN uv sync --frozen
USER app
