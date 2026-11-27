# Contrato — F02 Eventos e vitrine

> O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item, na ordem. Textos esperados vão entre aspas, exatos, e são conferidos com `grep -F` (`grep -c` conta **linhas** que contêm o texto).

- Feature: F02 — Eventos e vitrine (wave W2)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (F02-CA01…CA09) e 7 (XF-01)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- **Antes de tudo**, na raiz do repositório (ou da worktree): `git rev-parse HEAD` precisa imprimir exatamente o sha completo pedido para a avaliação, e `git status --porcelain` precisa sair vazio. Se um dos dois não bater, o avaliador **para**, registra no relatório as duas saídas e não avalia nenhum item.
- Commit avaliado: o sha informado no pedido de avaliação (branch `feat/F02-eventos-vitrine`).
- Ferramentas no host: Docker, Git, `curl`, **bash** e os utilitários `awk`, `sed`, `grep` (com `-o`, presente no GNU e no BSD), `cut`, `sort`, `tr`. Navegador é opcional.
- Contas da seed (README, "Credenciais"): `org.a@catraca.test`, `org.b@catraca.test` e `participante@catraca.test`, todas com a senha `catraca123`.
- **Porta.** Vem de `CATRACA_PORTA` (padrão 8000) e é a mesma na subida, nos itens e na descida.
- **Banco zerado**, na raiz:

```bash
PORTA=${CATRACA_PORTA:-8000}
docker compose --profile '*' down -v          # apaga só o volume deste projeto
CATRACA_PORTA=$PORTA ./scripts/up.sh          # código 0 e "Catraca no ar."
```

O banco começa com **0** eventos.

- **Funções e estado.** Rode uma vez o bloco abaixo, em bash. Ele grava as funções em `$D/f.sh` e os ids dos eventos em `$D/ids` (os itens acrescentam a ele), num diretório fixo por porta. Os itens rodam **na ordem**; os ids `E1`…`E5` e as contagens dependem dela. Se um item for rodado num **shell novo**, antes dele rode: `PORTA=${CATRACA_PORTA:-8000}; D=/tmp/catraca-F02-$PORTA; . $D/f.sh; . $D/ids`.

```bash
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F02-$PORTA; rm -rf "$D"; mkdir -p "$D"; : > "$D/ids"
cat > "$D/f.sh" <<'FIM'
PORTA=${CATRACA_PORTA:-8000}
D=/tmp/catraca-F02-$PORTA
export WEB=http://localhost:$PORTA
sql()     { docker compose exec -T db psql -U catraca -d catraca -tAc "$1"; }
eventos() { sql "select count(*) from dominio_evento"; }
csrf()    { awk '$6 == "csrftoken" {print $7}' "$1"; }
# GET com cookies; imprime a linha de status e o Location
ver()     { curl -s -o /dev/null -D - -b "$1" -c "$1" "$WEB$2" | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
# GET com cookies; imprime o corpo
corpo()   { curl -s -b "$1" -c "$1" "$WEB$2"; }
# POST de formulário com CSRF: postar <cookies> <caminho> campo=valor ...
# faz um GET antes (para o csrftoken), imprime status e Location e salva o corpo em <cookies>.html
postar()  { local jar=$1 caminho=$2; shift 2
            curl -s -o /dev/null -b "$jar" -c "$jar" "$WEB$caminho"
            local args=(--data-urlencode "csrfmiddlewaretoken=$(csrf "$jar")")
            for kv in "$@"; do args+=(--data-urlencode "$kv"); done
            curl -s -o "$jar.html" -D - -b "$jar" -c "$jar" "${args[@]}" "$WEB$caminho" \
              | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
entrar()  { postar "$1" /contas/entrar/ "email=$2" "senha=catraca123"; }
# id do evento a partir da saída de postar (Location /organizador/eventos/<id>/)
idde()    { awk 'tolower($1) == "location:" {print $2}' | cut -d/ -f4; }
# confere o formato do id: imprime 1 se for evt_ + 8 caracteres de [a-z0-9]
formato() { echo "$1" | grep -cE '^evt_[a-z0-9]{8}$'; }
FIM
. "$D/f.sh"
```

"Status 302 e `location: /x`" quer dizer: a linha `HTTP/1.1 302 …` e o cabeçalho `Location` com o valor exato `/x`. "Sem `location:`" quer dizer sem redirecionamento. `<E1>` nos resultados esperados é o valor de `$E1` impresso no item que o criou.

## 2. Itens verificáveis

### C-01 — Gates

```bash
./scripts/gates.sh; echo "código: $?"
```

Esperado: "código: 0"; ruff sem erros, `manage.py check` sem problemas, "No changes detected" no `makemigrations --check`, pytest sem falhas, última etapa "==> gates: OK".

### C-02 — (XF-01, R13) Visitante e participante não criam evento

```bash
ver $D/v /organizador/eventos/novo/
entrar $D/p participante@catraca.test
ver $D/p /organizador/eventos/novo/
postar $D/p /organizador/eventos/novo/ "nome=Invasão" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=2" "preco=100,00"
grep -cF "<h2>Acesso negado</h2>" $D/p.html
eventos
```

Esperado, linha a linha: status 302 e `location: /contas/entrar/?next=/organizador/eventos/novo/`; status 302 e `location: /`; status 403; status 403 sem `location:`; `1`; `0`.

### C-03 — (F02-CA01, XF-01) Organizador A cria E1 em rascunho

```bash
entrar $D/a org.a@catraca.test
corpo $D/a /organizador/eventos/novo/ | grep -oE 'name="(nome|inicio|local|lotacao|preco)"' | sort -u
R=$(postar $D/a /organizador/eventos/novo/ "nome=Jazz no Porão" "inicio=2027-06-15T21:00" "local=Bar do Porão" "lotacao=2" "preco=100,00"); echo "$R"
E1=$(echo "$R" | idde); echo "E1=$E1" >> $D/ids; echo "$E1"; formato "$E1"
sql "select e.status, e.preco_centavos, e.lotacao, u.email, to_char(e.inicio at time zone 'America/Sao_Paulo', 'YYYY-MM-DD HH24:MI') from dominio_evento e join dominio_usuario u on u.id = e.organizador_id where e.id_publico = '$E1'"
eventos
```

Esperado: status 302 e `location: /organizador/`. Exatamente 5 linhas: `name="inicio"`, `name="local"`, `name="lotacao"`, `name="nome"`, `name="preco"`. Status 302 e `location: /organizador/eventos/<E1>/`. O id impresso e, em seguida, `1` (formato `evt_` + 8). Uma linha: `rascunho|10000|2|org.a@catraca.test|2027-06-15 21:00`. `1`.

### C-04 — (F02-CA01) Preço "100" e "100.00" viram 10000 centavos

```bash
E2=$(postar $D/a /organizador/eventos/novo/ "nome=Preço Inteiro" "inicio=2027-07-01T20:00" "local=Teatro" "lotacao=10" "preco=100" | idde); echo "E2=$E2" >> $D/ids
E3=$(postar $D/a /organizador/eventos/novo/ "nome=Preço Ponto" "inicio=2027-07-02T20:00" "local=Teatro" "lotacao=10" "preco=100.00" | idde); echo "E3=$E3" >> $D/ids
formato "$E2"; formato "$E3"; [ "$E2" != "$E3" ] && echo diferentes
sql "select id_publico, preco_centavos, status from dominio_evento where id_publico in ('$E2', '$E3') order by inicio"
eventos
```

Esperado: `1`; `1`; `diferentes`. Duas linhas: `<E2>|10000|rascunho` e `<E3>|10000|rascunho`. `3`.

### C-05 — (F02-CA02, R01) Validações ao criar

```bash
postar $D/a /organizador/eventos/novo/ "nome=Ontem" "inicio=2026-01-10T20:00" "local=Bar" "lotacao=2" "preco=100,00"
grep -cF "A data de início precisa estar no futuro." $D/a.html
postar $D/a /organizador/eventos/novo/ "nome=Lotação zero" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=0" "preco=100,00"
grep -cF "A lotação precisa ser um número inteiro maior ou igual a 1." $D/a.html
postar $D/a /organizador/eventos/novo/ "nome=Lotação negativa" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=-1" "preco=100,00"
grep -cF "A lotação precisa ser um número inteiro maior ou igual a 1." $D/a.html
postar $D/a /organizador/eventos/novo/ "nome=Lotação quebrada" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=2.5" "preco=100,00"
grep -cF "A lotação precisa ser um número inteiro maior ou igual a 1." $D/a.html
postar $D/a /organizador/eventos/novo/ "nome=Preço texto" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=2" "preco=abc"
grep -cF "Informe o preço em reais, por exemplo 100,00." $D/a.html
postar $D/a /organizador/eventos/novo/ "nome=Preço zero" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=2" "preco=0"
grep -cF "O preço precisa ser maior que zero." $D/a.html
postar $D/a /organizador/eventos/novo/ "nome=Preço negativo" "inicio=2027-06-15T21:00" "local=Bar" "lotacao=2" "preco=-10"
grep -cF "O preço precisa ser maior que zero." $D/a.html
postar $D/a /organizador/eventos/novo/ "nome=" "inicio=" "local=" "lotacao=" "preco="
for m in "Informe o nome do evento." "Informe a data e a hora de início." "Informe o local." "Informe a lotação." "Informe o preço."; do grep -cF -- "$m" $D/a.html; done
eventos
```

Esperado: cada `postar` imprime status 200 **sem** `location:`; cada `grep -cF` logo depois imprime `1` (as sete primeiras mensagens e, no último caso, as cinco mensagens: cinco linhas `1`). Por fim, `eventos` → `3` (nada foi gravado).

### C-06 — (F02-CA03, R02) Rascunho fica fora da vitrine

```bash
corpo $D/v / > $D/vit0.html
grep -c 'id="vitrine"' $D/vit0.html
grep -c "Jazz no Porão" $D/vit0.html
grep -c "/eventos/evt_" $D/vit0.html
grep -cF "Nenhum evento à venda no momento." $D/vit0.html
ver $D/v /eventos/$E1/
ver $D/p /eventos/$E1/
ver $D/v /eventos/evt_zzzzzzzz/
```

Esperado: `1`; `0`; `0`; `1`; status 404; status 404; status 404.

### C-07 — (F02-CA04, F02-CA09, R02) Publicar E1

```bash
postar $D/a /organizador/eventos/$E1/publicar/
sql "select status from dominio_evento where id_publico = '$E1'"
corpo $D/v / > $D/vitrine.html
grep -c 'id="vitrine"' $D/vitrine.html
for t in "Jazz no Porão" "Bar do Porão" "15/06/2027 21:00" "R\$ 100,00" "href=\"/eventos/$E1/\""; do grep -cF -- "$t" $D/vitrine.html; done
grep -cE "$E2|$E3" $D/vitrine.html
ver $D/v /eventos/$E1/
corpo $D/v /eventos/$E1/ > $D/detalhe.html
grep -c 'id="compra"' $D/detalhe.html
grep -cF "Jazz no Porão" $D/detalhe.html
postar $D/a /organizador/eventos/$E1/publicar/
sql "select status from dominio_evento where id_publico = '$E1'"
eventos
```

Esperado: status 302 e `location: /organizador/eventos/<E1>/`; `publicado`; `1`; cinco números, cada um **maior ou igual a 1** (cada texto aparece na vitrine deslogada); `0` (os rascunhos E2 e E3 continuam fora); status 200; `1`; um número maior ou igual a `1`; de novo status 302 e `location: /organizador/eventos/<E1>/`; `publicado`; `3` (publicar de novo não muda nada).

### C-08 — (F02-CA09) Vitrine ordenada pelo início

```bash
E4=$(postar $D/a /organizador/eventos/novo/ "nome=Meetup Antecipado" "inicio=2027-05-01T19:00" "local=Cowork" "lotacao=30" "preco=25,00" | idde); echo "E4=$E4" >> $D/ids; formato "$E4"
postar $D/a /organizador/eventos/$E4/publicar/
corpo $D/v / | grep -oE 'href="/eventos/evt_[a-z0-9]{8}/"'
```

Esperado: `1`; status 302 e `location: /organizador/eventos/<E4>/`; exatamente duas linhas, nesta ordem: `href="/eventos/<E4>/"` e `href="/eventos/<E1>/"`.

### C-09 — (F02-CA05, R04) Página de gestão

```bash
ver $D/a /organizador/eventos/$E1/
corpo $D/a /organizador/eventos/$E1/ > $D/g1.html
for s in evento-dados evento-acoes evento-cancelar check-in painel; do grep -c "id=\"$s\"" $D/g1.html; done
for t in 'data-campo="nome">Jazz no Porão<' 'data-campo="inicio">15/06/2027 21:00<' 'data-campo="local">Bar do Porão<' 'data-campo="lotacao">2<' 'data-campo="preco">R$ 100,00<' 'data-campo="status">Publicado<'; do grep -cF -- "$t" $D/g1.html; done
grep -cF "href=\"/organizador/eventos/$E1/editar/\"" $D/g1.html
grep -cF "action=\"/organizador/eventos/$E1/publicar/\"" $D/g1.html
corpo $D/a /organizador/eventos/$E2/ > $D/g2.html
grep -cF 'data-campo="status">Rascunho<' $D/g2.html
grep -cF "action=\"/organizador/eventos/$E2/publicar/\"" $D/g2.html
postar $D/a /contas/sair/
ver $D/a /organizador/eventos/$E1/
entrar $D/a org.a@catraca.test
ver $D/a /organizador/eventos/$E1/
```

Esperado: status 200; cinco linhas `1` (um de cada bloco); seis linhas `1` (os dados com `data-campo`); `1` (link Editar); `0` (sem Publicar em evento publicado); `1` ("Rascunho" no E2); `1` (Publicar em rascunho); sair: status 302 e `location: /`; deslogado: status 302 e `location: /contas/entrar/?next=/organizador/eventos/<E1>/`; entrar: status 302 e `location: /organizador/`; status 200 (a URL abre direto de novo).

### C-10 — (F02-CA06, F02-CA02, R01, R03) Editar

```bash
corpo $D/a /organizador/eventos/$E1/editar/ > $D/ed.html
grep -cF 'value="2027-06-15T21:00"' $D/ed.html
grep -cF 'value="100,00"' $D/ed.html
postar $D/a /organizador/eventos/$E1/editar/ "nome=Jazz no Porão (edição)" "inicio=2027-06-20T22:30" "local=Porão Novo" "lotacao=4" "preco=120,50"
sql "select nome, local, lotacao, preco_centavos, to_char(inicio at time zone 'America/Sao_Paulo', 'YYYY-MM-DD HH24:MI'), status from dominio_evento where id_publico = '$E1'"
corpo $D/a /organizador/eventos/$E1/ > $D/g1b.html
for t in 'data-campo="nome">Jazz no Porão (edição)<' 'data-campo="inicio">20/06/2027 22:30<' 'data-campo="local">Porão Novo<' 'data-campo="lotacao">4<' 'data-campo="preco">R$ 120,50<'; do grep -cF -- "$t" $D/g1b.html; done
corpo $D/v / > $D/vitrine2.html
for t in "Jazz no Porão (edição)" "Porão Novo" "20/06/2027 22:30" "R\$ 120,50"; do grep -cF -- "$t" $D/vitrine2.html; done
postar $D/a /organizador/eventos/$E1/editar/ "nome=Volta ao passado" "inicio=2026-01-10T20:00" "local=Porão Novo" "lotacao=4" "preco=120,50"
grep -cF "A data de início precisa estar no futuro." $D/a.html
postar $D/a /organizador/eventos/$E1/editar/ "nome=Sem lotação" "inicio=2027-06-20T22:30" "local=Porão Novo" "lotacao=0" "preco=120,50"
grep -cF "A lotação precisa ser um número inteiro maior ou igual a 1." $D/a.html
sql "select nome, lotacao, to_char(inicio at time zone 'America/Sao_Paulo', 'YYYY-MM-DD HH24:MI') from dominio_evento where id_publico = '$E1'"
```

Esperado: `1`; `1` (o formulário vem preenchido); status 302 e `location: /organizador/eventos/<E1>/`; uma linha `Jazz no Porão (edição)|Porão Novo|4|12050|2027-06-20 22:30|publicado`; cinco linhas `1` (a gestão mostra os valores novos); quatro números maiores ou iguais a `1` (a vitrine também); status 200 sem `location:` e `1`; status 200 sem `location:` e `1`; uma linha `Jazz no Porão (edição)|4|2027-06-20 22:30` (as edições inválidas não gravaram nada).

### C-11 — (F02-CA07, XF-01, R13) Cada organizador só vê os próprios eventos na lista

```bash
corpo $D/a /organizador/ > $D/lista-a.html
grep -c 'id="meus-eventos"' $D/lista-a.html
grep -cF 'href="/organizador/eventos/novo/"' $D/lista-a.html
for e in "$E1:publicado" "$E2:rascunho" "$E3:rascunho" "$E4:publicado"; do grep -cF "data-evento=\"${e%%:*}\" data-status=\"${e##*:}\"" $D/lista-a.html; done
for t in "Jazz no Porão (edição)" "Preço Inteiro" "Preço Ponto" "Meetup Antecipado"; do grep -cF -- "$t" $D/lista-a.html; done
entrar $D/b org.b@catraca.test
E5=$(postar $D/b /organizador/eventos/novo/ "nome=Evento do B" "inicio=2027-08-01T20:00" "local=Sala B" "lotacao=5" "preco=20,00" | idde); echo "E5=$E5" >> $D/ids; formato "$E5"
corpo $D/b /organizador/ > $D/lista-b.html
grep -cF "data-evento=\"$E5\" data-status=\"rascunho\"" $D/lista-b.html
grep -c 'data-evento=' $D/lista-b.html
grep -cE "Jazz no Porão|Preço Inteiro|Preço Ponto|Meetup Antecipado" $D/lista-b.html
corpo $D/a /organizador/ | grep -cF "Evento do B"
sql "select u.email, count(*) from dominio_evento e join dominio_usuario u on u.id = e.organizador_id group by u.email order by u.email"
```

Esperado: `1`; `1`; quatro linhas `1` (cada evento de A com o seu status); quatro números maiores ou iguais a `1`; login de B: status 302 e `location: /organizador/`; `1`; `1`; `1` (a lista de B tem só o E5); `0`; `0`; duas linhas: `org.a@catraca.test|4` e `org.b@catraca.test|1`.

### C-12 — (F02-CA08, R13) Organizador B no evento de A: 404 sem dados e sem efeito

```bash
ver $D/b /organizador/eventos/$E1/
corpo $D/b /organizador/eventos/$E1/ | grep -cE "Jazz no Porão|Porão Novo|120,50|data-campo"
ver $D/b /organizador/eventos/$E1/editar/
corpo $D/b /organizador/eventos/$E1/editar/ | grep -cE "Jazz no Porão|Porão Novo|120,50|data-campo"
postar $D/b /organizador/eventos/$E1/editar/ "nome=Hackeado" "inicio=2027-06-20T22:30" "local=X" "lotacao=1" "preco=1,00"
grep -cE "Jazz no Porão|Porão Novo|120,50|data-campo" $D/b.html
postar $D/b /organizador/eventos/$E2/publicar/
grep -cE "Preço Inteiro|Teatro|100,00|data-campo" $D/b.html
sql "select id_publico, nome, lotacao, preco_centavos, status from dominio_evento where id_publico in ('$E1', '$E2') order by inicio"
```

Esperado: status 404; `0`; status 404; `0`; status 404 sem `location:`; `0`; status 404 sem `location:`; `0`; duas linhas, `<E1>|Jazz no Porão (edição)|4|12050|publicado` e `<E2>|Preço Inteiro|10|10000|rascunho` (nada mudou).

### C-13 — (XF-01, R13) Visitante e participante na gestão de um evento de A

```bash
ver $D/v /organizador/eventos/$E1/
curl -s "$WEB/organizador/eventos/$E1/" | grep -c "Jazz no Porão"
ver $D/p /organizador/eventos/$E1/
corpo $D/p /organizador/eventos/$E1/ | grep -cE "Jazz no Porão|data-campo"
```

Esperado: status 302 e `location: /contas/entrar/?next=/organizador/eventos/<E1>/`; `0`; status 403; `0`.

### C-14 — Teste que percorre todas as rotas de `/organizador/` (inclusive as novas)

```bash
./scripts/gates.sh web/tests/test_acesso.py::test_rotas_do_organizador_barram_visitante_e_participante; echo "código: $?"
```

Esperado: "1 passed" e "código: 0".

### C-15 — Testes automatizados da feature

```bash
./scripts/gates.sh -v dominio/tests/test_eventos.py web/tests/test_eventos.py; echo "código: $?"
```

Esperado: "código: 0", nenhum "FAILED" nem "SKIPPED", e aparecem como PASSED (com ou sem sufixo de parâmetro `[...]`) pelo menos:
- `dominio/tests/test_eventos.py`: `test_restricoes_do_evento_no_banco`, `test_criar_evento_nasce_rascunho_com_preco_em_centavos`, `test_criar_evento_valida_campos`, `test_criar_evento_junta_todos_os_erros`, `test_criar_e_editar_rejeitam_inicio_no_passado`, `test_editar_evento_grava_novos_valores`, `test_editar_evento_de_outro_organizador_lanca_nao_encontrado`, `test_publicar_evento_so_a_partir_de_rascunho_e_idempotente`, `test_eventos_do_organizador_so_os_proprios`, `test_eventos_a_venda_so_publicados_ordenados_por_inicio`, `test_evento_a_venda_lanca_indisponivel`, `test_id_publico_no_formato_evt`;
- `web/tests/test_eventos.py`: `test_filtro_reais`, `test_vitrine_lista_publicados_com_dados_e_link`, `test_vitrine_vazia`, `test_detalhe_de_rascunho_ou_inexistente_responde_404`, `test_criar_evento_pela_tela_vai_para_gestao`, `test_criar_evento_invalido_reexibe_formulario_sem_gravar`, `test_gestao_mostra_dados_acoes_e_slots`, `test_editar_evento_pela_tela`, `test_publicar_evento_pela_tela`, `test_lista_do_organizador_so_mostra_os_proprios`, `test_outro_organizador_recebe_404_sem_dados`, `test_participante_nao_cria_evento`, `test_visitante_na_gestao_vai_para_o_login_sem_dados`.

Ao terminar: `CATRACA_PORTA=$PORTA ./scripts/down.sh` e `rm -rf "$D"`.

## 3. Mapeamento critério do PRD → itens

| Critério do PRD | Itens |
|---|---|
| F02-CA01 — (R01, R02) Criar: rascunho, 10000 centavos, dono, `evt_…`, vai para a gestão; "100", "100,00" e "100.00" | C-03, C-04, C-15 |
| F02-CA02 — (R01) Validações ao criar e ao editar | C-05, C-10, C-15 |
| F02-CA03 — (R02) Rascunho fora da vitrine e de `eventos_a_venda()`; detalhe 404 | C-06, C-15 |
| F02-CA04 — (R02) Publicar; aparece na vitrine; publicar de novo não muda nada | C-07, C-15 |
| F02-CA05 — (R04) Gestão com URL própria, dados, ações e slots | C-09, C-15 |
| F02-CA06 — (R01, R03) Editar nome, local, início, preço e aumentar a lotação; aparece na gestão e na vitrine | C-10, C-15 |
| F02-CA07 — (R13) Lista só com os próprios eventos | C-11, C-15 |
| F02-CA08 — (R13) Outro organizador: 404 sem dados, banco não muda | C-12, C-15 |
| F02-CA09 — (R02) Vitrine pública ordenada pelo início, com link para o detalhe | C-06, C-07, C-08, C-15 |
| XF-01 [F01→F02] — (R13) Evento de A só na lista de A; participante 403 em novo e POST sem efeito; visitante na gestão vai para o login sem dados | C-02, C-03, C-11, C-13, C-14 |

## 4. Fora deste contrato

- Compra, lotação × vagas ocupadas e o conteúdo do bloco `#compra` (F03); listagem da API (F04, XF-05); check-in, painel e cancelamento (F05, F06, F07), cujos slots aqui só precisam existir.
- Evento cancelado na vitrine e na gestão: nenhuma ação da F02 grava `cancelado`; a F07 cobre.
