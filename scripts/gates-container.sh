#!/usr/bin/env bash
# Executado DENTRO do container `gates`. Não rode no host: use ./scripts/gates.sh.
set -euo pipefail

etapa() { printf '\n==> %s\n' "$*"; }

etapa "ruff check"
ruff check --no-cache .
etapa "ruff format --check"
ruff format --check --no-cache .
etapa "manage.py check"
python manage.py check
etapa "makemigrations --check --dry-run"
python manage.py makemigrations --check --dry-run
etapa "pytest"
pytest "$@"
etapa "gates: OK"
