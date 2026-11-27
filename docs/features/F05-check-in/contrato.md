# Contrato — F05 Check-in

> O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item, na ordem. Textos esperados vão entre aspas, exatos, e são conferidos com `grep -F` (`grep -c` conta **linhas** que contêm o texto).

- Feature: F05 — Check-in (wave W4, paralela à F04)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (F05-CA01…CA08) e 7 (XF-07, XF-08)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- **Antes de tudo**, na raiz do repositório (ou da worktree): `git rev-parse HEAD` precisa imprimir exatamente o sha completo pedido para a avaliação, e `git status --porcelain` precisa sair vazio. Se um dos dois não bater, o avaliador **para**, registra no relatório as duas saídas e não avalia nenhum item.
- Commit avaliado: o sha informado no pedido de avaliação (branch `feat/F05-check-in`).
- Ferramentas no host: Docker, Git, `curl`, **bash** e os utilitários `awk`, `sed`, `grep` (com `-o`), `cut`, `sort`, `uniq`, `xargs`, `seq`, `tr`, `paste`, `wc`, `cmp` e `sleep`. Navegador é opcional. A API de parceiros (F04) não é usada: as compras são feitas na vitrine.
- Contas da seed (README, "Credenciais"): `org.a@catraca.test`, `org.b@catraca.test` e `participante@catraca.test`, todas com a senha `catraca123`.
- **Tempo.** A execução completa leva uns 2 minutos, mais os gates. Os ingressos com final `0003` (aprovação lenta, 32–38 s) são conferidos como pendentes logo depois da compra, bem antes dos 30 s; não rode os itens C-03 a C-06 com pausas longas entre eles, nem o C-12 em partes.
- **Evento cancelado.** O cancelamento é da F07, que ainda não existe. O item C-12 **prepara** um evento cancelado direto no banco (`update dominio_evento set status = 'cancelado'`, e dois ingressos passados a `refunded` e `cancelled`, como a F07 fará); isso é só preparação de estado, não comportamento avaliado.
- **Porta.** Vem de `CATRACA_PORTA` (padrão 8000) e é a mesma na subida, nos itens e na descida.
- **Banco zerado**, na raiz:

```bash
PORTA=${CATRACA_PORTA:-8000}
docker compose --profile '*' down -v          # apaga só o volume deste projeto
CATRACA_PORTA=$PORTA ./scripts/up.sh          # código 0 e "Catraca no ar."
```

O banco começa sem eventos e sem ingressos.

- **Funções e estado.** Rode uma vez o bloco abaixo, em bash. Ele grava as funções em `$D/f.sh` e as variáveis criadas pelos itens (ids e códigos) em `$D/ids`. Os itens rodam **na ordem**; contagens e variáveis dependem dela. Se um item for rodado num **shell novo**, antes dele rode: `PORTA=${CATRACA_PORTA:-8000}; D=/tmp/catraca-F05-$PORTA; . $D/f.sh; . $D/ids`.

```bash
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F05-$PORTA; rm -rf "$D"; mkdir -p "$D"; : > "$D/ids"
cat > "$D/f.sh" <<'FIM'
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F05-$PORTA
export WEB=http://localhost:$PORTA
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
# comprar <cookies> <evento> <cartão>: POST de compra na vitrine com CSRF; imprime status e Location
comprar()   { curl -s -o /dev/null -b "$1" -c "$1" "$WEB/contas/entrar/"
              curl -s -o "$1.html" -D - -b "$1" -c "$1" \
                --data-urlencode "csrfmiddlewaretoken=$(csrf "$1")" --data-urlencode "cartao=$3" \
                "$WEB/eventos/$2/comprar/" | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
# códigos dos ingressos de Meus ingressos (num arquivo salvo), do mais novo para o mais antigo
codigos()   { grep -oE 'data-campo="codigo">[A-Z0-9]{8}<' "$1" | cut -d'>' -f2 | tr -d '<'; }
# linha de Meus ingressos (num arquivo salvo) com o código; cada <tr> fica numa linha só do HTML
linha()     { grep -F "data-campo=\"codigo\">$2<" "$1"; }
# compra <evento> <cartão>: o participante da seed ($D/p) compra na vitrine; imprime status e
# Location e salva Meus ingressos logo depois em $D/mi.html; novo: código mais recente dessa página
compra()    { comprar $D/p "$1" "$2"; corpo $D/p /meus-ingressos/ > $D/mi.html; }
novo()      { codigos $D/mi.html | head -n 1; }
# checkin <cookies> <evento> <código>: POST no formulário do bloco #check-in, com CSRF; imprime o
# status, o Location (se houver) e o elemento #check-in-mensagem inteiro, ou "sem mensagem";
# o corpo fica em <cookies>.html
checkin()   { curl -s -o /dev/null -b "$1" -c "$1" "$WEB/contas/entrar/"
              curl -s -o "$1.html" -D - -b "$1" -c "$1" \
                --data-urlencode "csrfmiddlewaretoken=$(csrf "$1")" --data-urlencode "codigo=$3" \
                "$WEB/organizador/eventos/$2/check-in/" | tr -d '\r' | grep -iE '^(HTTP/|location:)'
              grep -oE '<p id="check-in-mensagem">[^<]*</p>' "$1.html" || echo "sem mensagem"; }
# ingresso <código>: status e se tem check-in (t/f), lidos do banco
ingresso()  { sql "select status, check_in_em is not null from dominio_ingresso where codigo = '$1'"; }
quando()    { sql "select check_in_em from dominio_ingresso where codigo = '$1'"; }
FIM
. "$D/f.sh"
```

"Status 200 sem `location:`" quer dizer: a linha `HTTP/1.1 200 …` e nenhum cabeçalho `Location`. "Status 302 e `location: /x`" quer dizer a linha `HTTP/1.1 302 …` e o cabeçalho `Location` com o valor exato `/x`. Uma resposta de `checkin` "→ M" quer dizer: status 200 sem `location:` e, na linha seguinte, exatamente `<p id="check-in-mensagem">M</p>`. `<E1>`, `<C1>` etc. são os valores impressos no item que os criou. Em `/contas/entrar/` o `comprar` e o `checkin` só fazem um `GET` para garantir o cookie `csrftoken`.

## 2. Itens verificáveis

### C-01 — Gates

```bash
./scripts/gates.sh; echo "código: $?"
```

Esperado: "código: 0"; ruff sem erros, `manage.py check` sem problemas, "No changes detected" no `makemigrations --check`, pytest sem falhas, última etapa "==> gates: OK".

### C-02 — (F05-CA08, XF-07, R04, R13) Bloco `#check-in` na gestão do dono; `GET` 405; visitante e participante barrados

```bash
entrar $D/a org.a@catraca.test
E1=$(novo_evento $D/a "Check-in Principal" "2027-08-10T21:00" 10 "100,00"); guardar E1 "$E1"; echo "$E1"
echo "$E1" | grep -cE '^evt_[a-z0-9]{8}$'
corpo $D/a /organizador/eventos/$E1/ > $D/g1.html
sed -n '/<section id="check-in">/,/<\/section>/p' $D/g1.html > $D/bloco.html
grep -c '<section id="check-in">' $D/g1.html
grep -cF "<form id=\"form-check-in\" method=\"post\" action=\"/organizador/eventos/$E1/check-in/\">" $D/bloco.html
grep -c 'name="codigo"' $D/bloco.html; grep -c 'name="csrfmiddlewaretoken"' $D/bloco.html
grep -c 'id="check-in-mensagem"' $D/g1.html
ver $D/a /organizador/eventos/$E1/check-in/
ver $D/v /organizador/eventos/$E1/check-in/
checkin $D/v "$E1" ZZZZZZZZ
entrar $D/p participante@catraca.test
ver $D/p /organizador/eventos/$E1/check-in/
checkin $D/p "$E1" ZZZZZZZZ
```

Esperado:
- login de A: status 302 e `location: /organizador/`; um id `evt_…`; `1` (o id tem o formato `evt_` + 8 caracteres de `[a-z0-9]`);
- `1`; `1` (formulário com `POST` para a URL de check-in do evento); `1`; `1` (campo `codigo` e token CSRF dentro do bloco); `0` (sem mensagem antes de um envio);
- `GET` do organizador na URL de check-in: status 405;
- visitante: `GET` com status 302 e `location: /contas/entrar/?next=/organizador/eventos/<E1>/check-in/`; `POST` com status 302, `location: /contas/entrar/` e "sem mensagem";
- login do participante: status 302 e `location: /`; `GET` com status 403; `POST` com status 403 e "sem mensagem".

### C-03 — (XF-08, R09) Preparação: compras na vitrine e códigos de Meus ingressos

```bash
E2=$(novo_evento $D/a "Outro Evento de A" "2027-08-11T21:00" 5 "50,00"); guardar E2 "$E2"
entrar $D/b org.b@catraca.test
E3=$(novo_evento $D/b "Evento de B" "2027-08-12T21:00" 5 "80,00"); guardar E3 "$E3"; echo "$E2 $E3"
printf '%s\n' "$E2" "$E3" | grep -E '^evt_[a-z0-9]{8}$' | sort -u | wc -l
compra "$E1" 4000000000000001; C1=$(novo); guardar C1 "$C1"
compra "$E1" 4000000000000002; C3=$(novo); guardar C3 "$C3"
compra "$E1" 4000000000000001; C4=$(novo); guardar C4 "$C4"
compra "$E1" 4000000000000001; C5=$(novo); guardar C5 "$C5"
compra "$E2" 4000000000000001; C6=$(novo); guardar C6 "$C6"
compra "$E3" 4000000000000001; C7=$(novo); guardar C7 "$C7"
echo "$C1 $C3 $C4 $C5 $C6 $C7"
printf '%s\n' "$C1" "$C3" "$C4" "$C5" "$C6" "$C7" | grep -E '^[A-Z0-9]{8}$' | sort -u | wc -l
sleep 5
corpo $D/p /meus-ingressos/ > $D/mi-prep.html
for c in $C1 $C3 $C4 $C5 $C6 $C7; do linha $D/mi-prep.html "$c" | grep -oE 'data-campo="(evento|status)">[^<]*<' | paste -sd ' ' -; done
sql "select count(*) from dominio_ingresso where check_in_em is not null"
```

Esperado:
- login de B: status 302 e `location: /organizador/`; dois ids `evt_…`; o número `2` (com ou sem espaços à esquerda: dois ids distintos no formato `evt_` + 8 de `[a-z0-9]`);
- seis compras, cada uma com status 302 e `location: /meus-ingressos/`; seis códigos; o número `6` (com ou sem espaços à esquerda: seis códigos distintos de 8 caracteres de `[A-Z0-9]`);
- seis linhas, nesta ordem (`C1`, `C3`, `C4`, `C5`, `C6`, `C7`; o `C2`, pendente, é comprado no C-06):
  1. `data-campo="evento">Check-in Principal< data-campo="status">confirmado<`
  2. `data-campo="evento">Check-in Principal< data-campo="status">recusado<` (final `0002`)
  3. `data-campo="evento">Check-in Principal< data-campo="status">confirmado<`
  4. `data-campo="evento">Check-in Principal< data-campo="status">confirmado<`
  5. `data-campo="evento">Outro Evento de A< data-campo="status">confirmado<`
  6. `data-campo="evento">Evento de B< data-campo="status">confirmado<`
- `0` (nenhum check-in ainda).

### C-04 — (F05-CA06, XF-08, R10 item 5) Confirmado sem check-in → "Entrada liberada"

```bash
ingresso "$C1"
checkin $D/a "$E1" "$C1"
ingresso "$C1"
grep -c 'id="check-in-mensagem"' $D/a.html; grep -c 'id="evento-dados"' $D/a.html; grep -c 'id="form-check-in"' $D/a.html
grep 'name="codigo"' $D/a.html | grep -c 'value='; grep -cF "$C1" $D/a.html
corpo $D/a /organizador/eventos/$E1/ | grep -c 'id="check-in-mensagem"'
```

Esperado: `confirmed|f`; → "Entrada liberada"; `confirmed|t` (`check_in_em` gravado, status continua `confirmed`); `1`; `1`; `1` (a resposta é a página de gestão inteira, com uma única mensagem e o formulário pronto para o próximo código); `0` (o campo `codigo` volta vazio, sem atributo `value`); `0` (o código enviado não é ecoado na página); `0` (recarregar a gestão com `GET` não mostra mensagem).

### C-05 — (F05-CA05, R10 item 4) Já passou pelo check-in → "Ingresso já utilizado"

```bash
Q1=$(quando "$C1")
checkin $D/a "$E1" "$C1"
Q2=$(quando "$C1"); [ -n "$Q1" ] && [ "$Q1" = "$Q2" ] && echo "check_in_em mantido"
ingresso "$C1"
```

Esperado: → "Ingresso já utilizado"; "check_in_em mantido" (o horário do primeiro check-in não muda); `confirmed|t`.

### C-06 — (F05-CA04, XF-08, R10 item 3) Pendente (final `0003`) e recusado → "Ingresso não confirmado"

O ingresso pendente é comprado aqui mesmo, segundos antes do check-in (a aprovação do final `0003` leva 32–38 s).

```bash
compra "$E1" 4000000000000003; C2=$(novo); guardar C2 "$C2"
echo "$C2" | grep -cE '^[A-Z0-9]{8}$'
linha $D/mi.html "$C2" | grep -oE 'data-campo="(evento|status)">[^<]*<' | paste -sd ' ' -
ingresso "$C2"
checkin $D/a "$E1" "$C2"; ingresso "$C2"
checkin $D/a "$E1" "$C3"; ingresso "$C3"
```

Esperado: compra com status 302 e `location: /meus-ingressos/`; `1`; `data-campo="evento">Check-in Principal< data-campo="status">pendente<` (o código como aparece em Meus ingressos); `pending|f`; → "Ingresso não confirmado"; `pending|f`; → "Ingresso não confirmado" (`C3`, recusado); `declined|f`.

### C-07 — (F05-CA01, R10 item 1) Código inexistente → "Ingresso inválido para este evento"

```bash
for c in ZZZZZZZZ zzzzzzzz "" "${C4}A" "${C4:0:7}"; do checkin $D/a "$E1" "$c"; done
ingresso "$C4"
ER=$(postar $D/a /organizador/eventos/novo/ "nome=Rascunho" "inicio=2027-08-14T21:00" "local=Sala" "lotacao=5" "preco=10,00" | idde); guardar ER "$ER"; echo "$ER"
sql "select status from dominio_evento where id_publico = '$ER'"
checkin $D/a "$ER" ZZZZZZZZ; checkin $D/a "$ER" "$C4"
```

Esperado: cinco vezes → "Ingresso inválido para este evento" (`ZZZZZZZZ`, o mesmo em minúsculas, vazio, um código válido com um caractere a mais e com um a menos); `confirmed|f` (nada mudou no ingresso cujo código foi usado de base); um id `evt_…`; `rascunho`; no evento em rascunho (que não vende), duas vezes → "Ingresso inválido para este evento".

### C-08 — (F05-CA02, XF-08, R10 item 1) Código de outro evento, confirmado, do mesmo organizador e de outro → "Ingresso inválido para este evento"

```bash
checkin $D/a "$E1" "$C6"
checkin $D/a "$E1" "$C7"
ingresso "$C6"; ingresso "$C7"
```

Esperado: → "Ingresso inválido para este evento" (`C6`, do E2 de A); → "Ingresso inválido para este evento" (`C7`, do E3 de B); `confirmed|f`; `confirmed|f`.

### C-09 — (F05-CA08) Espaços nas pontas e minúsculas são normalizados

```bash
MIN=$(echo "$C6" | tr 'A-Z' 'a-z'); echo "[  $MIN  ]"
checkin $D/a "$E2" "  $MIN  "
ingresso "$C6"
checkin $D/a "$E2" " $C6"
```

Esperado: o código de `C6` em minúsculas entre dois espaços de cada lado; → "Entrada liberada"; `confirmed|t`; → "Ingresso já utilizado" (o mesmo ingresso, agora com um espaço à esquerda).

### C-10 — (F05-CA08, XF-07, R13) Outro organizador: 404 sem efeito e sem mensagem sobre o ingresso

```bash
checkin $D/b "$E1" "$C4"
grep -cE 'Ingresso inválido para este evento|Evento cancelado|Ingresso não confirmado|Ingresso já utilizado|Entrada liberada' $D/b.html
grep -c 'check-in' $D/b.html; grep -cF 'Check-in Principal' $D/b.html; grep -cF "$C4" $D/b.html
grep -cF '<h2>Página não encontrada</h2>' $D/b.html
ingresso "$C4"
checkin $D/b evt_zzzzzzzz "$C4"
checkin $D/a "$E1" "$C4"
```

Esperado:
- B no evento E1 de A: status 404 e "sem mensagem"; `0` (nenhuma das cinco mensagens); `0`; `0`; `0` (nem bloco de check-in, nem nome do evento, nem o código); `1` (a página 404 genérica);
- `confirmed|f` (nada mudou);
- B num evento inexistente: status 404 e "sem mensagem";
- o dono, com o mesmo código: → "Entrada liberada" (o código era válido; o 404 veio só do dono do evento).

### C-11 — (F05-CA07, R10) Dez check-ins simultâneos do mesmo código pela tela

```bash
ingresso "$C5"
TOKEN=$(csrf $D/a)
seq 10 | xargs -P 10 -I{} curl -s -o "$D/ci_{}.html" -w "%{http_code}\n" -b $D/a \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN" --data-urlencode "codigo=$C5" \
  "$WEB/organizador/eventos/$E1/check-in/" | sort | uniq -c
grep -lF '<p id="check-in-mensagem">Entrada liberada</p>' $D/ci_*.html | wc -l
grep -lF '<p id="check-in-mensagem">Ingresso já utilizado</p>' $D/ci_*.html | wc -l
ingresso "$C5"
```

Esperado: `confirmed|f`; exatamente uma linha de contagem, `10 200` (com espaços à esquerda do número); o número `1` e o número `9` (com ou sem espaços à esquerda): exatamente uma resposta liberou a entrada e as outras nove disseram "Ingresso já utilizado"; `confirmed|t`.

### C-12 — (F05-CA03, F05-CA02, R10 itens 1 e 2) Evento cancelado: o campo continua e vale a lista

```bash
E4=$(novo_evento $D/a "Será Cancelado" "2027-08-13T21:00" 10 "100,00"); guardar E4 "$E4"; echo "$E4"
echo "$E4" | grep -cE '^evt_[a-z0-9]{8}$'
compra "$E4" 4000000000000001; K1=$(novo); guardar K1 "$K1"
compra "$E4" 4000000000000001; K2=$(novo); guardar K2 "$K2"
compra "$E4" 4000000000000001; K3=$(novo); guardar K3 "$K3"
compra "$E4" 4000000000000002; K4=$(novo); guardar K4 "$K4"
compra "$E4" 4000000000000003; K6=$(novo); guardar K6 "$K6"
sleep 5
checkin $D/a "$E4" "$K1"; checkin $D/a "$E4" "$K3"
compra "$E4" 4000000000000003; K5=$(novo); guardar K5 "$K5"
printf '%s\n' "$K1" "$K2" "$K3" "$K4" "$K5" "$K6" | grep -E '^[A-Z0-9]{8}$' | sort -u | wc -l
# preparação de estado (o cancelamento é da F07):
sql "update dominio_evento set status = 'cancelado' where id_publico = '$E4'"
sql "update dominio_ingresso set status = 'refunded' where codigo = '$K3'"
sql "update dominio_ingresso set status = 'cancelled' where codigo = '$K6'"
sql "select codigo, status, check_in_em is not null from dominio_ingresso where codigo in ('$K1', '$K2', '$K3', '$K4', '$K5', '$K6') order by id"
sql "select codigo, check_in_em from dominio_ingresso order by id" > $D/antes
corpo $D/a /organizador/eventos/$E4/ > $D/g4.html
grep -oE 'data-campo="status">[^<]*<' $D/g4.html; grep -c 'id="form-check-in"' $D/g4.html; grep -c 'name="codigo"' $D/g4.html
for k in $K5 $K1 $K2 $K3 $K4 $K6; do checkin $D/a "$E4" "$k"; done
checkin $D/a "$E4" "$C7"
checkin $D/a "$E4" "$C5"
checkin $D/a "$E4" ZZZZZZZZ
sql "select codigo, check_in_em from dominio_ingresso order by id" > $D/depois
cmp -s $D/antes $D/depois && echo "nada mudou"
```

Esperado:
- um id `evt_…`; `1`; seis compras ao todo, cada uma com status 302 e `location: /meus-ingressos/` (K5, final `0003`, é a última, feita pouco antes do cancelamento);
- antes do cancelamento: → "Entrada liberada" (`K1`) e → "Entrada liberada" (`K3`);
- o número `6` (com ou sem espaços à esquerda: seis códigos distintos de 8 caracteres de `[A-Z0-9]`);
- as três atualizações de preparação imprimem `UPDATE 1` cada;
- uma única consulta com seis linhas, nesta ordem (por id): `<K1>|confirmed|t`, `<K2>|confirmed|f`, `<K3>|refunded|t`, `<K4>|declined|f`, `<K6>|cancelled|f`, `<K5>|pending|f`;
- a gestão do evento cancelado: `data-campo="status">Cancelado<`; `1`; `1` (o formulário de check-in continua);
- seis vezes → "Evento cancelado" (K5 pendente, K1 confirmado com check-in, K2 confirmado sem check-in, K3 estornado com check-in, K4 recusado, K6 cancelado);
- → "Ingresso inválido para este evento" (`C7`, confirmado do evento de B, sem check-in); → "Ingresso inválido para este evento" (`C5`, confirmado de outro evento de A, com check-in); → "Ingresso inválido para este evento" (`ZZZZZZZZ`);
- "nada mudou" (nenhum `check_in_em` de nenhum ingresso mudou com esses nove envios).

### C-13 — (F05-CA07) Teste de concorrência contra o Postgres

```bash
./scripts/gates.sh -v dominio/tests/test_checkin_concorrencia.py; echo "código: $?"
for p in 'CHECK_INS_SIMULTANEOS = 10' 'RODADAS = 10' 'threading.Barrier(CHECK_INS_SIMULTANEOS)' 'connection.close()'; do
  grep -qF "$p" dominio/tests/test_checkin_concorrencia.py && echo "ok: $p"
done
```

Esperado: "código: 0" com `test_check_ins_simultaneos_liberam_uma_unica_vez PASSED` (10 threads liberadas juntas por uma barreira, cada uma com a sua conexão, fazem o check-in do mesmo código confirmado: exatamente 1 "Entrada liberada" e 9 "Ingresso já utilizado", repetido em 10 ingressos novos); quatro linhas, exatamente `ok: CHECK_INS_SIMULTANEOS = 10`, `ok: RODADAS = 10`, `ok: threading.Barrier(CHECK_INS_SIMULTANEOS)` e `ok: connection.close()`.

### C-14 — Testes automatizados da feature

```bash
./scripts/gates.sh -v dominio/tests/test_checkin.py web/tests/test_checkin.py web/tests/test_acesso.py; echo "código: $?"
```

Esperado: "código: 0", nenhum "FAILED" nem "SKIPPED", e como PASSED (com ou sem sufixo `[...]`) pelo menos: `test_resultado_check_in_tem_as_cinco_mensagens_exatas_na_ordem`, `test_codigo_inexistente_e_invalido`, `test_codigo_de_outro_evento_e_invalido`, `test_codigo_de_outro_evento_em_evento_cancelado_e_invalido`, `test_evento_cancelado_vem_antes_do_status_e_do_check_in`, `test_ingresso_nao_confirmado` (os quatro status não confirmados, com e sem `check_in_em`, num evento publicado), `test_ingresso_ja_utilizado`, `test_entrada_liberada_grava_check_in_e_mantem_confirmado`, `test_codigo_normalizado`, `test_codigo_mal_formado_e_invalido`, `test_evento_em_rascunho_so_tem_codigos_invalidos`, `test_evento_de_outro_organizador_ou_inexistente_lanca_sem_efeito`, `test_check_in_trava_evento_e_depois_ingresso`, `test_resultados_rejeitados_nao_escrevem` (em `dominio/tests/test_checkin.py`); `test_gestao_do_dono_mostra_bloco_check_in`, `test_check_in_pela_tela_mostra_cada_mensagem`, `test_check_in_pela_tela_normaliza_o_codigo`, `test_check_in_de_outro_organizador_responde_404_sem_efeito`, `test_check_in_de_visitante_e_participante_e_barrado_sem_efeito`, `test_check_in_por_get_responde_405`, `test_evento_cancelado_mantem_o_campo_e_responde_evento_cancelado`, `test_resposta_do_check_in_e_a_gestao_inteira` (em `web/tests/test_checkin.py`); `test_rotas_do_organizador_barram_visitante_e_participante` (em `web/tests/test_acesso.py`, que percorre todas as rotas sob `/organizador/`, inclusive a de check-in).

### C-15 — Camadas e travas (regra 1 do AGENTS.md; F05-CA07)

```bash
grep -cE 'objects\.|\.save\(|\.update\(|check_in_em|select_for_update' web/views/checkin.py
grep -A1 '^@organizador_requerido$' web/views/checkin.py
sed -n '/^def fazer_check_in/,$p' dominio/servicos/checkin.py | grep -c 'select_for_update()'
sed -n '/^def fazer_check_in/,$p' dominio/servicos/checkin.py | grep -c 'transaction.atomic()'
```

Esperado: `0` (a view não lê nem grava no banco; só chama o domínio); duas linhas, exatamente `@organizador_requerido` e `@require_POST` (a guarda é o decorador mais externo); `2` (o check-in trava o evento e o ingresso); `1` (numa única transação).

Ao terminar: `CATRACA_PORTA=$PORTA ./scripts/down.sh` e `rm -rf "$D"`.

## 3. Mapeamento critério do PRD → itens

| Critério do PRD | Itens |
|---|---|
| F05-CA01 — (R10 item 1) Código inexistente → "Ingresso inválido para este evento" | C-07, C-12, C-14 |
| F05-CA02 — (R10 item 1 antes do 2) Código de outro evento (mesmo organizador ou outro), confirmado, inclusive em evento cancelado → "Ingresso inválido para este evento" | C-08, C-12, C-14 |
| F05-CA03 — (R10 item 2 antes do 3 e do 4) Evento cancelado, ingresso dele em qualquer status, com ou sem check-in → "Evento cancelado"; o campo continua | C-12, C-14 |
| F05-CA04 — (R10 item 3) Publicado, `pending` ou `declined` → "Ingresso não confirmado" | C-06, C-14 |
| F05-CA05 — (R10 item 4) Confirmado com check-in → "Ingresso já utilizado" | C-05, C-09, C-14 |
| F05-CA06 — (R10 item 5) Confirmado sem check-in → "Entrada liberada"; `check_in_em` gravado; continua `confirmed` | C-04, C-14 |
| F05-CA07 — (R10) Atomicidade: 10 threads, 1 liberada e 9 já utilizado, 10 ingressos | C-13, C-11, C-15 |
| F05-CA08 — (R04, R10, R13) Bloco na gestão do dono; normalização; outro organizador → 404 sem efeito e sem mensagem | C-02, C-09, C-10, C-14, C-15 |
| XF-07 [F02→F05] — Bloco `#check-in` na gestão do dono; B na URL de check-in de um evento de A → 404 e nada muda | C-02, C-10 |
| XF-08 [F03→F05] — Código de Meus ingressos: confirmado → "Entrada liberada"; pendente (`0003`) → "Ingresso não confirmado"; de outro evento → "Ingresso inválido para este evento" | C-03, C-04, C-06, C-08 |

## 4. Fora deste contrato

- Cancelar o evento pela tela e o efeito do cancelamento nos ingressos (F07; aqui o evento cancelado é só preparado no banco), inclusive XF-17 e XF-19.
- Check-ins no painel (F06: XF-12, XF-13) e `checkedIn` na API de parceiros (F04, que lê o mesmo `check_in_em`; a combinação é provada no XF-13).
