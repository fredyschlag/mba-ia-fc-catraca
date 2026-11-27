# Contrato — F03 Compra, lotação e gateway

> O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item, na ordem. Textos esperados vão entre aspas, exatos, e são conferidos com `grep -F` (`grep -c` conta **linhas** que contêm o texto).

- Feature: F03 — Compra, lotação e gateway (wave W3)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (F03-CA01…CA14) e 7 (XF-02, XF-03, XF-04)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- **Antes de tudo**, na raiz do repositório (ou da worktree): `git rev-parse HEAD` precisa imprimir exatamente o sha completo pedido para a avaliação, e `git status --porcelain` precisa sair vazio. Se um dos dois não bater, o avaliador **para**, registra no relatório as duas saídas e não avalia nenhum item.
- Commit avaliado: o sha informado no pedido de avaliação (branch `feat/F03-compra-lotacao-gateway`).
- Ferramentas no host: Docker, Git, `curl`, **bash** e os utilitários `awk`, `sed`, `grep`, `cut`, `sort`, `uniq`, `xargs`, `seq`, `tr`, `date` (`date +%s`) e `sleep`. Navegador é opcional.
- Contas da seed (README, "Credenciais"): `org.a@catraca.test` e `participante@catraca.test`, com a senha `catraca123`.
- **Tempo.** O item C-06 espera os cartões lentos (cerca de 45 s) e o C-15 derruba e sobe o ambiente. A execução completa leva uns 4 minutos, sem contar os gates. Os itens que conferem "pendente" logo depois de uma compra usam um retrato salvo com `curl` imediatamente depois dela, e os prazos do gateway ("em até 5 s", "pendente aos 30 s") são medidos no banco pela diferença entre a criação do ingresso e o processamento da cobrança, para não depender da velocidade do `docker compose exec`.
- **Porta.** Vem de `CATRACA_PORTA` (padrão 8000) e é a mesma na subida, nos itens e na descida.
- **Banco zerado**, na raiz:

```bash
PORTA=${CATRACA_PORTA:-8000}
docker compose --profile '*' down -v          # apaga só o volume deste projeto
CATRACA_PORTA=$PORTA ./scripts/up.sh          # código 0 e "Catraca no ar."
```

O banco começa sem eventos e sem ingressos.

- **Funções e estado.** Rode uma vez o bloco abaixo, em bash. Ele grava as funções em `$D/f.sh` e as variáveis criadas pelos itens (ids e códigos) em `$D/ids`. Os itens rodam **na ordem**; contagens e variáveis dependem dela. Se um item for rodado num **shell novo**, antes dele rode: `PORTA=${CATRACA_PORTA:-8000}; D=/tmp/catraca-F03-$PORTA; . $D/f.sh; . $D/ids`.

```bash
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F03-$PORTA; rm -rf "$D"; mkdir -p "$D"; : > "$D/ids"
cat > "$D/f.sh" <<'FIM'
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F03-$PORTA
export WEB=http://localhost:$PORTA
sql()       { docker compose exec -T db psql -U catraca -d catraca -tAc "$1"; }
ingressos() { sql "select count(*) from dominio_ingresso"; }
cobrancas() { sql "select count(*) from dominio_cobrancagateway"; }
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
# comprar <cookies> <evento> <cartão>: POST de compra na vitrine com CSRF;
# imprime status, Location e "tempo=<segundos>"; o corpo fica em <cookies>.html
comprar()   { curl -s -o /dev/null -b "$1" -c "$1" "$WEB/contas/entrar/"
              curl -s -o "$1.html" -D - -w 'tempo=%{time_total}\n' -b "$1" -c "$1" \
                --data-urlencode "csrfmiddlewaretoken=$(csrf "$1")" --data-urlencode "cartao=$3" \
                "$WEB/eventos/$2/comprar/" | tr -d '\r' | grep -iE '^(HTTP/|location:|tempo=)'; }
# código do ingresso mais recente do evento
ultimo()    { sql "select i.codigo from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico = '$1' order by i.id desc limit 1"; }
status()    { sql "select status from dominio_ingresso where codigo = '$1'"; }
# linha de Meus ingressos (num arquivo salvo) com o código; cada <tr> fica numa linha só do HTML
linha()     { grep -F "data-campo=\"codigo\">$2<" "$1"; }
# códigos dos ingressos de Meus ingressos (num arquivo salvo), do mais novo para o mais antigo
codigos()   { grep -oE 'data-campo="codigo">[A-Z0-9]{8}<' "$1" | cut -d'>' -f2 | tr -d '<'; }
# tempo entre a compra e o processamento da cobrança, conferido no banco: imprime status|t ou status|f
prazo()     { sql "select i.status, (c.processada_em - i.criado_em) $2 from dominio_ingresso i join dominio_cobrancagateway c on c.ingresso_id = i.id where i.codigo = '$1'"; }
vagas()     { corpo "$1" "/eventos/$2/" | grep -oE 'data-campo="vagas-disponiveis">[0-9]+<'; }
FIM
. "$D/f.sh"
```

"Status 302 e `location: /x`" quer dizer: a linha `HTTP/1.1 302 …` e o cabeçalho `Location` com o valor exato `/x`. "Sem `location:`" quer dizer sem redirecionamento. `<E1>`, `<C1>` etc. nos resultados esperados são os valores impressos no item que os criou. Em `/contas/entrar/` o `comprar` só faz um `GET` para garantir o cookie `csrftoken`.

## 2. Itens verificáveis

### C-01 — Gates

```bash
./scripts/gates.sh; echo "código: $?"
```

Esperado: "código: 0", pytest sem falhas, última etapa "==> gates: OK".

### C-02 — (F03-CA13, XF-03, R02) Rascunho, inexistente e organizador não compram

```bash
entrar $D/a org.a@catraca.test
E1=$(postar $D/a /organizador/eventos/novo/ "nome=Show Dois" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=2" "preco=100,00" | idde); guardar E1 "$E1"; echo "$E1"
postar $D/n /contas/cadastro/ "nome=Nina Nova" "email=nina@example.com" "senha=Senha-Nina-123"
comprar $D/n "$E1" 4000000000000001
comprar $D/n evt_zzzzzzzz 4000000000000001
comprar $D/v "$E1" 4000000000000001
comprar $D/a "$E1" 4000000000000001
ingressos; cobrancas
```

Esperado: login de A com status 302 e `location: /organizador/`; um id `evt_…`; cadastro de Nina com status 302 e `location: /`; compra no rascunho: status 404 (e uma linha `tempo=…`); no inexistente: status 404; visitante: status 302 e `location: /contas/entrar/`; organizador: status 403; `0` e `0`.

### C-03 — (F03-CA01, F03-CA02, XF-03, XF-02, R06, R08, R09) Publicar, aparecer na vitrine, comprar, pendente e confirmado em até 5 s

```bash
postar $D/a /organizador/eventos/$E1/publicar/
corpo $D/v / | grep -cF "href=\"/eventos/$E1/\""
corpo $D/n /eventos/$E1/ > $D/det.html
grep -c 'id="compra"' $D/det.html; grep -c 'id="form-compra"' $D/det.html; grep -c 'name="cartao"' $D/det.html; vagas $D/n "$E1"
comprar $D/n "$E1" 4000000000000001; corpo $D/n /meus-ingressos/ > $D/mi1.html
C1=$(codigos $D/mi1.html | head -n 1); guardar C1 "$C1"; echo "$C1"
linha $D/mi1.html "$C1"
comprar $D/v "$E1" 4000000000000001
sql "select i.valor_centavos, i.cartao_final, i.canal, i.email_comprador, u.email from dominio_ingresso i join dominio_usuario u on u.id = i.comprador_id where i.codigo = '$C1'"
ingressos
sleep 5
corpo $D/n /meus-ingressos/ > $D/mi2.html; linha $D/mi2.html "$C1"
prazo "$C1" "<= interval '5 seconds'"
```

Esperado:
- publicar: status 302 e `location: /organizador/eventos/<E1>/`; `1` (E1 aparece na vitrine);
- `1`; `1`; `1`; `data-campo="vagas-disponiveis">2<`;
- a compra: status 302, `location: /meus-ingressos/` e `tempo=` com um número **menor que 1** (a resposta não espera o gateway);
- um código de 8 caracteres de `[A-Z0-9]`;
- a linha do retrato tirado logo depois da compra contém `data-status="pending"`, `data-campo="evento">Show Dois<`, `data-campo="status">pendente<` e `data-campo="codigo"><C1><`;
- visitante com E1 publicado: status 302 e `location: /contas/entrar/`;
- `10000|0001|vitrine|nina@example.com|nina@example.com`; `1` (o visitante não criou ingresso);
- depois dos 5 s: a linha contém `data-campo="status">confirmado<`; `confirmed|t` (processado em até 5 s depois da compra).

### C-04 — (XF-02, F03-CA08, R09) Cada participante só vê os próprios ingressos

```bash
entrar $D/p participante@catraca.test
corpo $D/p /meus-ingressos/ > $D/mp.html
grep -c "$C1" $D/mp.html
grep -cF "Você ainda não tem ingressos." $D/mp.html
grep -c 'data-ingresso="tkt_' $D/mi2.html
```

Esperado: status 302 e `location: /`; `0`; `1`; `1`.

### C-05 — (F03-CA03, R05, R08) Recusa (final 0002 e final fora da tabela) libera a vaga em até 5 s

```bash
E2=$(novo_evento $D/a "Recusa" "2027-06-16T21:00" 3 "50,00"); guardar E2 "$E2"; echo "$E2"
vagas $D/n "$E2"
comprar $D/n "$E2" 4000000000000002; vagas $D/n "$E2" > $D/v1
comprar $D/n "$E2" 4000000000000009; vagas $D/n "$E2" > $D/v2; corpo $D/n /meus-ingressos/ > $D/mi3.html
cat $D/v1 $D/v2
C3=$(codigos $D/mi3.html | sed -n 1p); C2=$(codigos $D/mi3.html | sed -n 2p); guardar C2 "$C2"; guardar C3 "$C3"
linha $D/mi3.html "$C2" | grep -c 'data-campo="status">pendente<'; linha $D/mi3.html "$C3" | grep -c 'data-campo="status">pendente<'
sql "select cartao_final from dominio_ingresso where codigo in ('$C2', '$C3') order by id"
sleep 5
prazo "$C2" "<= interval '5 seconds'"; prazo "$C3" "<= interval '5 seconds'"
vagas $D/n "$E2"
corpo $D/n /meus-ingressos/ | grep -F "data-campo=\"codigo\">$C2<" | grep -c 'data-campo="status">recusado<'
```

Esperado: um id `evt_…`; `data-campo="vagas-disponiveis">3<`; duas compras com status 302 e `location: /meus-ingressos/`; duas linhas, `data-campo="vagas-disponiveis">2<` e `data-campo="vagas-disponiveis">1<` (cada pendente ocupa uma vaga); `1`; `1`; duas linhas, `0002` e `0009`; depois dos 5 s, `declined|t` e `declined|t`; `data-campo="vagas-disponiveis">3<` (as vagas voltaram); `1`.

### C-06 — (F03-CA04, F03-CA05, F03-CA11, R05, R06, R07, R08) Cartões lentos: pendente ocupa a vaga até a resposta; esgotado na vitrine

```bash
E3=$(novo_evento $D/a "Lento Recusado" "2027-06-17T21:00" 1 "30,00"); guardar E3 "$E3"
E3B=$(novo_evento $D/a "Lento Aprovado" "2027-06-17T22:00" 1 "30,00"); guardar E3B "$E3B"; echo "$E3 $E3B"
T0=$(date +%s); comprar $D/n "$E3" 4000000000000004; comprar $D/n "$E3B" 4000000000000003
corpo $D/n /eventos/$E3/ > $D/e3a.html; corpo $D/n /meus-ingressos/ > $D/mi4.html
C4B=$(codigos $D/mi4.html | sed -n 1p); C4=$(codigos $D/mi4.html | sed -n 2p); guardar C4 "$C4"; guardar C4B "$C4B"
grep -oE 'data-campo="vagas-disponiveis">[0-9]+<' $D/e3a.html; grep -c 'id="esgotado"' $D/e3a.html; grep -cF '<p id="esgotado">Ingressos esgotados</p>' $D/e3a.html; grep -c 'id="form-compra"' $D/e3a.html
comprar $D/n "$E3" 4000000000000001
grep -c 'id="esgotado"' $D/n.html; grep -cF 'id="erro-compra">Ingressos esgotados<' $D/n.html
sql "select count(*) from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico = '$E3'"
sleep $(( T0 + 31 - $(date +%s) )); status "$C4"; status "$C4B"; vagas $D/n "$E3"
sleep $(( T0 + 45 - $(date +%s) )); status "$C4"; status "$C4B"
prazo "$C4" "between interval '30 seconds' and interval '40 seconds'"; prazo "$C4B" "between interval '30 seconds' and interval '40 seconds'"
corpo $D/n /eventos/$E3/ > $D/e3b.html
grep -oE 'data-campo="vagas-disponiveis">[0-9]+<' $D/e3b.html; grep -c 'id="esgotado"' $D/e3b.html; grep -c 'id="form-compra"' $D/e3b.html
vagas $D/n "$E3B"
```

Esperado:
- os dois ids; duas compras com status 302 e `location: /meus-ingressos/`;
- logo depois: `data-campo="vagas-disponiveis">0<`; `1`; `1` ("Ingressos esgotados" no lugar do formulário); `0` (sem formulário);
- a segunda compra no E3: status 200 **sem** `location:`; `1`; `1` (a resposta exibe "Ingressos esgotados"); `1` (só o primeiro ingresso existe);
- aos 31 s: `pending`, `pending` e `data-campo="vagas-disponiveis">0<`;
- aos 45 s: `declined` (final 0004) e `confirmed` (final 0003); `declined|t` e `confirmed|t` (responderam entre 30 e 40 s depois da compra);
- E3 depois da recusa: `data-campo="vagas-disponiveis">1<`; `0`; `1` (o formulário voltou); E3B continua lotado: `data-campo="vagas-disponiveis">0<`.

### C-07 — (F03-CA07) Cartão fora de 16 dígitos é rejeitado antes de criar o ingresso; só o final é gravado

```bash
echo "$(ingressos)/$(cobrancas)"
for c in 123 40000000000000011 400000000000000A ""; do comprar $D/n "$E2" "$c"; grep -cF 'id="erro-compra">O número do cartão precisa ter 16 dígitos.<' $D/n.html; done
comprar $D/n evt_zzzzzzzz 123
echo "$(ingressos)/$(cobrancas)"
docker compose exec -T db pg_dump -U catraca -d catraca --data-only | grep -c '4000000000000001'
sql "select distinct length(cartao_final) from dominio_ingresso"
```

Esperado: `5/5`; quatro vezes: status 200 sem `location:` e `1`; cartão inválido em evento inexistente: status 404; `5/5` (nada criado); `0` (o número inteiro não está em nenhuma tabela); `4`.

### C-08 — (F03-CA08, R09) Código único, maiúsculo, de 8 caracteres

```bash
sql "select count(*), count(distinct codigo), bool_and(codigo ~ '^[A-Z0-9]{8}\$') from dominio_ingresso"
sql "select count(*) from pg_indexes where tablename = 'dominio_ingresso' and indexdef like 'CREATE UNIQUE INDEX%' and indexdef like '%(codigo)%'"
```

Esperado: `5|5|t`; `1` (restrição de unicidade no banco).

### C-09 — (F03-CA09, F03-CA10, F03-CA08, XF-04, R03, R12) Lotação × ocupadas e preço gravado; Meus ingressos com todos os próprios

```bash
E4=$(novo_evento $D/a "Preço Muda" "2027-06-18T21:00" 2 "100,00"); guardar E4 "$E4"; echo "$E4"
comprar $D/n "$E4" 4000000000000001; comprar $D/n "$E4" 4000000000000001
postar $D/a /organizador/eventos/$E4/editar/ "nome=Preço Muda" "inicio=2027-06-18T21:00" "local=Sala" "lotacao=1" "preco=100,00"
grep -cF "A lotação não pode ser menor que as vagas ocupadas (2)." $D/a.html
sql "select lotacao, preco_centavos from dominio_evento where id_publico = '$E4'"
postar $D/a /organizador/eventos/$E4/editar/ "nome=Preço Muda" "inicio=2027-06-18T21:00" "local=Sala" "lotacao=2" "preco=100,00"
postar $D/a /organizador/eventos/$E4/editar/ "nome=Preço Muda" "inicio=2027-06-18T21:00" "local=Sala" "lotacao=3" "preco=150,00"
sql "select lotacao, preco_centavos from dominio_evento where id_publico = '$E4'"
comprar $D/n "$E4" 4000000000000001
sql "select i.valor_centavos from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico = '$E4' order by i.id"
corpo $D/n /meus-ingressos/ | grep -c 'data-ingresso="tkt_'
sql "select count(*) from dominio_ingresso i join dominio_usuario u on u.id = i.comprador_id where u.email = 'nina@example.com'"
```

Esperado: um id `evt_…`; duas compras com status 302 e `location: /meus-ingressos/`; editar para lotação 1: status 200 sem `location:`; `1`; `2|10000` (não mudou); lotação 2: status 302 e `location: /organizador/eventos/<E4>/`; lotação 3 e preço 150,00: status 302 e o mesmo `location:`; `3|15000`; terceira compra com status 302; três linhas, nesta ordem: `10000`, `10000`, `15000`; `8` e `8` (Meus ingressos de Nina mostra todos os 8 ingressos dela).

### C-10 — (F03-CA06, F03-CA09, R07, R03) Testes de concorrência contra o Postgres

```bash
./scripts/gates.sh -v dominio/tests/test_concorrencia.py; echo "código: $?"
grep -cE 'COMPRAS_SIMULTANEAS = 30|LOTACAO = 5|RODADAS = 10|threading\.Barrier\(COMPRAS_SIMULTANEAS\)' dominio/tests/test_concorrencia.py
```

Esperado: "código: 0" com `test_compras_simultaneas_nunca_passam_da_lotacao PASSED` (30 threads liberadas juntas por uma barreira, cada uma com a sua conexão, num evento de lotação 5, repetido em 10 eventos novos: exatamente 5 ingressos e 25 `IngressosEsgotados` em cada um) e `test_editar_lotacao_concorrente_com_compras PASSED` (edição de lotação para baixo disputando com compras simultâneas; as vagas ocupadas nunca passam da lotação gravada); `4` (as quatro constantes do teste estão no arquivo).

### C-11 — (R07) Rajada de 30 compras simultâneas pela vitrine, em dois eventos novos

```bash
TOKEN=$(csrf $D/n)
for rodada in 1 2; do
  E=$(novo_evento $D/a "Rajada $rodada" "2027-07-0${rodada}T20:00" 5 "10,00"); echo "$E"
  seq 30 | xargs -P 30 -I{} curl -s -o "$D/r${rodada}_{}.html" -w "%{http_code}\n" -b $D/n \
    --data-urlencode "csrfmiddlewaretoken=$TOKEN" --data-urlencode "cartao=4000000000000001" \
    "$WEB/eventos/$E/comprar/" | sort | uniq -c
  grep -lF 'id="erro-compra">Ingressos esgotados<' $D/r${rodada}_*.html | wc -l
  sql "select count(*), count(*) filter (where i.status in ('pending', 'confirmed')), e.lotacao from dominio_ingresso i join dominio_evento e on e.id = i.evento_id where e.id_publico = '$E' group by e.lotacao"
done
```

Esperado, em cada uma das duas rodadas: um id `evt_…`; exatamente duas linhas de contagem, `25 200` e `5 302` (com espaços à esquerda do número): 5 compras aceitas, com o redirecionamento para Meus ingressos, e 25 respostas 200; o número `25` (com ou sem espaços à esquerda): as 25 respostas 200 exibem "Ingressos esgotados"; `5|5|5` (5 ingressos, 5 vagas ocupadas, lotação 5).

### C-12 — (F03-CA11, R08) Tempos do gateway e fator de atraso só em teste

```bash
./scripts/gates.sh -v dominio/tests/test_gateway.py -k "resultado_por_final or atrasos_ficam or fator_de_atraso or compose_nao_define"; echo "código: $?"
grep -c GATEWAY_FATOR_ATRASO compose.yaml
docker compose exec -T gateway printenv GATEWAY_FATOR_ATRASO; echo "código: $?"
```

Esperado: "código: 0" com `test_resultado_por_final_do_cartao`, `test_atrasos_ficam_nas_faixas_com_semente`, `test_fator_de_atraso_multiplica` e `test_compose_nao_define_fator_de_atraso` como PASSED; `0`; nenhuma saída do `printenv` e "código: 1" (a variável não existe no container do gateway).

### C-13 — (F03-CA12, R08, R11) Resposta do gateway só muda ingresso pendente, num único UPDATE condicional

```bash
./scripts/gates.sh -v dominio/tests/test_gateway.py -k "aplicar_resposta or processar or respostas_simultaneas"; echo "código: $?"
sed -n '/^def aplicar_resposta_gateway/,/^def /p' dominio/servicos/gateway.py | grep -cE 'filter\(pk=ingresso_id, status=Ingresso\.Status\.PENDENTE\)\.update\('
sed -n '/^def aplicar_resposta_gateway/,/^def /p' dominio/servicos/gateway.py | grep -cE '\.save\(|\.get\(|select_for_update'
```

Esperado: "código: 0" com `test_aplicar_resposta_so_muda_pendente` (os quatro status não pendentes devolvem `False` e não mudam), `test_respostas_simultaneas_so_uma_aplica` (duas respostas opostas ao mesmo tempo: exatamente uma devolve `True`), `test_processar_cobrancas_vencidas_marca_processada_mesmo_sem_mudanca` e `test_processar_ignora_cobrancas_nao_vencidas` como PASSED; `1` (a resposta é um `filter(…, status=pendente).update(…)`); `0` (sem ler e gravar em dois passos).

### C-14 — Meus ingressos e o link do bloco do usuário

```bash
ver $D/n /meus-ingressos/
ver $D/v /meus-ingressos/
ver $D/a /meus-ingressos/
corpo $D/n / | sed -n '/id="usuario-logado"/,/<\/nav>/p' | grep -cF 'href="/meus-ingressos/"'
```

Esperado: status 200; status 302 e `location: /contas/entrar/?next=/meus-ingressos/`; status 403; `1`.

### C-15 — (F03-CA14) Worker em container próprio, resiliente a derrubar e subir

```bash
docker compose ps --format '{{.Service}} {{.State}}' | grep -E '^(web|gateway) ' | sort
docker compose stop gateway
comprar $D/n "$E2" 4000000000000001; corpo $D/n /meus-ingressos/ > $D/mi5.html
C5=$(codigos $D/mi5.html | head -n 1); guardar C5 "$C5"
sleep 6
sql "select i.status, c.processada_em is null, c.responder_em < now() from dominio_ingresso i join dominio_cobrancagateway c on c.ingresso_id = i.id where i.codigo = '$C5'"
CATRACA_PORTA=$PORTA ./scripts/down.sh
CATRACA_PORTA=$PORTA ./scripts/up.sh >/dev/null; echo "up: $?"
sleep 3
sql "select i.status, c.processada_em is null from dominio_ingresso i join dominio_cobrancagateway c on c.ingresso_id = i.id where i.codigo = '$C5'"
```

Esperado: duas linhas, nesta ordem, `gateway running` e `web running` (serviços separados); compra com status 302; `pending|t|t` (vencida e não processada com o worker parado); "Catraca encerrada (volume do banco mantido)."; `up: 0`; `confirmed|f` (processada depois da subida).

### C-16 — Testes automatizados da feature

```bash
./scripts/gates.sh -v dominio/tests/test_compras.py dominio/tests/test_gateway.py web/tests/test_compras.py; echo "código: $?"
```

Esperado: "código: 0", nenhum "FAILED" nem "SKIPPED", e como PASSED (com ou sem sufixo `[...]`) pelo menos: `test_restricoes_do_ingresso_no_banco`, `test_comprar_cria_pendente_com_preco_e_final_do_cartao`, `test_cartao_invalido_nao_cria_nada`, `test_cartao_invalido_antes_de_evento_indisponivel`, `test_email_invalido_nao_cria_nada`, `test_evento_indisponivel_nao_vende`, `test_sem_vaga_lanca_esgotados`, `test_pendente_ocupa_e_recusado_libera_vaga`, `test_vagas_disponiveis_de_cancelado_e_zero`, `test_preco_gravado_nao_muda_com_preco_novo`, `test_lotacao_nao_fica_abaixo_das_ocupadas`, `test_codigo_unico_maiusculo_de_8`, `test_consultar_ingresso`, `test_ingressos_do_participante_so_os_proprios` (em `dominio/tests/test_compras.py`); `test_resultado_por_final_do_cartao`, `test_atrasos_ficam_nas_faixas_com_semente`, `test_fator_de_atraso_multiplica`, `test_compose_nao_define_fator_de_atraso`, `test_aplicar_resposta_so_muda_pendente`, `test_respostas_simultaneas_so_uma_aplica`, `test_processar_cobrancas_vencidas_marca_processada_mesmo_sem_mudanca`, `test_processar_ignora_cobrancas_nao_vencidas`, `test_worker_processa_cobrancas_vencidas` (em `dominio/tests/test_gateway.py`); `test_bloco_compra_com_vaga_mostra_formulario`, `test_bloco_compra_sem_vaga_mostra_esgotados`, `test_visitante_ve_link_para_entrar`, `test_compra_pela_vitrine_vai_para_meus_ingressos_pendente`, `test_compra_com_cartao_invalido_reexibe_sem_criar`, `test_compra_esgotada_mostra_mensagem_sem_criar`, `test_compra_de_rascunho_ou_inexistente_responde_404`, `test_visitante_e_organizador_nao_compram`, `test_meus_ingressos_so_os_proprios`, `test_editar_lotacao_abaixo_das_ocupadas_pela_tela` (em `web/tests/test_compras.py`).

Ao terminar: `CATRACA_PORTA=$PORTA ./scripts/down.sh` e `rm -rf "$D"`.

## 3. Mapeamento critério do PRD → itens

| Critério do PRD | Itens |
|---|---|
| F03-CA01 — (R06, R09) Compra na vitrine nasce pendente, resposta < 1 s, Meus ingressos com evento, "pendente" e código | C-03, C-16 |
| F03-CA02 — (R08) Final 0001 confirmado em até 5 s | C-03 |
| F03-CA03 — (R05, R08) 0002 e final fora da tabela recusados em até 5 s; vaga volta | C-05 |
| F03-CA04 — (R05, R06) Pendente lento (0004) ocupa a vaga; esgotado na vitrine; recusa entre 30 e 40 s devolve a vaga; 0003 confirma depois de 30 s | C-06 |
| F03-CA05 — (R07) Sem vaga: "Ingressos esgotados" no lugar do formulário e no POST, sem criar ingresso | C-06, C-11, C-16 |
| F03-CA06 — (R07) Concorrência: 30 threads, lotação 5, 10 eventos | C-10, C-11 |
| F03-CA07 — Cartão fora de 16 dígitos rejeitado antes de criar; só o final gravado | C-07, C-16 |
| F03-CA08 — (R09) Código único e maiúsculo; Meus ingressos com todos os próprios e nenhum de outro | C-04, C-08, C-09, C-16 |
| F03-CA09 — (R03) Lotação abaixo das ocupadas rejeitada com a mensagem exata; 2 e 3 aceitas; com a linha travada | C-09, C-10, C-16 |
| F03-CA10 — (R03, R12) Preço gravado: 10000 continua, a seguinte grava 15000 | C-09, C-16 |
| F03-CA11 — (R08) Faixas de atraso; Compose sem `GATEWAY_FATOR_ATRASO` | C-12, C-03, C-05, C-06 |
| F03-CA12 — (R08, R11) `aplicar_resposta_gateway` condicional; cobrança processada mesmo assim | C-13 |
| F03-CA13 — (R02, R06) Compra de rascunho ou inexistente: 404 sem criar | C-02, C-07, C-16 |
| F03-CA14 — Worker em container próprio, cobranças vencidas processadas depois de subir de novo | C-15 |
| XF-02 [F01→F03] — Conta do cadastro compra e vê o ingresso; a da seed não vê; visitante vai para o login sem criar | C-02, C-03, C-04 |
| XF-03 [F02→F03] — Evento publicado pela gestão aparece na vitrine e vende; em rascunho o POST dava 404 | C-02, C-03 |
| XF-04 [F02→F03] — Lotação 1 rejeitada com 2 ocupadas; 150,00 e lotação 3 aceitos; 15000 na seguinte | C-09 |

## 4. Fora deste contrato

- Compra pela API e `checkedIn` (F04); check-in (F05); painel (F06); cancelamento e resposta tardia em evento cancelado (F07). O comportamento condicional de `aplicar_resposta_gateway`, base da F07, é coberto aqui (C-13).
