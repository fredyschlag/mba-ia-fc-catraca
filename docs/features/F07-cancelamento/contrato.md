# Contrato — F07 Cancelamento

> O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item, na ordem. Textos esperados vão entre aspas, exatos, e são conferidos com `grep -F` (`grep -c` conta **linhas** que contêm o texto).

- Feature: F07 — Cancelamento (wave W6)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (F07-CA01…CA08) e 7 (XF-14…XF-19)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- **Antes de tudo**, na raiz do repositório: `git rev-parse HEAD` precisa imprimir exatamente o sha completo pedido para a avaliação, e `git status --porcelain` precisa sair vazio. Se um dos dois não bater, o avaliador **para**, registra no relatório as duas saídas e não avalia nenhum item.
- Commit avaliado: o sha informado no pedido de avaliação (branch `feat/F07-cancelamento`).
- Ferramentas no host: Docker, Git, `curl`, **bash** e os utilitários `awk`, `sed`, `grep` (GNU ou BSD, com `-o`; se o seu shell redefinir `grep` como função ou alias, rode antes `unset -f grep; unalias grep 2>/dev/null`), `cut`, `sort`, `uniq`, `xargs`, `seq`, `tr`, `paste`, `date` (`date +%s`) e `sleep`. Navegador é opcional.
- **Blocos sem pausa.** O C-03 compra cartões lentos (32–38 s) e precisa cancelar antes de 30 s da compra: ele roda **inteiro num só bloco**, sem pausas além dos `sleep` escritos. O C-09 confere depois de 45 s da compra (o `sleep` dele calcula o que falta a partir de `T0`). Todo comando roda na raiz do repositório (o `sql` usa `docker compose exec`).
- Contas da seed (README, "Credenciais"): `org.a@catraca.test`, `org.b@catraca.test` e `participante@catraca.test`, com a senha `catraca123`; chave de parceiro `chave-parceiro-dev`.
- **Tempo.** A execução completa leva uns 2 minutos, sem contar os gates.
- **Porta.** Vem de `CATRACA_PORTA` (padrão 8000); o avaliador exporta a porta informada no pedido de avaliação antes de tudo. A mesma variável vale na subida, nos itens e na descida.
- **Banco zerado**, na raiz:

```bash
PORTA=${CATRACA_PORTA:-8000}
docker compose --profile '*' down -v          # apaga só o volume deste projeto
CATRACA_PORTA=$PORTA ./scripts/up.sh          # código 0 e "Catraca no ar."
```

- **Funções e estado.** Rode uma vez o bloco abaixo, em bash. Ele grava as funções em `$D/f.sh` e as variáveis criadas pelos itens em `$D/ids`. Os itens rodam **na ordem**. Se um item for rodado num **shell novo**, antes dele rode: `PORTA=${CATRACA_PORTA:-8000}; D=/tmp/catraca-F07-$PORTA; . $D/f.sh; . $D/ids`.

```bash
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F07-$PORTA; rm -rf "$D"; mkdir -p "$D"; : > "$D/ids"
cat > "$D/f.sh" <<'FIM'
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F07-$PORTA
export WEB=http://localhost:$PORTA
export API=$WEB
KEY=chave-parceiro-dev
sql()       { docker compose exec -T db psql -U catraca -d catraca -tAc "$1"; }
csrf()      { awk '$6 == "csrftoken" {print $7}' "$1"; }
ver()       { curl -s -o /dev/null -D - -b "$1" -c "$1" "$WEB$2" | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
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
# compra na vitrine como participante; imprime status e Location
comprar()   { curl -s -o /dev/null -b "$1" -c "$1" "$WEB/contas/entrar/"
              curl -s -o "$1.html" -D - -b "$1" -c "$1" \
                --data-urlencode "csrfmiddlewaretoken=$(csrf "$1")" --data-urlencode "cartao=$3" \
                "$WEB/eventos/$2/comprar/" | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
# compra pela API: compra_api <evento> <cartão> → imprime "<status http> <corpo>"; o corpo fica em $D/resposta.json
compra_api(){ curl -s -o "$D/resposta.json" -w '%{http_code}' -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
                --data-binary "{\"buyerEmail\":\"parceiro@example.com\",\"cardNumber\":\"$2\"}" \
                "$API/api/partner/events/$1/purchases"; echo " $(cat "$D/resposta.json")"; }
campo()     { sed -nE "s/.*\"$1\":\"?([^\",}]*)\"?.*/\1/p" "$D/resposta.json"; }
bilhete()   { curl -s -H "X-Api-Key: $KEY" "$API/api/partner/tickets/$1"; echo; }
# código do ingresso mais recente do evento
ultimo()    { sql "select i.codigo from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico = '$1' order by i.id desc limit 1"; }
# check-in pela gestão: checkin <cookies> <evento> <código> → imprime a mensagem (ou "sem mensagem")
checkin()   { curl -s -o /dev/null -b "$1" -c "$1" "$WEB/contas/entrar/"
              curl -s -o "$1.html" -b "$1" -c "$1" \
                --data-urlencode "csrfmiddlewaretoken=$(csrf "$1")" --data-urlencode "codigo=$3" \
                "$WEB/organizador/eventos/$2/check-in/"
              grep -oE '<p id="check-in-mensagem">[^<]*</p>' "$1.html" || echo "sem mensagem"; }
# os seis números do painel da gestão, numa linha: confirmados=… pendentes=… check-ins=… vagas-disponiveis=… receita=… estornados=…
painel()    { corpo "$1" "/organizador/eventos/$2/" | grep -oE 'data-metrica="[a-z-]+">[^<]*<' \
                | sed -E 's/data-metrica="([a-z-]+)">([^<]*)</\1=\2/' | paste -sd' ' -; }
# cancela pela gestão: cancelar <cookies> <evento> → imprime status e Location; o corpo fica em <cookies>.html
cancelar()  { postar "$1" "/organizador/eventos/$2/cancelar/"; }
# status de um ingresso pelo id público ou pelo código
status_id() { sql "select status from dominio_ingresso where id_publico = '$1'"; }
status_cod(){ sql "select status from dominio_ingresso where codigo = '$1'"; }
FIM
. "$D/f.sh"
```

"Status 302 e `location: /x`" quer dizer: a linha `HTTP/1.1 302 …` e o cabeçalho `Location` com o valor exato `/x`. A saída de `painel` é uma única linha com os seis pares na ordem do bloco. `<E1>`, `<C1>` etc. são os valores impressos no item que os criou.

## 2. Itens verificáveis

### C-01 — Gates

```bash
./scripts/gates.sh; echo "código: $?"
```

Esperado: "código: 0", pytest sem falhas, última etapa "==> gates: OK".

### C-02 — (F07-CA01, F07-CA07, R11, R13) Só o dono cancela, e só evento publicado; o botão pede confirmação

```bash
entrar $D/a org.a@catraca.test; entrar $D/b org.b@catraca.test; entrar $D/p participante@catraca.test
E0=$(postar $D/a /organizador/eventos/novo/ "nome=Rascunho" "inicio=2027-06-19T21:00" "local=Sala" "lotacao=2" "preco=10,00" | idde); guardar E0 "$E0"
corpo $D/a /organizador/eventos/$E0/ | grep -c 'id="form-cancelar"'
cancelar $D/a "$E0"; grep -cF "Só evento publicado pode ser cancelado." $D/a.html
E1=$(novo_evento $D/a "Show Cancelável" "2027-06-20T21:00" 5 "50,00"); guardar E1 "$E1"; echo "$E0 $E1"
corpo $D/a /organizador/eventos/$E1/ > $D/g1.html
grep -c 'id="form-cancelar"' $D/g1.html; grep -cF "action=\"/organizador/eventos/$E1/cancelar/\"" $D/g1.html; grep -cF 'onsubmit="return confirm(' $D/g1.html
cancelar $D/b "$E1"; grep -cF "Show Cancelável" $D/b.html
ver $D/v /contas/entrar/ >/dev/null; cancelar $D/v "$E1"
cancelar $D/p "$E1"
sql "select id_publico, status from dominio_evento where id_publico in ('$E0', '$E1') order by id"
```

Esperado: três logins com status 302 (`location: /organizador/`, `/organizador/` e `/`); `0` (rascunho sem botão); status 409 sem `location:` e `1`; os dois ids; `1`; `1`; `1` (formulário, destino e confirmação no navegador); organizador B: status 404 e `0` (nenhum dado do evento); visitante: status 302 e `location: /contas/entrar/`; participante: status 403; duas linhas, `<E0>|rascunho` e `<E1>|publicado` (nada mudou).

### C-03 — (F07-CA01, F07-CA04, XF-16, XF-19, R11) Passo 12 do Fluxo: compras pela API e pela vitrine, check-in, cancelamento antes de 30 s; ingressos mudam na mesma transação

```bash
E2=$(novo_evento $D/a "Outro Evento" "2027-06-21T21:00" 5 "30,00"); guardar E2 "$E2"
E3=$(novo_evento $D/a "Vitrine Cancelável" "2027-06-22T21:00" 5 "40,00"); guardar E3 "$E3"; echo "$E2 $E3"
T0=$(date +%s); guardar T0 "$T0"
compra_api "$E1" 4000000000000003; T5=$(campo ticketId); K5=$(campo code); guardar T5 "$T5"; guardar K5 "$K5"
compra_api "$E1" 4000000000000001; T6=$(campo ticketId); K6=$(campo code); guardar T6 "$T6"; guardar K6 "$K6"
compra_api "$E1" 4000000000000004; T7=$(campo ticketId); K7=$(campo code); guardar T7 "$T7"; guardar K7 "$K7"
compra_api "$E2" 4000000000000001; T9=$(campo ticketId); K9=$(campo code); guardar T9 "$T9"; guardar K9 "$K9"
comprar $D/p "$E3" 4000000000000001; V1=$(ultimo "$E3"); guardar V1 "$V1"
comprar $D/p "$E3" 4000000000000003; V2=$(ultimo "$E3"); guardar V2 "$V2"
comprar $D/p "$E3" 4000000000000002; TV=$(date +%s); V3=$(ultimo "$E3"); guardar V3 "$V3"
s=$(( TV + 5 - $(date +%s) )); [ "$s" -gt 0 ] && sleep "$s"
for t in "$T5" "$T6" "$T7"; do status_id "$t"; done; for v in "$V1" "$V2" "$V3"; do status_cod "$v"; done
checkin $D/a "$E1" "$K6"
painel $D/a "$E1"
TC=$(date +%s); cancelar $D/a "$E1"
sql "select status from dominio_evento where id_publico = '$E1'"
sql "select status, check_in_em is not null from dominio_ingresso where id_publico in ('$T5', '$T6', '$T7') order by id"
bilhete "$T6"; bilhete "$T5"; echo "segundos desde o cancelamento: $(( $(date +%s) - TC ))"
cancelar $D/a "$E3"
sql "select status from dominio_ingresso where codigo in ('$V1', '$V2', '$V3') order by id"
echo "segundos desde a compra de T5: $(( $(date +%s) - T0 ))"
```

Esperado:
- os dois ids; quatro compras pela API `202 {…,"status":"pending"}`; três compras na vitrine com status 302 e `location: /meus-ingressos/`;
- 5 s depois da última compra: `pending` (T5, 0003), `confirmed` (T6), `pending` (T7, 0004), `confirmed` (V1), `pending` (V2, 0003), `declined` (V3, 0002);
- check-in de T6: `<p id="check-in-mensagem">Entrada liberada</p>`;
- antes do cancelamento: `confirmados=1 pendentes=2 check-ins=1 vagas-disponiveis=2 receita=R$ 50,00 estornados=0`;
- cancelar E1: status 302 e `location: /organizador/eventos/<E1>/`; `cancelado`; três linhas, `cancelled|f` (T5), `refunded|t` (T6, que continua com o check-in) e `cancelled|f` (T7) — conferido logo depois do POST;
- pela API, logo depois: `{"ticketId":"<T6>","code":"<K6>","eventId":"<E1>","status":"refunded","checkedIn":true}` e `{"ticketId":"<T5>","code":"<K5>","eventId":"<E1>","status":"cancelled","checkedIn":false}`; um número **menor ou igual a 10**;
- cancelar E3: status 302 e `location: /organizador/eventos/<E3>/`; três linhas, `refunded` (V1), `cancelled` (V2) e `declined` (V3, que não muda);
- um número **menor que 30**.

### C-04 — (F07-CA02, XF-14, XF-15, XF-16, R02, R11) Evento cancelado sai da vitrine e da API e não vende

```bash
corpo $D/v / | grep -cE "$E1|$E3"
ver $D/v /eventos/$E1/
curl -s -H "X-Api-Key: $KEY" "$API/api/partner/events" | grep -cE "$E1|$E3"
curl -s -H "X-Api-Key: $KEY" "$API/api/partner/events" | grep -c "$E2"
compra_api "$E1" 4000000000000001
comprar $D/p "$E3" 4000000000000001
sql "select e.id_publico, count(i.id) from dominio_evento e left join dominio_ingresso i on i.evento_id = e.id where e.id_publico in ('$E1', '$E3') group by e.id_publico, e.id order by e.id"
corpo $D/a /organizador/ > $D/lista.html
grep -cF "data-evento=\"$E1\" data-status=\"cancelado\"" $D/lista.html; grep -cF "data-evento=\"$E3\" data-status=\"cancelado\"" $D/lista.html; grep -c '>Cancelado<' $D/lista.html
```

Esperado: `0`; status 404; `0`; `1` (o E2, publicado, continua na API); `404 {"error":"event_not_available"}`; status 404; duas linhas, `<E1>|3` e `<E3>|3` (nenhum ingresso novo); `1`; `1`; `2` (a lista do organizador mostra "Cancelado").

### C-05 — (F07-CA03, F07-CA01, XF-14, R11) Irreversível: sem editar, sem publicar, sem reverter

```bash
corpo $D/a /organizador/eventos/$E1/ > $D/g1c.html
grep -cF "/organizador/eventos/$E1/editar/" $D/g1c.html; grep -cF "/organizador/eventos/$E1/publicar/" $D/g1c.html; grep -c 'id="form-cancelar"' $D/g1c.html
grep -cF 'data-campo="status">Cancelado<' $D/g1c.html; grep -cF "Este evento foi cancelado." $D/g1c.html
grep -oE 'organizador/eventos/<str:evento_id>/[a-z-]+/' web/urls.py | sort
ver $D/a /organizador/eventos/$E1/editar/
corpo $D/a /organizador/eventos/$E1/editar/ | grep -cF "Evento cancelado não pode ser alterado."
postar $D/a /organizador/eventos/$E1/editar/ "nome=Ressuscitado" "inicio=2027-07-20T21:00" "local=Outro" "lotacao=10" "preco=1,00"; grep -cF "Evento cancelado não pode ser alterado." $D/a.html
postar $D/a /organizador/eventos/$E1/publicar/; grep -cF "Evento cancelado não pode ser alterado." $D/a.html
cancelar $D/a "$E1"
sql "select nome, lotacao, preco_centavos, status, local, to_char(inicio at time zone 'America/Sao_Paulo', 'YYYY-MM-DD HH24:MI') from dominio_evento where id_publico = '$E1'"
ver $D/b /organizador/eventos/$E1/editar/
postar $D/b /organizador/eventos/$E1/editar/ "nome=Invasor" "inicio=2027-07-20T21:00" "local=Outro" "lotacao=10" "preco=1,00"; grep -cE 'Show Cancelável|cancelado não pode' $D/b.html
postar $D/b /organizador/eventos/$E1/publicar/; grep -cE 'Show Cancelável|cancelado não pode' $D/b.html
sql "select status from dominio_ingresso where id_publico in ('$T5', '$T6') order by id"
```

Esperado: `0`; `0`; `0` (sem editar, publicar nem cancelar); `1`; `1`; exatamente quatro linhas, nesta ordem: `organizador/eventos/<str:evento_id>/cancelar/`, `organizador/eventos/<str:evento_id>/check-in/`, `organizador/eventos/<str:evento_id>/editar/` e `organizador/eventos/<str:evento_id>/publicar/` (não existe rota de reverter; publicar um cancelado é rejeitado logo abaixo); status 409; `1`; editar por POST: status 409 sem `location:` e `1`; publicar: status 409 sem `location:` e `1`; cancelar de novo: status 302 e `location: /organizador/eventos/<E1>/`; `Show Cancelável|5|5000|cancelado|Sala|2027-06-20 21:00`; organizador B: status 404 no `GET` de editar, status 404 sem `location:` e `0` no `POST` de editar, status 404 sem `location:` e `0` no `POST` de publicar (o 404 de outro organizador vem antes do 409 e não revela o evento); `cancelled` e `refunded` (nada mudou).

### C-06 — (XF-15, XF-16, XF-19, R11) API e Meus ingressos logo depois do cancelamento

```bash
bilhete "$T6"; bilhete "$T5"
corpo $D/p /meus-ingressos/ > $D/mi.html
for par in "$V1:estornado" "$V2:cancelado" "$V3:recusado"; do grep -F "data-campo=\"codigo\">${par%%:*}<" $D/mi.html | grep -cF "data-campo=\"status\">${par##*:}<"; done
```

Esperado: `{"ticketId":"<T6>","code":"<K6>","eventId":"<E1>","status":"refunded","checkedIn":true}`; `{"ticketId":"<T5>","code":"<K5>","eventId":"<E1>","status":"cancelled","checkedIn":false}`; três linhas `1`.

### C-07 — (XF-17, XF-19, R10, R11) Check-in em evento cancelado

```bash
checkin $D/a "$E1" "$K6"
checkin $D/a "$E1" "$K5"
checkin $D/a "$E1" "$K9"
checkin $D/a "$E3" "$V1"
checkin $D/a "$E3" "$V3"
sql "select count(*) from dominio_ingresso where check_in_em is not null"
```

Esperado: `<p id="check-in-mensagem">Evento cancelado</p>` (T6, que estava confirmado e com check-in); `<p id="check-in-mensagem">Evento cancelado</p>` (T5); `<p id="check-in-mensagem">Ingresso inválido para este evento</p>` (ingresso de outro evento); `<p id="check-in-mensagem">Evento cancelado</p>` (V1); `<p id="check-in-mensagem">Evento cancelado</p>` (V3, recusado); `1` (só o check-in de T6 do C-03).

### C-08 — (XF-18, XF-19, F07-CA08, R05, R12) Painel depois do cancelamento

```bash
painel $D/a "$E1"
painel $D/a "$E3"
```

Esperado: `confirmados=0 pendentes=0 check-ins=0 vagas-disponiveis=0 receita=R$ 0,00 estornados=1` nas duas linhas (o estorno não é receita, o check-in de um estornado não conta e as vagas de evento cancelado são zero mesmo com a lotação livre).

### C-09 — (F07-CA05, XF-15, XF-16, R08, R11) Passo 14 do Fluxo: a resposta tardia do gateway não muda nada

```bash
s=$(( T0 + 46 - $(date +%s) )); [ "$s" -gt 0 ] && sleep "$s"
echo "segundos desde a compra de T5: $(( $(date +%s) - T0 ))"
bilhete "$T5"; bilhete "$T7"
status_cod "$V2"
sql "select count(*) filter (where c.processada_em is not null) from dominio_cobrancagateway c join dominio_ingresso i on i.id = c.ingresso_id where i.id_publico in ('$T5', '$T7') or i.codigo = '$V2'"
corpo $D/p /meus-ingressos/ | grep -F "data-campo=\"codigo\">$V2<" | grep -cF 'data-campo="status">cancelado<'
painel $D/a "$E1"
```

Esperado: um número maior ou igual a `45`; `{"ticketId":"<T5>","code":"<K5>","eventId":"<E1>","status":"cancelled","checkedIn":false}` e `{"ticketId":"<T7>","code":"<K7>","eventId":"<E1>","status":"cancelled","checkedIn":false}`; `cancelled`; `3` (o worker já processou as três cobranças lentas, duas aprovações e uma recusa, e nenhuma mudou nada); `1`; `confirmados=0 pendentes=0 check-ins=0 vagas-disponiveis=0 receita=R$ 0,00 estornados=1`.

### C-10 — (F07-CA06, R11) Corrida gateway × cancelamento

```bash
./scripts/gates.sh -v dominio/tests/test_cancelamento_concorrencia.py; echo "código: $?"
for p in 'REPETICOES = 50' 'threading.Barrier(2)' 'aplicar_resposta_gateway(' 'cancelar_evento(' 'def test_aprovacao_que_espera_o_cancelamento_nao_muda_nada' 'def test_cancelamento_que_espera_a_aprovacao_estorna'; do grep -qF "$p" dominio/tests/test_cancelamento_concorrencia.py && echo "ok: $p"; done
grep -cE 'Case\(|When\(' dominio/servicos/cancelamento.py
```

Esperado: "código: 0" com três PASSED: `test_corrida_aprovacao_e_cancelamento_nunca_deixa_confirmado` (50 repetições soltas por uma barreira de 2 threads: o par retorno da aprovação × status final é sempre `(True, refunded)` ou `(False, cancelled)`, nunca `confirmed` nem `pending` em evento cancelado), `test_aprovacao_que_espera_o_cancelamento_nao_muda_nada` (a aprovação espera a trava do cancelamento e devolve `False`; o ingresso fica `cancelled`) e `test_cancelamento_que_espera_a_aprovacao_estorna` (o cancelamento espera a trava da aprovação e estorna: `refunded`); seis linhas `ok: …`; um número maior ou igual a `1` (os ingressos mudam num único `UPDATE` com `CASE`).

### C-11 — Testes automatizados da feature

```bash
./scripts/gates.sh -v dominio/tests/test_cancelamento.py web/tests/test_cancelamento.py; echo "código: $?"
```

Esperado: "código: 0", nenhum "FAILED" nem "SKIPPED", e como PASSED (com ou sem sufixo `[...]`) pelo menos: `test_cancelar_publicado_estorna_confirmados_e_cancela_pendentes`, `test_cancelar_mantem_check_in_e_recusados`, `test_cancelar_de_novo_nao_muda_nada`, `test_cancelar_rascunho_e_rejeitado`, `test_cancelar_evento_de_outro_organizador`, `test_evento_cancelado_nao_edita_nem_publica`, `test_evento_cancelado_sai_da_venda`, `test_vagas_de_evento_cancelado_sao_zero`, `test_resposta_tardia_nao_muda_cancelado_nem_estornado`, `test_propriedades_de_estado_do_evento` (em `dominio/tests/test_cancelamento.py`); `test_bloco_cancelar_so_em_publicado_com_confirmacao`, `test_cancelar_pela_gestao`, `test_cancelar_rascunho_pela_tela_responde_409`, `test_outro_organizador_nao_cancela`, `test_visitante_e_participante_nao_cancelam`, `test_gestao_de_cancelado_sem_editar_nem_publicar`, `test_editar_e_publicar_cancelado_respondem_409`, `test_lista_do_organizador_mostra_cancelado` (em `web/tests/test_cancelamento.py`).

Ao terminar: `CATRACA_PORTA=$PORTA ./scripts/down.sh` e `rm -rf "$D"`.

## 3. Mapeamento critério do PRD → itens

| Critério do PRD | Itens |
|---|---|
| F07-CA01 — (R11) `#evento-cancelar` pede confirmação; POST cancela; rascunho sem botão e POST rejeitado; já cancelado não muda | C-02, C-03, C-05, C-11 |
| F07-CA02 — (R11, R02) Sai de `/`, de `eventos_a_venda()`; detalhe 404; `comprar_ingresso` recusa | C-04, C-11 |
| F07-CA03 — (R11) Gestão sem editar e publicar; editar e publicar mostram "Evento cancelado não pode ser alterado."; banco não muda; sem reverter | C-05, C-11 |
| F07-CA04 — (R11) Na mesma transação: confirmed → refunded (com check-in também), pending → cancelled, declined igual; logo após o POST | C-03, C-11 |
| F07-CA05 — (R11, R08) Pendente 0003 continua `cancelled` depois da resposta do gateway (45 s no modo padrão; em teste com atraso curto) | C-09, C-11 |
| F07-CA06 — (R11) Corrida gateway × cancelamento, 50 repetições | C-10 |
| F07-CA07 — (R13) POST de outro organizador → 404 sem efeito | C-02, C-11 |
| F07-CA08 — (R05) Vagas de evento cancelado = 0 | C-08, C-11 |
| XF-14 [F02→F07] — Sai da vitrine; gestão sem editar e publicar; POST rejeitados; lista com "Cancelado" | C-04, C-05 |
| XF-15 [F03→F07] — Meus ingressos "estornado" e "cancelado" logo após; pendente continua "cancelado" depois do worker; vagas 0; vitrine recusa | C-03, C-04, C-06, C-08, C-09 |
| XF-16 [F04→F07] — Some da API; compra 404 `event_not_available`; refunded e cancelled em até 10 s; cancelled 45 s após a compra | C-03, C-04, C-06, C-09 |
| XF-17 [F05→F07] — Code que estava confirmado → "Evento cancelado"; code de outro evento → "Ingresso inválido para este evento" | C-07 |
| XF-18 [F06→F07] — Passos 12 a 14: painel 0/0/0/0/"R$ 0,00"/1 | C-08, C-09 |
| XF-19 [F04+F05+F06→F07] — Ingresso da API confirmado com check-in → `refunded` e `checkedIn: true`; painel Estornados 1, Check-ins 0, Receita "R$ 0,00"; check-in → "Evento cancelado" | C-03, C-06, C-07, C-08 |

## 4. Fora deste contrato

- Estorno financeiro real (fora de escopo do PRD); cancelamento de ingresso pelo participante (fora de escopo do enunciado).
