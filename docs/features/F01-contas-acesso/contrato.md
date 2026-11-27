# Contrato — F01 Contas e acesso

> O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item. Textos esperados vão entre aspas, exatos, e são conferidos com `grep -F`.

- Feature: F01 — Contas e acesso (wave W1)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (F01-CA01…CA06) e 7 (XF-01, XF-02, verificados na F02 e na F03)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- **Antes de tudo**, na raiz do repositório: `git rev-parse HEAD` precisa imprimir exatamente o sha completo pedido para a avaliação, e `git status --porcelain` precisa sair vazio. Se um dos dois não bater, o avaliador **para**, registra no relatório o que encontrou (as duas saídas) e não avalia nenhum item.
- Commit avaliado: o sha informado no pedido de avaliação (branch `feat/F01-contas-acesso`).
- **Banco zerado**, para as contagens baterem: na raiz do repositório, `docker compose --profile '*' down -v` e depois `./scripts/up.sh`, com código 0. Começa com **3** usuários (os da seed).
- Contas da seed (README, "Credenciais"): `org.a@catraca.test` ("Organizadora A"), `org.b@catraca.test` ("Organizador B"), `participante@catraca.test` ("Participante da Seed"), todas com a senha `catraca123`.
- Ferramentas no host: Docker, Git, `curl`, `awk`, `sed`, `grep`. Navegador é opcional.
- **Os itens rodam na ordem**, no mesmo shell, a partir da raiz do repositório, com as funções abaixo definidas uma vez. As contagens de usuários esperadas contam com essa ordem.

```bash
export WEB=http://localhost:8000
D=$(mktemp -d)                      # um arquivo de cookies por "navegador": $D/<nome>
sql()     { docker compose exec -T db psql -U catraca -d catraca -tAc "$1"; }
usuarios(){ sql "select count(*) from dominio_usuario"; }
csrf()    { awk '$6 == "csrftoken" {print $7}' "$1"; }
# GET com cookies; imprime a linha de status e o Location
ver()     { curl -s -o /dev/null -D - -b "$1" -c "$1" "$WEB$2" | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
# GET com cookies; imprime o corpo
corpo()   { curl -s -b "$1" -c "$1" "$WEB$2"; }
# só o bloco #usuario-logado da página
bloco()   { corpo "$1" "$2" | sed -n '/id="usuario-logado"/,/<\/nav>/p'; }
# POST de formulário com CSRF: postar <cookies> <caminho> campo=valor ...
# faz um GET antes (para o csrftoken), imprime status e Location e salva o corpo em <cookies>.html
postar()  { local jar=$1 caminho=$2; shift 2
            curl -s -o /dev/null -b "$jar" -c "$jar" "$WEB$caminho"
            local args=(--data-urlencode "csrfmiddlewaretoken=$(csrf "$jar")")
            for kv in "$@"; do args+=(--data-urlencode "$kv"); done
            curl -s -o "$jar.html" -D - -b "$jar" -c "$jar" "${args[@]}" "$WEB$caminho" \
              | tr -d '\r' | grep -iE '^(HTTP/|location:)'; }
```

"Status 302 e `location: /x`" quer dizer: a linha `HTTP/1.1 302 …` e o cabeçalho `Location` com o valor exato `/x`. Sem `location:` na saída quer dizer sem redirecionamento. Nas tabelas abaixo, `\|` é só o escape do Markdown: no shell e na saída esperada é `|`.

## 2. Itens verificáveis

| Item | Como verificar (comando ou passo) | Resultado esperado |
|---|---|---|
| C-01 | `./scripts/gates.sh` | Código de saída 0; ruff, `manage.py check`, "No changes detected" no `makemigrations --check` e pytest sem falhas; última linha "==> gates: OK". |
| C-02 | Cadastro e bloco do visitante: `ver $D/v /contas/cadastro/`; `corpo $D/v /contas/cadastro/ \| grep -oE 'name="(nome\|email\|senha\|csrfmiddlewaretoken)"' \| sort -u`; `corpo $D/v /contas/cadastro/ \| grep -F 'type="password"'`; `bloco $D/v /` | Status 200. Exatamente 4 linhas: `name="csrfmiddlewaretoken"`, `name="email"`, `name="nome"`, `name="senha"`. O campo de senha tem `type="password"`. O bloco tem "Entrar" e "Criar conta" e não tem "Sair". |
| C-03 | Cadastro válido, com e-mail em caixa mista e espaços: `usuarios`; `postar $D/ana /contas/cadastro/ "nome=Ana Teste" "email= Ana.Teste@Example.COM " "senha=Senha-F01-secreta"`; `usuarios`; `sql "select email, papel, is_staff, is_superuser, left(password, 14) from dominio_usuario where email = 'ana.teste@example.com'"`; `bloco $D/ana /` | `3` antes. Status 302 e `location: /`. `4` depois. Uma linha: `ana.teste@example.com\|participante\|f\|f\|pbkdf2_sha256$`. O bloco contém "Ana Teste", "Meus ingressos" e "Sair" (sessão iniciada). |
| C-04 | Senha em texto em nenhuma coluna de nenhuma tabela: `docker compose exec -T db pg_dump -U catraca -d catraca --data-only \| grep -c 'Senha-F01-secreta'`; o mesmo com `'catraca123'` | `0` nas duas (o `grep` sai com código 1, o que é esperado). |
| C-05 | E-mail já cadastrado, com caixa diferente: `postar $D/dup /contas/cadastro/ "nome=Outra Ana" "email=ANA.TESTE@example.com" "senha=OutraSenha-123"`; `grep -F "Já existe uma conta com este e-mail." $D/dup.html`; `usuarios` | Status 200, sem `location:`. A mensagem aparece. `4` (não mudou). |
| C-06 | E-mail mal formado: `postar $D/mal /contas/cadastro/ "nome=Bia" "email=bia@" "senha=Senha-Bia-123"`; `grep -F "Informe um e-mail válido." $D/mal.html`; `usuarios` | Status 200, sem `location:`. A mensagem aparece. `4`. |
| C-07 | Campos vazios e senha curta: (a) `postar $D/vaz /contas/cadastro/ "nome=   " "email=" "senha="` e `grep -F` de cada mensagem em `$D/vaz.html`; (b) `postar $D/cur /contas/cadastro/ "nome=Caio" "email=caio@example.com" "senha=1234567"`, `grep -F "A senha precisa ter pelo menos 8 caracteres." $D/cur.html`, `grep -F 'value="caio@example.com"' $D/cur.html`, `grep -c '1234567' $D/cur.html`; `usuarios` | (a) Status 200; aparecem "Informe o seu nome.", "Informe o seu e-mail." e "Informe uma senha.". (b) Status 200; a mensagem aparece; o e-mail volta preenchido; `0` (a senha não volta no HTML). `4`. |
| C-08 | Cadastro sem token CSRF: `curl -s -o $D/semcsrf.html -w '%{http_code}\n' --data-urlencode "nome=Sem Csrf" --data-urlencode "email=sem.csrf@example.com" --data-urlencode "senha=SenhaValida-1" $WEB/contas/cadastro/`; `grep -F "Acesso negado" $D/semcsrf.html`; `usuarios` | `403`; a página genérica aparece; `4`. |
| C-09 | (R13) Campo extra de papel: `postar $D/esp /contas/cadastro/ "nome=Esperto" "email=esperto@example.com" "senha=Senha-Esperta-1" "papel=organizador" "is_staff=1" "is_superuser=1"`; `sql "select papel, is_staff, is_superuser from dominio_usuario where email = 'esperto@example.com'"`; `ver $D/esp /organizador/`; `corpo $D/esp /organizador/ \| grep -F "Acesso negado"`; `corpo $D/esp /organizador/ \| grep -c "Meus eventos"`; `usuarios` | Status 302 e `location: /`. `participante\|f\|f`. Status 403. "Acesso negado" aparece. `0`. `5`. |
| C-10 | Nome é escapado: `postar $D/xss /contas/cadastro/ "nome=<b>Xss</b>" "email=xss@example.com" "senha=Senha-Xss-123"`; `bloco $D/xss / \| grep -F '&lt;b&gt;Xss&lt;/b&gt;'`; `bloco $D/xss / \| grep -c '<b>Xss</b>'`; `usuarios` | Status 302 e `location: /`. A forma escapada aparece. `0`. `6`. |
| C-11 | Entrar válido: (a) `postar $D/oa /contas/entrar/ "email=ORG.A@catraca.test" "senha=catraca123"`, `grep -c sessionid $D/oa`, `ver $D/oa /organizador/`, `corpo $D/oa /organizador/ \| grep -F "Meus eventos"`, `bloco $D/oa /organizador/`; (b) `postar $D/pa /contas/entrar/ "email=participante@catraca.test" "senha=catraca123"`, `bloco $D/pa /` | (a) Status 302 e `location: /organizador/`; `1`; status 200; "Meus eventos" aparece; o bloco contém "Organizadora A", "Área do organizador" e "Sair", e não contém "Meus ingressos". (b) Status 302 e `location: /`; o bloco contém "Participante da Seed", `href="/meus-ingressos/"`, "Meus ingressos" e "Sair". |
| C-12 | Entrar inválido, cada caso com cookies novos: (a) `postar $D/e1 /contas/entrar/ "email=org.a@catraca.test" "senha=senha-errada"`; (b) `postar $D/e2 /contas/entrar/ "email=ninguem@catraca.test" "senha=catraca123"`; (c) `postar $D/e3 /contas/entrar/ "email=" "senha="`; em cada um: `grep -F "E-mail ou senha inválidos." $D/eN.html` e `grep -c sessionid $D/eN`; depois `ver $D/e1 /organizador/` | Nos três: status 200, sem `location:`; a mensagem aparece; `0` (sem sessão). Por fim, status 302 e `location: /contas/entrar/?next=/organizador/`. |
| C-13 | `?next=` (cookies novos em cada login, porque quem já está logado vai sempre ao destino padrão): (a) `ver $D/n0 /organizador/` e `corpo $D/n0 '/contas/entrar/?next=/organizador/' \| grep -F 'name="next" value="/organizador/"'`; (b) `postar $D/n1 /contas/entrar/ "email=participante@catraca.test" "senha=catraca123" "next=/eventos/evt_ab12cd34/"`; (c) `postar $D/n2 /contas/entrar/ "email=org.a@catraca.test" "senha=catraca123" "next=https://evil.example/"`; (d) o mesmo com `"next=//evil.example/"` em `$D/n3`; (e) o mesmo com `"next=/\evil.example"` em `$D/n4` | (a) Status 302 e `location: /contas/entrar/?next=/organizador/`; o campo oculto aparece. (b) Status 302 e `location: /eventos/evt_ab12cd34/` (caminho interno é aceito, mesmo que a página ainda não exista). (c), (d), (e) Status 302 e `location: /organizador/` (destino padrão; endereço externo ignorado). |
| C-14 | Já autenticado: `ver $D/oa /contas/entrar/`; `ver $D/pa /contas/cadastro/`; `usuarios` | Status 302 e `location: /organizador/`; status 302 e `location: /`; `6`. |
| C-15 | Sair: `postar $D/s /contas/entrar/ "email=org.b@catraca.test" "senha=catraca123"`; `ANTIGO=$(awk '$6 == "sessionid" {print $7}' $D/s)`; `ver $D/s /contas/sair/`; `ver $D/s /organizador/`; `curl -s -o /dev/null -w '%{http_code}\n' -b $D/s -X POST $WEB/contas/sair/`; `ver $D/s /organizador/`; `postar $D/s /contas/sair/`; `ver $D/s /organizador/`; `curl -s -o /dev/null -D - -H "Cookie: sessionid=$ANTIGO" $WEB/organizador/ \| tr -d '\r' \| grep -iE '^(HTTP/\|location:)'` | Status 302 (`location: /organizador/`). `GET` de sair: status 405, e a sessão continua (`/organizador/` → 200). `POST` sem token: `403`, e a sessão continua (200). `POST` com token: status 302 e `location: /`. Depois, `/organizador/` → 302 e `location: /contas/entrar/?next=/organizador/`, inclusive reenviando o cookie de sessão antigo. |
| C-16 | Seed rodada duas vezes: `usuarios`; `docker compose exec -T web python manage.py seed; echo "código: $?"` (duas vezes); `usuarios`; `sql "select email, nome, papel from dominio_usuario where email like '%@catraca.test' order by email"`; depois, com cookies novos, `postar` em `/contas/entrar/` com cada uma das três contas e a senha `catraca123` | `6` antes e depois. As duas execuções terminam com a linha "seed: concluída" e "código: 0". Exatamente três linhas: `org.a@catraca.test\|Organizadora A\|organizador`, `org.b@catraca.test\|Organizador B\|organizador`, `participante@catraca.test\|Participante da Seed\|participante`. Os logins: status 302 com `location: /organizador/` (org.a, org.b) e `location: /` (participante). |
| C-17 | (R13) Guarda de `/organizador/` nos três papéis, `GET` e `POST`: visitante `ver $D/g1 /organizador/`; visitante com token `ver $D/g1 /contas/entrar/ >/dev/null; postar $D/g1 /organizador/`; participante (`$D/pa` de C-11) `ver $D/pa /organizador/`, `corpo $D/pa /organizador/ \| grep -F "Acesso negado"`, `corpo $D/pa /organizador/ \| grep -c "Meus eventos"` e `postar $D/pa /organizador/`; organizador `ver $D/oa /organizador/` | Visitante `GET`: status 302 e `location: /contas/entrar/?next=/organizador/`. Visitante `POST`: status 302 e `location: /contas/entrar/`. Participante: status 403, "Acesso negado", `0`, e o `POST` também 403. Organizador: status 200. |
| C-18 | Teste que percorre todas as rotas registradas sob `/organizador/`: `./scripts/gates.sh web/tests/test_acesso.py::test_rotas_do_organizador_barram_visitante_e_participante` | Código 0 e "1 passed". |
| C-19 | Testes automatizados da feature: `./scripts/gates.sh -v dominio/tests/test_contas.py web/tests/test_contas.py web/tests/test_acesso.py` | Código 0, nenhum "FAILED" nem "SKIPPED", e aparecem como PASSED pelo menos: `test_cadastrar_participante_cria_participante_com_senha_em_hash`, `test_cadastrar_participante_rejeita_email_duplicado`, `test_cadastrar_participante_valida_campos`, `test_cadastrar_participante_converte_integrity_error_em_email_ja_cadastrado`, `test_cadastro_ignora_papel_organizador_e_flags_de_equipe`, `test_cadastro_exige_csrf`, `test_cadastro_respeita_next_interno`, `test_entrar_invalido_mostra_mensagem_sem_sessao`, `test_entrar_respeita_next_interno_e_ignora_externo`, `test_sair_exige_post_e_csrf_e_encerra_sessao`, `test_organizador_requerido_por_papel`, `test_participante_requerido_por_papel`, `test_guardas_em_post_de_visitante_nao_executam_a_view`, `test_area_do_organizador_por_papel`, `test_usuario_logado_por_papel`, `test_usuario_logado_escapa_o_nome`. |

Ao terminar: `./scripts/down.sh` e `rm -rf "$D"`.

## 3. Mapeamento critério do PRD → itens

| Critério do PRD | Itens |
|---|---|
| F01-CA01 — Cadastro (campos, participante, hash, sessão, vitrine com o nome) | C-02, C-03, C-04, C-10, C-19 |
| F01-CA02 — Cadastro inválido (duplicado, mal formado, vazio; contagem não muda) | C-05, C-06, C-07, C-08, C-19 |
| F01-CA03 — (R13) `papel=organizador` cria participante, que recebe 403 em `/organizador/` | C-09, C-19 |
| F01-CA04 — Entrar e sair ("E-mail ou senha inválidos."; após sair, `/organizador/` → 302 login) | C-11, C-12, C-13, C-14, C-15, C-19 |
| F01-CA05 — Seed rodada duas vezes, uma conta de cada, as três entram | C-16 |
| F01-CA06 — (R13) Guarda de `/organizador/` e teste que percorre as rotas | C-17, C-18, C-13 (a), C-19 |

## 4. Fora deste contrato

- **XF-01 [F01→F02]** e **XF-02 [F01→F03]**: dependem de eventos e de compra; são verificados nos contratos da F02 e da F03. O que a F01 provê para eles (participante barrado em `GET` e `POST` sob `/organizador/`, visitante levado ao login sem a view executar, organizador barrado em `participante_requerido`) está em C-17, C-18 e C-19.
- **O link "Meus ingressos" leva à página 404 genérica até a F03** registrar `/meus-ingressos/` (spec 3.8). C-11 só confere que o link existe para o participante e não existe para o organizador.
- `/organizador/` mostra só o esqueleto ("Meus eventos", sem lista); a lista é da F02.
- O modelo `Usuario`, a migration `0001` e a seed são da W0 (H-01…H-08, já verificados); aqui a seed só é conferida (C-16).
- Recuperação de senha, confirmação de e-mail, edição de perfil e limite de tentativas de login estão fora de escopo (PRD, seção 10).
