#!/usr/bin/env bash
# Encerra tudo que up.sh e gates.sh iniciaram neste projeto (inclusive serviços de profile e
# containers de `docker compose run`). Mantém o volume do banco.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose --profile '*' down --remove-orphans

# Rede de segurança: qualquer container restante com o rótulo deste projeto.
projeto="$(docker compose config --format json | sed -n 's/^  "name": "\(.*\)",$/\1/p' | head -n1)"
if [[ -n "${projeto}" ]]; then
  restantes="$(docker ps -aq --filter "label=com.docker.compose.project=${projeto}")"
  if [[ -n "${restantes}" ]]; then
    # shellcheck disable=SC2086
    docker rm -f ${restantes} >/dev/null
  fi
fi
echo "Catraca encerrada (volume do banco mantido)."
