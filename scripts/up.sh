#!/usr/bin/env bash
# Sobe tudo (db, migrate + seed, web, gateway) e espera ficar saudável.
# Porta: CATRACA_PORTA (padrão 8000). Projeto: nome da pasta ou COMPOSE_PROJECT_NAME.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d --build --wait

porta="${CATRACA_PORTA:-8000}"
echo
echo "Catraca no ar."
echo "  WEB=http://localhost:${porta}"
echo "  API=http://localhost:${porta}   (rotas em /api/partner/...)"
echo "  Credenciais de desenvolvimento e chave de parceiro: README.md, seção \"Credenciais\"."
