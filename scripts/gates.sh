#!/usr/bin/env bash
# Roda os gates no container `gates` (estágio dev), contra o Postgres do Compose.
# Sai com o código do container: 0 só se tudo passar. Argumentos extras vão para o pytest.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose --profile gates run --rm --build gates bash scripts/gates-container.sh "$@"
