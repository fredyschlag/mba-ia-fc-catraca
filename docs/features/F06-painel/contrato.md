# Contrato — F06 Painel

> O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item, na ordem. Textos esperados vão entre aspas, exatos, e são conferidos com `grep -F` (`grep -c` conta **linhas** que contêm o texto).

- Feature: F06 — Painel (wave W5)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (F06-CA01…CA05) e 7 (XF-09, XF-10, XF-11, XF-12, XF-13)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- **Antes de tudo**, na raiz do repositório: `git rev-parse HEAD` precisa imprimir exatamente o sha completo pedido para a avaliação, e `git status --porcelain` precisa sair vazio. Se um dos dois não bater, o avaliador **para**, registra no relatório as duas saídas e não avalia nenhum item.
- Commit avaliado: o sha informado no pedido de avaliação (branch `feat/F06-painel`).
- Ferramentas no host: Docker, Git, `curl`, **bash** e os utilitários `awk`, `sed`, `grep` (GNU ou BSD, com `-o`; se o seu shell redefinir `grep` como função ou alias, rode antes `unset -f grep; unalias grep 2>/dev/null`), `cut`, `sort`, `uniq`, `xargs`, `seq`, `tr`, `paste`, `date` (`date +%s`) e `sleep`. Navegador é opcional.
- **Blocos sem pausa.** C-03, C-04 e C-05 dependem do tempo do gateway (os rápidos respondem em 2–4 s, os lentos em 32–38 s): cada um desses itens roda **inteiro num só bloco**, sem pausas além dos `sleep` escritos. Todo comando roda na raiz do repositório (o `sql` usa `docker compose exec`).
- Contas da seed (README, "Credenciais"): `org.a@catraca.test`, `org.b@catraca.test` e `participante@catraca.test`, com a senha `catraca123`; chave de parceiro `chave-parceiro-dev`.
- **Tempo.** O C-04 espera os cartões lentos (cerca de 45 s). A execução completa leva uns 3 minutos, sem contar os gates.
- **Porta.** Vem de `CATRACA_PORTA` (padrão 8000); o avaliador exporta a porta informada no pedido de avaliação antes de tudo. A mesma variável vale na subida, nos itens e na descida.
- **Banco zerado**, na raiz:

```bash
PORTA=${CATRACA_PORTA:-8000}
docker compose --profile '*' down -v          # apaga só o volume deste projeto
CATRACA_PORTA=$PORTA ./scripts/up.sh          # código 0 e "Catraca no ar."
```

- **Funções e estado.** Rode uma vez o bloco abaixo, em bash. Ele grava as funções em `$D/f.sh` e as variáveis criadas pelos itens em `$D/ids`. Os itens rodam **na ordem**. Se um item for rodado num **shell novo**, antes dele rode: `PORTA=${CATRACA_PORTA:-8000}; D=/tmp/catraca-F06-$PORTA; . $D/f.sh; . $D/ids`.

```bash
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F06-$PORTA; rm -rf "$D"; mkdir -p "$D"; : > "$D/ids"
cat > "$D/f.sh" <<'FIM'
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F06-$PORTA
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
# compra pela API: compra_api <evento> <cartão> → imprime "<status http> <corpo>"; o corpo fica em $D/b
compra_api(){ curl -s -o "$D/b" -w '%{http_code}' -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
                --data-binary "{\"buyerEmail\":\"parceiro@example.com\",\"cardNumber\":\"$2\"}" \
                "$API/api/partner/events/$1/purchases"; echo " $(cat "$D/b")"; }
campo()     { sed -nE "s/.*\"$1\":\"?([^\",}]*)\"?.*/\1/p" "$D/b"; }
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

### C-02 — (F06-CA01, R04, R12) Bloco do painel na gestão

```bash
entrar $D/a org.a@catraca.test
E1=$(novo_evento $D/a "Jazz no Porão" "2027-06-15T21:00" 2 "100,00"); guardar E1 "$E1"; echo "$E1"
corpo $D/a /organizador/eventos/$E1/ > $D/g.html
grep -c 'id="painel"' $D/g.html
for par in "Confirmados:confirmados" "Pendentes:pendentes" "Check-ins:check-ins" "Vagas disponíveis:vagas-disponiveis" "Receita:receita" "Estornados:estornados"; do grep -cF "<dt>${par%%:*}</dt><dd data-metrica=\"${par##*:}\">" $D/g.html; done
painel $D/a "$E1"
```

Esperado: login com status 302 e `location: /organizador/`; um id `evt_…`; `1`; seis linhas `1` (cada rótulo seguido do seu `data-metrica`); `confirmados=0 pendentes=0 check-ins=0 vagas-disponiveis=2 receita=R$ 0,00 estornados=0`.

### C-03 — (XF-10, XF-09, XF-11, F06-CA03, R03, R05, R12) Passo 9 do Fluxo: receita com o preço de cada compra e vagas acompanhando a lotação

```bash
entrar $D/p participante@catraca.test
comprar $D/p "$E1" 4000000000000001; C1=$(ultimo "$E1"); guardar C1 "$C1"
comprar $D/p "$E1" 4000000000000001; C2=$(ultimo "$E1"); guardar C2 "$C2"
sleep 5
painel $D/a "$E1"
postar $D/a /organizador/eventos/$E1/editar/ "nome=Jazz no Porão" "inicio=2027-06-15T21:00" "local=Sala" "lotacao=3" "preco=150,00"
painel $D/a "$E1"
compra_api "$E1" 4000000000000001; T4=$(campo ticketId); K4=$(campo code); guardar T4 "$T4"; guardar K4 "$K4"
painel $D/a "$E1"
sleep 5
painel $D/a "$E1"
sql "select i.valor_centavos from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico = '$E1' order by i.id"
```

Esperado:
- login com status 302 e `location: /`; duas compras com status 302 e `location: /meus-ingressos/`;
- `confirmados=2 pendentes=0 check-ins=0 vagas-disponiveis=0 receita=R$ 200,00 estornados=0`;
- edição: status 302 e `location: /organizador/eventos/<E1>/`;
- `confirmados=2 pendentes=0 check-ins=0 vagas-disponiveis=1 receita=R$ 200,00 estornados=0` (lotação 2 → 3 com 2 ocupadas: vagas 0 → 1);
- a compra pela API: `202 {"ticketId":"tkt_…","code":"…","status":"pending"}`; logo depois `confirmados=2 pendentes=1 check-ins=0 vagas-disponiveis=0 receita=R$ 200,00 estornados=0`;
- depois dos 5 s: `confirmados=3 pendentes=0 check-ins=0 vagas-disponiveis=0 receita=R$ 350,00 estornados=0`;
- três linhas: `10000`, `10000`, `15000`.

### C-04 — (XF-10, XF-11, F06-CA02, R05, R08) Pendentes lentos da vitrine e da API: 0004 sai de Pendentes sem entrar em nenhum outro número; 0003 vira confirmado

```bash
E2=$(novo_evento $D/a "Lentos" "2027-06-16T21:00" 5 "20,00"); guardar E2 "$E2"; echo "$E2"
T0=$(date +%s)
comprar $D/p "$E2" 4000000000000004; K5=$(ultimo "$E2"); guardar K5 "$K5"
T5=$(sql "select id_publico from dominio_ingresso where codigo = '$K5'"); guardar T5 "$T5"
compra_api "$E2" 4000000000000003; T6=$(campo ticketId); K6=$(campo code); guardar T6 "$T6"; guardar K6 "$K6"
painel $D/a "$E2"
sleep $(( T0 + 30 - $(date +%s) )); painel $D/a "$E2"
sleep $(( T0 + 45 - $(date +%s) )); painel $D/a "$E2"
bilhete "$T5"; bilhete "$T6"
```

Esperado: um id `evt_…`; a compra na vitrine (0004) com status 302 e `location: /meus-ingressos/`; a compra pela API (0003) `202 {"ticketId":"<T6>","code":"<K6>","status":"pending"}`; `confirmados=0 pendentes=2 check-ins=0 vagas-disponiveis=3 receita=R$ 0,00 estornados=0` (o pendente da vitrine e o da API contam igual); aos 30 s, a mesma linha; aos 45 s, `confirmados=1 pendentes=0 check-ins=0 vagas-disponiveis=4 receita=R$ 20,00 estornados=0`; `{"ticketId":"<T5>","code":"<K5>","eventId":"<E2>","status":"declined","checkedIn":false}` e `{"ticketId":"<T6>","code":"<K6>","eventId":"<E2>","status":"confirmed","checkedIn":false}`.

### C-05 — (XF-12, XF-13, R10, R12) Check-in conta em Check-ins e só ali; rejeitados não mudam nada; ingresso da API passa no check-in

```bash
checkin $D/a "$E1" "$C1"
painel $D/a "$E1"
checkin $D/a "$E1" "$C1"
checkin $D/a "$E1" ZZZZZZZZ
checkin $D/a "$E1" "$K6"
painel $D/a "$E1"
compra_api "$E2" 4000000000000004; T7=$(campo ticketId); K7=$(campo code); guardar T7 "$T7"
checkin $D/a "$E2" "$K7"
painel $D/a "$E2"
checkin $D/a "$E1" "$K4"
bilhete "$T4"
painel $D/a "$E1"
```

Esperado:
- `<p id="check-in-mensagem">Entrada liberada</p>`; `confirmados=3 pendentes=0 check-ins=1 vagas-disponiveis=0 receita=R$ 350,00 estornados=0`;
- `<p id="check-in-mensagem">Ingresso já utilizado</p>`; `<p id="check-in-mensagem">Ingresso inválido para este evento</p>`; `<p id="check-in-mensagem">Ingresso inválido para este evento</p>` (o code de um ingresso da API de outro evento); a mesma linha do painel de antes (nada mudou);
- compra `202 {…,"status":"pending"}`; `<p id="check-in-mensagem">Ingresso não confirmado</p>`; `confirmados=1 pendentes=1 check-ins=0 vagas-disponiveis=3 receita=R$ 20,00 estornados=0`;
- o code da resposta 202 da compra pela API do C-03: `<p id="check-in-mensagem">Entrada liberada</p>`; `{"ticketId":"<T4>","code":"<K4>","eventId":"<E1>","status":"confirmed","checkedIn":true}`; `confirmados=3 pendentes=0 check-ins=2 vagas-disponiveis=0 receita=R$ 350,00 estornados=0` (o ingresso da API conta em Confirmados, Check-ins e Receita).

### C-06 — (XF-11, R07, R12) Rajada de 30 compras simultâneas pela API: o painel mostra Confirmados 5 e Vagas 0 em até 10 s

```bash
E3=$(novo_evento $D/a "Rajada" "2027-07-01T20:00" 5 "10,00"); guardar E3 "$E3"; echo "$E3"
seq 30 | xargs -P 30 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST "$API/api/partner/events/$E3/purchases" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"buyerEmail":"carga{}@example.com","cardNumber":"4000000000000001"}' | sort | uniq -c
T0=$(date +%s); sleep $(( T0 + 9 - $(date +%s) ))
painel $D/a "$E3"
```

Esperado: um id `evt_…`; exatamente duas linhas, `5 202` e `25 409` (com espaços à esquerda); menos de 10 s depois da rajada, `confirmados=5 pendentes=0 check-ins=0 vagas-disponiveis=0 receita=R$ 50,00 estornados=0`.

### C-07 — (F06-CA02, F06-CA03, R05, R12) Estornados e cancelados: estorno sai da receita e de Check-ins e entra em Estornados; evento cancelado tem zero vagas

Preparação de estado (o cancelamento é da F07): marca no banco o confirmado **com check-in** C1 do E1 como `refunded` e o pendente T7 do E2 como `cancelled`; depois marca o E2 como `cancelado` e o seu confirmado T6 como `refunded`.

```bash
sql "update dominio_ingresso set status = 'refunded' where codigo = '$C1'"
sql "update dominio_ingresso set status = 'cancelled' where id_publico = '$T7'"
painel $D/a "$E1"
painel $D/a "$E2"
sql "update dominio_evento set status = 'cancelado' where id_publico = '$E2'"
sql "update dominio_ingresso set status = 'refunded' where id_publico = '$T6'"
painel $D/a "$E2"
```

Esperado: `UPDATE 1`; `UPDATE 1`; `confirmados=2 pendentes=0 check-ins=1 vagas-disponiveis=1 receita=R$ 250,00 estornados=1` (o estornado com check-in não é receita, não é check-in e não ocupa vaga); `confirmados=1 pendentes=0 check-ins=0 vagas-disponiveis=4 receita=R$ 20,00 estornados=0` (cancelado não entra em nenhum número); `UPDATE 1`; `UPDATE 1`; `confirmados=0 pendentes=0 check-ins=0 vagas-disponiveis=0 receita=R$ 0,00 estornados=1` (evento cancelado: zero vagas, mesmo com a lotação 5 livre).

### C-08 — (F06-CA05, R13) Outro organizador, participante e visitante não veem o painel

```bash
entrar $D/b org.b@catraca.test
ver $D/b /organizador/eventos/$E1/
corpo $D/b /organizador/eventos/$E1/ | grep -cE 'id="painel"|data-metrica|R\$ 350|R\$ 250'
ver $D/p /organizador/eventos/$E1/
corpo $D/p /organizador/eventos/$E1/ | grep -c 'data-metrica'
ver $D/v /organizador/eventos/$E1/
```

Esperado: status 302 e `location: /organizador/`; status 404; `0`; status 403; `0`; status 302 e `location: /contas/entrar/?next=/organizador/eventos/<E1>/`.

### C-09 — (F06-CA04) Números só do domínio, sem regra no template

```bash
P=web/templates/web/organizador/gestao
grep -cE '\{% *(if|for|with)|\|(add|length)' $P/_painel_conteudo.html
grep -c 'data-metrica=' $P/_painel_conteudo.html
grep 'data-metrica=' $P/_painel_conteudo.html | grep -vcE '<dd data-metrica="[a-z-]+">\{\{ painel\.[a-z_]+( ?\| ?reais)? \}\}</dd>'
grep -cF '{% bloco_painel evento %}' $P/_painel.html
grep -cF 'painel_do_evento(evento)' web/templatetags/painel.py
grep -cE "objects\.|filter\(|aggregate\(|Count\(|Sum\(|\.count\(" web/templatetags/painel.py
```

Esperado: `0` (o template não decide nem soma nada); `6`; `0` (cada `data-metrica` mostra só um campo de `painel`, a receita com o filtro `reais`); `1` (o parcial da gestão usa a tag); `1` (a tag entrega `painel_do_evento(evento)` ao template); `0` (a tag não consulta o ORM).

### C-10 — Testes automatizados da feature

```bash
./scripts/gates.sh -v dominio/tests/test_painel.py web/tests/test_painel.py; echo "código: $?"
```

Esperado: "código: 0", nenhum "FAILED" nem "SKIPPED", e como PASSED (com ou sem sufixo `[...]`) pelo menos: `test_painel_de_evento_sem_ingressos`, `test_painel_conta_cada_status_pela_definicao`, `test_check_ins_so_de_confirmados`, `test_receita_soma_o_preco_gravado_de_cada_confirmado`, `test_receita_ignora_pendentes_recusados_cancelados_e_estornados`, `test_vitrine_e_api_contam_igual`, `test_vagas_disponiveis_segue_r05_e_zera_em_cancelado`, `test_painel_usa_uma_consulta_agregada` (em `dominio/tests/test_painel.py`); `test_bloco_painel_na_gestao_com_rotulos_e_metricas`, `test_receita_no_formato_reais`, `test_recarregar_mostra_estado_atual`, `test_outro_organizador_nao_ve_o_painel` (em `web/tests/test_painel.py`).

Ao terminar: `CATRACA_PORTA=$PORTA ./scripts/down.sh` e `rm -rf "$D"`.

## 3. Mapeamento critério do PRD → itens

| Critério do PRD | Itens |
|---|---|
| F06-CA01 — (R12, R04) Bloco com os seis rótulos e `data-metrica`; receita "R$ 350,00" | C-02, C-03, C-10 |
| F06-CA02 — (R12, R05) Definições de cada número (Check-ins só de confirmados; vagas zero em cancelado); recusados e cancelados fora | C-04, C-05, C-07, C-10 |
| F06-CA03 — (R12, R03) Receita = soma do preço gravado dos confirmados; pendentes, recusados e estornados não somam | C-03, C-07, C-10 |
| F06-CA04 — (R12) Números só de `painel_do_evento`; recarregar mostra o estado atual | C-03, C-04, C-09, C-10 |
| F06-CA05 — (R13) Outro organizador: 404 sem `#painel` | C-08, C-10 |
| XF-09 [F02→F06] — Vagas acompanham a lotação editada (0 → 1) | C-03 |
| XF-10 [F03→F06] — 3 confirmados com R$ 350,00; 0004 em Pendentes e depois em nenhum número | C-03, C-04 |
| XF-11 [F04→F06] — Rajada pela API: Confirmados 5 e Vagas 0 em até 10 s; 0003 pela API em Pendentes | C-04, C-06, C-03 |
| XF-12 [F05→F06] — Check-in sobe Check-ins sem mudar Confirmados e Receita; rejeitados não mudam nada | C-05 |
| XF-13 [F04+F05→F06] — Ingresso da API confirmado passa no check-in com o code do 202, `checkedIn: true`, conta em Confirmados, Check-ins e Receita; code de outro evento é inválido | C-05 |

## 4. Fora deste contrato

- Cancelamento de verdade e estornos gerados por ele (F07; XF-18 e XF-19). Aqui o estorno e o cancelado do C-07 são só preparação de estado no banco.
