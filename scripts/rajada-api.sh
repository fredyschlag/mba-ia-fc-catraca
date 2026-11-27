#!/usr/bin/env bash
# Rajada de compras simultâneas pela API de parceiros (R07; F04-CA09).
#
# Uso: ./scripts/rajada-api.sh [rodadas]        (padrão: 5 rodadas)
# Porta: CATRACA_PORTA (padrão 8000). Chave: CATRACA_CHAVE_PARCEIRO (padrão: a do README).
#
# Entra como org.a@catraca.test pelo formulário de login (cookie + CSRF). Em cada rodada, cria
# e publica pela interface um evento novo de lotação 5 e dispara 30 POSTs de compra ao mesmo
# tempo com `xargs -P 30` (o comando do passo 15 do Fluxo do avaliador). A rodada passa só com
# exatamente 30 respostas: 5 × 202 e 25 × 409. Sai com código 0 só se todas as rodadas passarem.
# Usa só bash, curl e utilitários POSIX.
set -uo pipefail

RODADAS=${1:-5}
PORTA=${CATRACA_PORTA:-8000}
WEB=http://localhost:$PORTA
API=$WEB
KEY=${CATRACA_CHAVE_PARCEIRO:-chave-parceiro-dev}
EMAIL_ORGANIZADOR=org.a@catraca.test
SENHA_ORGANIZADOR=catraca123
LOTACAO=5
COMPRAS=30

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
JAR=$TMP/cookies

falhar() {
  echo "$*"
  echo "rajada-api: FALHOU"
  exit 1
}

case "$RODADAS" in
  '' | *[!0-9]* | 0) falhar "uso: $0 [rodadas], com rodadas inteiro maior que zero" ;;
esac

csrf() { awk '$6 == "csrftoken" {print $7}' "$JAR"; }

# postar <caminho> campo=valor ...: GET (para o csrftoken) e POST do formulário com CSRF;
# imprime a linha de status e o Location da resposta do POST.
postar() {
  local caminho=$1
  shift
  curl -s -o /dev/null -b "$JAR" -c "$JAR" "$WEB$caminho" || return 1
  local args=(--data-urlencode "csrfmiddlewaretoken=$(csrf)")
  local kv
  for kv in "$@"; do args+=(--data-urlencode "$kv"); done
  curl -s -o /dev/null -D - -b "$JAR" -c "$JAR" "${args[@]}" "$WEB$caminho" \
    | tr -d '\r' | grep -iE '^(HTTP/|location:)'
}

local_de() { awk 'tolower($1) == "location:" {print $2}'; }

destino=$(postar /contas/entrar/ "email=$EMAIL_ORGANIZADOR" "senha=$SENHA_ORGANIZADOR" | local_de)
[ "$destino" = "/organizador/" ] || falhar "login de $EMAIL_ORGANIZADOR falhou em $WEB"

ANO=$(($(date +%Y) + 1))
CARIMBO=$(date +%s)
falhas=0
for rodada in $(seq "$RODADAS"); do
  destino=$(postar /organizador/eventos/novo/ "nome=Rajada API $CARIMBO-$rodada" \
    "inicio=$ANO-06-15T20:00" "local=Sala da rajada" "lotacao=$LOTACAO" "preco=10,00" | local_de)
  evento=$(echo "$destino" | cut -d/ -f4)
  echo "$evento" | grep -qE '^evt_[a-z0-9]{8}$' || falhar "não consegui criar o evento da rodada $rodada"
  destino=$(postar "/organizador/eventos/$evento/publicar/" | local_de)
  [ "$destino" = "/organizador/eventos/$evento/" ] || falhar "não consegui publicar $evento"

  seq "$COMPRAS" | xargs -P 30 -I{} curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"buyerEmail":"rajada{}@example.com","cardNumber":"4000000000000001"}' \
    "$API/api/partner/events/$evento/purchases" > "$TMP/codigos"
  sort "$TMP/codigos" | uniq -c

  total=$(wc -l < "$TMP/codigos" | tr -d ' ')
  aceitas=$(grep -c '^202$' "$TMP/codigos")
  esgotadas=$(grep -c '^409$' "$TMP/codigos")
  if [ "$total" -eq "$COMPRAS" ] && [ "$aceitas" -eq "$LOTACAO" ] \
    && [ "$esgotadas" -eq $((COMPRAS - LOTACAO)) ]; then
    echo "rodada $rodada ($evento): OK"
  else
    echo "rodada $rodada ($evento): FALHOU ($aceitas × 202, $esgotadas × 409 em $total respostas)"
    falhas=$((falhas + 1))
  fi
done

if [ "$falhas" -eq 0 ]; then
  echo "rajada-api: OK ($RODADAS rodadas)"
  exit 0
fi
echo "rajada-api: FALHOU"
exit 1
