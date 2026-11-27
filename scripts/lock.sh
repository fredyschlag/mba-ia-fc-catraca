#!/usr/bin/env bash
# Gera ou atualiza o uv.lock dentro de container (sem Python nem uv no host).
# Uso: ./scripts/lock.sh            -> uv lock
#      ./scripts/lock.sh --upgrade  -> argumentos extras vão para o uv lock
set -euo pipefail
cd "$(dirname "$0")/.."

imagem="catraca-uv-base:local"
docker build --quiet --target base --tag "$imagem" . >/dev/null
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD:/app" \
  --workdir /app \
  "$imagem" uv lock "$@"
