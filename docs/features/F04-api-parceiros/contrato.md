# Contrato — F04 API de parceiros

> O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item, na ordem. Textos esperados vão entre aspas ou em blocos de código, exatos, e são conferidos com `grep -F` (`grep -c` conta **linhas** que contêm o texto). As respostas da API são JSON compacto (sem espaços), com as chaves na ordem do brief, então o corpo inteiro é comparado como texto.

- Feature: F04 — API de parceiros (wave W4)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (F04-CA01…CA10) e 7 (XF-05, XF-06)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- **Antes de tudo**, na raiz do repositório (ou da worktree): `git rev-parse HEAD` precisa imprimir exatamente o sha completo pedido para a avaliação, e `git status --porcelain` precisa sair vazio. Se um dos dois não bater, o avaliador **para**, registra no relatório as duas saídas e não avalia nenhum item.
- Commit avaliado: o sha informado no pedido de avaliação (branch `feat/F04-api-parceiros`).
- Ferramentas no host: Docker, Git, `curl`, **bash** e os utilitários `awk`, `sed`, `grep`, `cut`, `sort`, `uniq`, `xargs`, `seq`, `tr`, `head`, `wc`, `mktemp`, `date` (`date +%s`) e `sleep`. Sem `jq` e sem Python no host. Navegador é opcional.
- Contas da seed (README, "Credenciais"): `org.a@catraca.test` e `participante@catraca.test`, com a senha `catraca123`. Chave de parceiro (README, "Credenciais"): `chave-parceiro-dev`.
- **Tempo.** O C-08 espera os cartões lentos (cerca de 45 s) e o C-11 faz 7 rajadas. A execução completa leva uns 3 minutos, sem contar os gates. Os itens que conferem "pendente" logo depois de uma compra usam a resposta ou uma consulta feita imediatamente depois dela, e os prazos do gateway ("em até 5 s", "entre 30 e 40 s") são medidos no banco pela diferença entre a criação do ingresso e o processamento da cobrança.
- **Simulações.** Cancelamento (F07) e check-in (F05) ainda não existem nesta branch; o C-06 e o C-09 simulam os dois com um `update` direto no banco, marcado com comentário.
- **Porta.** Vem de `CATRACA_PORTA` (padrão 8000) e é a mesma na subida, nos itens, no `scripts/rajada-api.sh` e na descida.
- **Banco zerado**, na raiz:

```bash
PORTA=${CATRACA_PORTA:-8000}
docker compose --profile '*' down -v          # apaga só o volume deste projeto
CATRACA_PORTA=$PORTA ./scripts/up.sh          # código 0 e "Catraca no ar."
```

O banco começa sem eventos e sem ingressos.

- **Funções e estado.** Rode uma vez o bloco abaixo, em bash. Ele grava as funções em `$D/f.sh` e as variáveis criadas pelos itens (ids e códigos) em `$D/ids`. Os itens rodam **na ordem**; contagens e variáveis dependem dela. Se um item for rodado num **shell novo**, antes dele rode: `PORTA=${CATRACA_PORTA:-8000}; D=/tmp/catraca-F04-$PORTA; . $D/f.sh; . $D/ids`.

```bash
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F04-$PORTA; rm -rf "$D"; mkdir -p "$D"; : > "$D/ids"
cat > "$D/f.sh" <<'FIM'
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F04-$PORTA
export WEB=http://localhost:$PORTA
KEY=chave-parceiro-dev
sql()       { docker compose exec -T db psql -U catraca -d catraca -tAc "$1"; }
ingressos() { sql "select count(*) from dominio_ingresso"; }
cobrancas() { sql "select count(*) from dominio_cobrancagateway"; }
csrf()      { awk '$6 == "csrftoken" {print $7}' "$1"; }
corpo()     { curl -s -b "$1" -c "$1" "$WEB$2"; }
postar()    { local jar=$1 caminho=$2; shift 2
              curl -s -o /dev/null -b "$jar" -c "$jar" "$WEB$caminho"
              local args=(--data-urlencode "csrfmiddlewaretoken=$(csrf "$jar")")
              for kv in "$@"; do args+=(--data-urlencode "$kv"); done
              curl -s -o "$jar.html" -D - -b "$jar" -c "$jar" "${args[@]}" "$WEB$caminho" \
                | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
entrar()    { postar "$1" /contas/entrar/ "email=$2" "senha=catraca123"; }
idde()      { awk 'tolower($1) == "location:" {print $2}' | cut -d/ -f4; }
guardar()   { echo "$1=$2" >> "$D/ids"; }
# novo_evento <cookies do organizador> <nome> <início> <lotação> <preço>: cria, publica e imprime o id
novo_evento() { local id
              id=$(postar "$1" /organizador/eventos/novo/ "nome=$2" "inicio=$3" "local=Sala" "lotacao=$4" "preco=$5" | idde)
              postar "$1" /organizador/eventos/$id/publicar/ >/dev/null; echo "$id"; }
# comprar <cookies> <evento> <cartão>: compra na vitrine (POST com CSRF); imprime status, Location e tempo
comprar()   { curl -s -o /dev/null -b "$1" -c "$1" "$WEB/contas/entrar/"
              curl -s -o "$1.html" -D - -w 'tempo=%{time_total}\n' -b "$1" -c "$1" \
                --data-urlencode "csrfmiddlewaretoken=$(csrf "$1")" --data-urlencode "cartao=$3" \
                "$WEB/eventos/$2/comprar/" | tr -d '\r' | grep -iE '^(HTTP/|location:|tempo=)'; }
vagas()     { corpo "$1" "/eventos/$2/" | grep -oE 'data-campo="vagas-disponiveis">[0-9]+<'; }
# req <chave, ou - para não mandar o cabeçalho> <método> <caminho> [corpo JSON]
# imprime "<status HTTP> <corpo>"; cabeçalhos em $D/h, corpo em $D/b, tempo total (s) em $D/t
req()       { local chave=$1 metodo=$2 caminho=$3 saida
              local args=(-s -o "$D/b" -D "$D/h" -w '%{http_code} %{time_total}' -X "$metodo")
              if [ "$chave" != "-" ]; then args+=(-H "X-Api-Key: $chave"); fi
              if [ $# -ge 4 ]; then args+=(-H "Content-Type: application/json" --data-binary "$4"); fi
              saida=$(curl "${args[@]}" "$WEB$caminho")
              echo "${saida#* }" > "$D/t"; echo "${saida%% *} $(cat "$D/b")"; }
api()       { req "$KEY" "$@"; }
# cabeçalhos Content-Type e Set-Cookie da última resposta da API
cabecalhos(){ tr -d '\r' < "$D/h" | grep -iE '^(content-type|set-cookie):'; }
# valor de um campo do último corpo de objeto da API (string, número ou booleano)
campo()     { sed -nE "s/.*\"$1\":\"?([^\",}]*)\"?.*/\1/p" "$D/b"; }
# objeto do evento na listagem da API e o availableSeats dele
objeto()    { api GET /api/partner/events >/dev/null; grep -oE "\{[^{}]*\"id\":\"$1\"[^{}]*\}" "$D/b"; }
assentos()  { objeto "$1" | grep -oE '"availableSeats":[0-9]+'; }
situacao()  { api GET "/api/partner/tickets/$1" | grep -oE '"status":"[a-z]+"'; }
# tempo entre a compra e o processamento da cobrança, conferido no banco: imprime status|t ou status|f
prazo()     { sql "select i.status, (c.processada_em - i.criado_em) $2 from dominio_ingresso i join dominio_cobrancagateway c on c.ingresso_id = i.id where i.id_publico = '$1'"; }
FIM
. "$D/f.sh"
```

"Status 302 e `location: /x`" quer dizer: a linha `HTTP/1.1 302 …` e o cabeçalho `Location` com o valor exato `/x`. `<E1>`, `<T1>`, `<K1>` etc. nos resultados esperados são os valores impressos (ou guardados em `$D/ids`) no item que os criou. "Linha de compra 202" quer dizer uma linha que casa com a expressão `^202 \{"ticketId":"tkt_[a-z0-9]{8}","code":"[A-Z0-9]{8}","status":"pending"\}$`.

## 2. Itens verificáveis

### C-01 — Gates

```bash
./scripts/gates.sh; echo "código: $?"
```

Esperado: "código: 0", pytest sem falhas, última etapa "==> gates: OK".

### C-02 — (XF-05, F04-CA01, R02) Rascunho fora da API; publicado aparece com o id da gestão

```bash
api GET /api/partner/events
cabecalhos
entrar $D/a org.a@catraca.test
R=$(postar $D/a /organizador/eventos/novo/ "nome=Jazz no Porão" "inicio=2027-06-15T21:00" "local=Bar do Porão" "lotacao=2" "preco=100,00"); echo "$R"
E1=$(echo "$R" | idde); guardar E1 "$E1"; echo "$E1"
api GET /api/partner/events
postar $D/a /organizador/eventos/$E1/publicar/
api GET /api/partner/events
```

Esperado, linha a linha:
- `200 []`;
- uma única linha, `Content-Type: application/json` (nenhum `Set-Cookie`);
- login de A: status 302 e `location: /organizador/`;
- criação: status 302 e `location: /organizador/eventos/<E1>/`; o id `<E1>` (`evt_` + 8 caracteres);
- com E1 em rascunho: `200 []`;
- publicar: status 302 e `location: /organizador/eventos/<E1>/`;
- exatamente:

```
200 [{"id":"<E1>","name":"Jazz no Porão","startsAt":"2027-06-15T21:00:00-03:00","priceCents":10000,"availableSeats":2}]
```

### C-03 — (F04-CA03) Sem chave ou com chave errada: 401 antes de tudo, nas três rotas

```bash
for chave in - errada chave-parceiro-dev2; do
  req "$chave" GET /api/partner/events
  req "$chave" POST /api/partner/events/$E1/purchases '{"buyerEmail":"ana@example.com","cardNumber":"4000000000000001"}'
  req "$chave" POST /api/partner/events/evt_zzzzzzzz/purchases 'isto não é json'
  req "$chave" GET /api/partner/tickets/tkt_naoexiste
done
cabecalhos
echo "$(ingressos)/$(cobrancas)"
```

Esperado: exatamente 12 linhas, todas `401 {"error":"unauthorized"}` (sem cabeçalho, com uma chave qualquer e com a chave certa seguida de um caractere; na listagem, na compra válida de um evento à venda, na compra com corpo inválido de evento inexistente e na consulta de ingresso inexistente); uma única linha `Content-Type: application/json`; `0/0` (nada foi criado).

### C-04 — (F04-CA02, F04-CA07, XF-06, R06, R08) Compra pela API com final 0001: pendente na hora, confirmada em até 5 s

```bash
api POST /api/partner/events/$E1/purchases '{"buyerEmail":"Ana@Example.com","cardNumber":"4000000000000001"}' > $D/c1
cat $D/c1; grep -cE '^202 \{"ticketId":"tkt_[a-z0-9]{8}","code":"[A-Z0-9]{8}","status":"pending"\}$' $D/c1; cat $D/t
cabecalhos
T1=$(campo ticketId); K1=$(campo code); guardar T1 "$T1"; guardar K1 "$K1"; echo "$T1 $K1"
api GET /api/partner/tickets/$T1
api GET /api/partner/events
sql "select canal, comprador_id is null, email_comprador, valor_centavos, cartao_final from dominio_ingresso where id_publico = '$T1'"
sleep 5
api GET /api/partner/tickets/$T1
prazo "$T1" "<= interval '5 seconds'"
```

Esperado:
- uma linha de compra 202; `1`; um número **menor que 1** (o tempo da resposta, que não espera o gateway);
- uma única linha `Content-Type: application/json`;
- o id `<T1>` (`tkt_…`) e o código `<K1>` (8 caracteres de `[A-Z0-9]`);
- logo depois da compra, exatamente `200 {"ticketId":"<T1>","code":"<K1>","eventId":"<E1>","status":"pending","checkedIn":false}`;
- exatamente `200 [{"id":"<E1>","name":"Jazz no Porão","startsAt":"2027-06-15T21:00:00-03:00","priceCents":10000,"availableSeats":1}]` (a compra pendente já ocupa a vaga);
- `api|t|ana@example.com|10000|0001` (canal API, sem comprador, e-mail informado, preço vigente, só o final do cartão);
- depois dos 5 s: exatamente `200 {"ticketId":"<T1>","code":"<K1>","eventId":"<E1>","status":"confirmed","checkedIn":false}`; `confirmed|t` (processado em até 5 s depois da compra).

### C-05 — (F04-CA04) Corpo inválido: 422 sem criar nada, inclusive com evento inexistente ou em rascunho

```bash
E2=$(postar $D/a /organizador/eventos/novo/ "nome=Rascunho API" "inicio=2027-06-16T21:00" "local=Sala" "lotacao=5" "preco=50,00" | idde); guardar E2 "$E2"; echo "$E2"
echo "$(ingressos)/$(cobrancas)"
for corpo in 'isto não é json' '' '[]' '"texto"' '{}' \
  '{"cardNumber":"4000000000000001"}' \
  '{"buyerEmail":"ana@example.com"}' \
  '{"buyerEmail":"ana@example.com","cardNumber":4000000000000001}' \
  '{"buyerEmail":123,"cardNumber":"4000000000000001"}' \
  '{"buyerEmail":"ana-sem-arroba","cardNumber":"4000000000000001"}' \
  '{"buyerEmail":"ana@example.com","cardNumber":"123"}' \
  '{"buyerEmail":"ana@example.com","cardNumber":"400000000000000A"}' \
  '{"buyerEmail":"ana@example.com","cardNumber":"40000000000000011"}'; do
  api POST /api/partner/events/$E1/purchases "$corpo"
done
for e in evt_zzzzzzzz "$E2"; do
  api POST /api/partner/events/$e/purchases '{"buyerEmail":"ana@example.com","cardNumber":"123"}'
  api POST /api/partner/events/$e/purchases '{"buyerEmail":"ana@","cardNumber":"4000000000000001"}'
  api POST /api/partner/events/$e/purchases 'nada'
done
echo "$(ingressos)/$(cobrancas)"
```

Esperado: o id `<E2>`; `1/1`; exatamente 13 linhas `422 {"error":"invalid_request"}` (não é JSON, vazio, array, string, objeto vazio, sem `buyerEmail`, sem `cardNumber`, `cardNumber` número, `buyerEmail` número, e-mail mal formado, cartão `123`, cartão com letra, cartão com 17 dígitos), num evento que ainda tem vaga; exatamente 6 linhas `422 {"error":"invalid_request"}` (evento inexistente e evento em rascunho, com corpo inválido: 422 antes de 404); `1/1` (nada foi criado).

### C-06 — (F04-CA05, F04-CA06, F04-CA01, R02) Evento indisponível: 404, inclusive cancelado lotado (404, não 409); fora da listagem

```bash
E3=$(novo_evento $D/a "Cancelado API" "2027-06-17T21:00" 1 "30,00"); guardar E3 "$E3"; echo "$E3"
api POST /api/partner/events/$E3/purchases '{"buyerEmail":"bia@example.com","cardNumber":"4000000000000001"}' | cut -c1-3
api POST /api/partner/events/$E3/purchases '{"buyerEmail":"bia@example.com","cardNumber":"4000000000000001"}'
sql "update dominio_evento set status = 'cancelado' where id_publico = '$E3'"   # simula o cancelamento (F07)
echo "$(ingressos)/$(cobrancas)"
for e in evt_zzzzzzzz "$E2" "$E3"; do
  api POST /api/partner/events/$e/purchases '{"buyerEmail":"bia@example.com","cardNumber":"4000000000000001"}'
done
echo "$(ingressos)/$(cobrancas)"
api GET /api/partner/events | grep -oE '"id":"evt_[a-z0-9]{8}"'
```

Esperado: o id `<E3>`; `202`; `409 {"error":"sold_out"}` (lotado enquanto publicado); `UPDATE 1`; `2/2`; exatamente 3 linhas `404 {"error":"event_not_available"}` (inexistente, rascunho e cancelado lotado: 404, não 409); `2/2` (nada foi criado); uma única linha, `"id":"<E1>"` (rascunho e cancelado ficam fora da listagem).

### C-07 — (F04-CA06, F04-CA07, XF-06, R07) API e vitrine dividem a lotação; ingresso da vitrine consultável na API

```bash
E4=$(novo_evento $D/a "Última Vaga API" "2027-06-18T21:00" 1 "40,00"); guardar E4 "$E4"
E5=$(novo_evento $D/a "Última Vaga Vitrine" "2027-06-18T22:00" 1 "40,00"); guardar E5 "$E5"; echo "$E4 $E5"
entrar $D/p participante@catraca.test
vagas $D/p "$E4"
api POST /api/partner/events/$E4/purchases '{"buyerEmail":"caio@example.com","cardNumber":"4000000000000001"}' | cut -c1-3
corpo $D/p /eventos/$E4/ > $D/e4.html
grep -oE 'data-campo="vagas-disponiveis">[0-9]+<' $D/e4.html; grep -cF '<p id="esgotado">Ingressos esgotados</p>' $D/e4.html; grep -c 'id="form-compra"' $D/e4.html
api POST /api/partner/events/$E4/purchases '{"buyerEmail":"caio@example.com","cardNumber":"4000000000000001"}'
comprar $D/p "$E5" 4000000000000001
corpo $D/p /meus-ingressos/ > $D/mi.html
TV=$(grep -oE 'data-ingresso="tkt_[a-z0-9]{8}"' $D/mi.html | head -n 1 | cut -d'"' -f2); guardar TV "$TV"
KV=$(grep -F "data-ingresso=\"$TV\"" $D/mi.html | grep -oE 'data-campo="codigo">[A-Z0-9]{8}<' | cut -d'>' -f2 | tr -d '<'); guardar KV "$KV"; echo "$TV $KV"
objeto "$E5"
api POST /api/partner/events/$E5/purchases '{"buyerEmail":"caio@example.com","cardNumber":"4000000000000001"}'
sleep 5
api GET /api/partner/tickets/$TV
sql "select count(*) from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico in ('$E4', '$E5')"
```

Esperado:
- os dois ids; login do participante: status 302 e `location: /`; `data-campo="vagas-disponiveis">1<`;
- `202` (a API ocupou a última vaga do E4);
- na vitrine do E4: `data-campo="vagas-disponiveis">0<`; `1` ("Ingressos esgotados" no lugar da compra); `0` (sem formulário);
- `409 {"error":"sold_out"}`;
- compra na vitrine do E5: status 302, `location: /meus-ingressos/` e uma linha `tempo=…`;
- o id `<TV>` (`tkt_…`) e o código `<KV>` mostrados em Meus ingressos;
- exatamente `{"id":"<E5>","name":"Última Vaga Vitrine","startsAt":"2027-06-18T22:00:00-03:00","priceCents":4000,"availableSeats":0}`;
- `409 {"error":"sold_out"}` (a vitrine ocupou a última vaga do E5);
- depois dos 5 s: exatamente `200 {"ticketId":"<TV>","code":"<KV>","eventId":"<E5>","status":"confirmed","checkedIn":false}` (o mesmo código de Meus ingressos);
- `2` (um ingresso em cada evento; as recusas 409 não criaram nada).

### C-08 — (XF-06, F04-CA07, F04-CA06, R05, R08) Cartões lentos pela API: 0004 pendente aos 30 s ocupando a vaga, recusado antes de 45 s devolvendo a vaga

```bash
E6=$(novo_evento $D/a "Lento API Recusado" "2027-06-19T21:00" 1 "20,00"); guardar E6 "$E6"
E7=$(novo_evento $D/a "Lento API Aprovado" "2027-06-19T22:00" 1 "20,00"); guardar E7 "$E7"; echo "$E6 $E7"
T0=$(date +%s)
api POST /api/partner/events/$E6/purchases '{"buyerEmail":"duda@example.com","cardNumber":"4000000000000004"}' | cut -c1-3; T4=$(campo ticketId); guardar T4 "$T4"
api POST /api/partner/events/$E7/purchases '{"buyerEmail":"duda@example.com","cardNumber":"4000000000000003"}' | cut -c1-3; T3=$(campo ticketId); guardar T3 "$T3"
assentos "$E6"; assentos "$E7"
api POST /api/partner/events/$E6/purchases '{"buyerEmail":"duda@example.com","cardNumber":"4000000000000001"}'
sleep $(( T0 + 31 - $(date +%s) ))
situacao "$T4"; situacao "$T3"; assentos "$E6"
sleep $(( T0 + 45 - $(date +%s) ))
api GET /api/partner/tickets/$T4
api GET /api/partner/tickets/$T3
assentos "$E6"; assentos "$E7"
prazo "$T4" "between interval '30 seconds' and interval '40 seconds'"; prazo "$T3" "between interval '30 seconds' and interval '40 seconds'"
```

Esperado:
- os dois ids; `202`; `202`;
- logo depois: `"availableSeats":0` e `"availableSeats":0` (cada pendente ocupa a única vaga); `409 {"error":"sold_out"}`;
- aos 31 s: `"status":"pending"`, `"status":"pending"` e `"availableSeats":0`;
- aos 45 s: exatamente `200 {"ticketId":"<T4>","code":"…","eventId":"<E6>","status":"declined","checkedIn":false}` e `200 {"ticketId":"<T3>","code":"…","eventId":"<E7>","status":"confirmed","checkedIn":false}` (com os códigos de 8 caracteres de cada um);
- `"availableSeats":1` (a recusa devolveu a vaga do E6) e `"availableSeats":0` (E7 confirmado continua ocupando);
- `declined|t` e `confirmed|t` (responderam entre 30 e 40 s depois da compra).

### C-09 — (F04-CA07) Consulta: `checkedIn` vem do check-in e `status` é o valor do banco

```bash
sql "update dominio_ingresso set check_in_em = now() where id_publico = '$T1'"   # simula o check-in (F05)
api GET /api/partner/tickets/$T1
sql "update dominio_ingresso set status = 'refunded' where id_publico = '$T3'"   # simula o estorno (F07)
api GET /api/partner/tickets/$T3 | grep -oE '"status":"[a-z]+","checkedIn":(true|false)'
cabecalhos
```

Esperado: `UPDATE 1`; exatamente `200 {"ticketId":"<T1>","code":"<K1>","eventId":"<E1>","status":"confirmed","checkedIn":true}` (check-in não muda o status); `UPDATE 1`; `"status":"refunded","checkedIn":false`; uma única linha `Content-Type: application/json`.

### C-10 — (F04-CA08) Ingresso inexistente

```bash
api GET /api/partner/tickets/tkt_naoexiste
api GET /api/partner/tickets/$K1
cabecalhos
```

Esperado: `404 {"error":"ticket_not_found"}`; `404 {"error":"ticket_not_found"}` (o código do ingresso não é o `ticketId`); uma única linha `Content-Type: application/json`.

### C-11 — (F04-CA09, R07) Rajada de 30 compras simultâneas pela API (passo 15) e `scripts/rajada-api.sh`

```bash
for rodada in 1 2; do
  E=$(novo_evento $D/a "Rajada API $rodada" "2027-07-0${rodada}T20:00" 5 "10,00"); echo "$E"
  seq 30 | xargs -P 30 -I{} curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" -d '{"buyerEmail":"rajada{}@example.com","cardNumber":"4000000000000001"}' "$WEB/api/partner/events/$E/purchases" | sort | uniq -c
  sql "select count(*), count(*) filter (where i.status in ('pending', 'confirmed')), e.lotacao from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico = '$E' group by e.lotacao"
done
CATRACA_PORTA=$PORTA ./scripts/rajada-api.sh; echo "código: $?"
CATRACA_PORTA=$PORTA CATRACA_CHAVE_PARCEIRO=errada ./scripts/rajada-api.sh 1 | tail -n 1; echo "código: ${PIPESTATUS[0]}"
```

Esperado:
- em cada uma das duas rodadas: um id `evt_…`; exatamente duas linhas de contagem, `5 202` e `25 409` (com espaços à esquerda do número); `5|5|5` (5 ingressos, 5 vagas ocupadas, lotação 5);
- o script: para cada uma das 5 rodadas, as duas linhas `5 202` e `25 409` e a linha `rodada N (evt_…): OK` (N de 1 a 5); por último `rajada-api: OK (5 rodadas)`; "código: 0";
- com a chave errada (prova de que o script confere o resultado): `rajada-api: FALHOU`; "código: 1".

### C-12 — (F04-CA10) A API só chama serviços do domínio

```bash
grep -rnE "objects\.(create|update|filter\(.*\)\.update)|\.save\(" api_parceiros/ | grep -v '^api_parceiros/tests/' | wc -l
grep -ohE "comprar_ingresso|consultar_ingresso|eventos_a_venda|vagas_disponiveis" api_parceiros/views.py api_parceiros/serializadores.py | sort -u
grep -c "compare_digest" api_parceiros/auth.py
```

Esperado: `0` (nenhuma gravação direta fora dos testes; com ou sem espaços à esquerda); exatamente 4 linhas: `comprar_ingresso`, `consultar_ingresso`, `eventos_a_venda`, `vagas_disponiveis`; `1` (comparação da chave em tempo constante).

### C-13 — Testes automatizados da feature

```bash
./scripts/gates.sh -v api_parceiros/tests/; echo "código: $?"
```

Esperado: "código: 0", nenhum "FAILED" nem "SKIPPED", e como PASSED (com ou sem sufixo `[...]`) pelo menos:
- `api_parceiros/tests/test_auth.py`: `test_sem_chave_responde_401_nas_tres_rotas`, `test_chave_errada_responde_401_nas_tres_rotas`, `test_chave_vazia_no_cabecalho_responde_401`, `test_configuracao_vazia_nunca_autentica`, `test_401_vem_antes_de_corpo_invalido_e_inexistentes`, `test_chave_certa_passa`, `test_comparacao_em_tempo_constante`, `test_api_isenta_de_csrf_e_sem_cookie`, `test_metodo_errado_responde_405_depois_da_chave`;
- `api_parceiros/tests/test_eventos.py`: `test_lista_vazia`, `test_lista_so_publicados_na_ordem_do_inicio`, `test_evento_tem_exatamente_os_cinco_campos`, `test_starts_at_iso_com_offset_de_sao_paulo`, `test_available_seats_igual_a_vagas_disponiveis`, `test_rascunho_e_cancelado_ficam_fora`, `test_json_compacto_e_content_type`;
- `api_parceiros/tests/test_compras.py`: `test_compra_responde_202_pendente_com_tres_campos`, `test_compra_grava_canal_api_sem_comprador`, `test_corpo_invalido_responde_422_sem_criar`, `test_422_antes_de_404`, `test_evento_indisponivel_responde_404`, `test_cancelado_lotado_responde_404_e_nao_409`, `test_sem_vaga_responde_409_sem_criar`, `test_compra_da_api_esgota_a_vitrine`;
- `api_parceiros/tests/test_ingressos.py`: `test_consulta_tem_exatamente_os_cinco_campos`, `test_consulta_mostra_cada_status`, `test_checked_in_vem_de_check_in_em`, `test_ingresso_da_vitrine_e_consultavel_com_o_mesmo_code`, `test_ingresso_inexistente_responde_404`;
- `api_parceiros/tests/test_camada.py`: `test_api_parceiros_nao_grava_direto_no_banco`, `test_rajada_api_existe_e_usa_xargs_p_30`.

Ao terminar: `CATRACA_PORTA=$PORTA ./scripts/down.sh` e `rm -rf "$D"`.

## 3. Mapeamento critério do PRD → itens

| Critério do PRD | Itens |
|---|---|
| F04-CA01 — (R02, R05) Listagem com exatamente os cinco campos, `startsAt` com offset, `priceCents` inteiro, `availableSeats` = vagas disponíveis; só publicados | C-02, C-04, C-06, C-07, C-08, C-13 |
| F04-CA02 — (R06) Compra 202 com exatamente `ticketId`, `code`, `status: "pending"`; `canal=api`, comprador nulo, e-mail informado | C-04, C-13 |
| F04-CA03 — 401 `unauthorized` nas três rotas sem chave ou com chave errada, antes de tudo | C-03, C-13 |
| F04-CA04 — Corpo inválido → 422 `invalid_request` sem criar; 422 antes de 404 | C-05, C-13 |
| F04-CA05 — (R02) Inexistente, rascunho ou cancelado → 404 `event_not_available`; cancelado é 404, não 409 | C-06, C-13 |
| F04-CA06 — (R07) Sem vaga → 409 `sold_out` sem criar | C-06, C-07, C-08, C-13 |
| F04-CA07 — Consulta com exatamente cinco campos; `checkedIn` booleano; ingresso da vitrine também | C-04, C-07, C-08, C-09, C-13 |
| F04-CA08 — Ingresso inexistente → 404 `ticket_not_found` | C-10, C-13 |
| F04-CA09 — (R07) Rajada do passo 15: `5 202` e `25 409`; `scripts/rajada-api.sh` em 5 eventos novos com código 0 | C-11 |
| F04-CA10 — Grep da camada sem nada fora dos testes | C-12, C-13 |
| XF-05 [F02→F04] — Rascunho criado pela interface fora da API; publicado com o `id` da gestão, `priceCents` 10000 e `availableSeats` = lotação | C-02 |
| XF-06 [F03→F04] — Mesma lotação e mesmo gateway: API esgota a vitrine e vitrine esgota a API (409); 0001 `confirmed` em até 5 s; 0004 `pending` aos 30 s com `availableSeats` 0 e `declined` antes de 45 s devolvendo a vaga; ingresso da vitrine consultável com o mesmo `code` | C-04, C-07, C-08 |

## 4. Fora deste contrato

- Cancelamento de verdade (F07, XF-16 e XF-19): aqui o status `cancelado` e o `refunded` são simulados no banco só para mostrar que a API os respeita. Check-in de verdade (F05; XF-13 cobre a combinação com a API na F06): aqui `check_in_em` é simulado no banco. Painel contando as vendas da API (F06, XF-11 e XF-13).
- Gestão de chaves, limite de taxa e paginação da API (fora de escopo, PRD seção 10).
