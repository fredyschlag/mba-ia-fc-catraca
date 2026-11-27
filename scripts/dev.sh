#!/usr/bin/env bash
# Roda um comando no container de desenvolvimento (estágio dev), com o código montado e
# arquivos criados com o seu usuário. Exemplos:
#   ./scripts/dev.sh python manage.py makemigrations dominio
#   ./scripts/dev.sh ruff format .
#   ./scripts/dev.sh ruff check --fix .
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose --profile gates run --rm --build --user "$(id -u):$(id -g)" gates "$@"
