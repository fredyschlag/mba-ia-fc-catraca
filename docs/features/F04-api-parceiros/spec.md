# Spec — F04 API de parceiros (W4)

- PRD: [docs/prd.md](../../prd.md), seções 3.2 (F04), 6 (F04-CA01…CA10) e 7 (XF-05, XF-06, atribuídos a esta feature).
- Regras: R02, R05, R06, R07 (canal API); o contrato fixo da API de parceiros do [brief](../../brief.md).
- Consome: F02 (`eventos_a_venda`, `Evento.id_publico`, criação e publicação pela interface), F03 (`comprar_ingresso`, `vagas_disponiveis`, `consultar_ingresso`, campos de `Ingresso`, worker do gateway).
- Plano: [plano.md](plano.md) · Contrato: [contrato.md](contrato.md).

## 1. Escopo

As três rotas do contrato fixo do brief, autenticadas só pela chave de parceiro (`X-Api-Key`), com os erros na ordem 401 > 422 > 404 > 409. A compra pela API usa o mesmo `comprar_ingresso` da vitrine (mesma trava de lotação, mesmo preço gravado, mesmo gateway); a API não tem regra de negócio própria. Entra também `scripts/rajada-api.sh`, que prova R07 pela API em eventos novos.

Fica fora: check-in (F05; a API só lê `check_in_em`), painel (F06), cancelamento (F07; aqui o evento cancelado só precisa responder 404 e sumir da listagem, o que já sai de `eventos_a_venda` e `comprar_ingresso`). Gestão de chaves, limite de taxa e paginação estão fora de escopo (PRD, seção 10).

## 2. Rotas (`api_parceiros/urls.py`, já incluído em `catraca/urls.py` sob `api/partner/`)

Sem barra no fim, exatamente como no brief:

| Método e rota | View | Sucesso |
|---|---|---|
| `GET /api/partner/events` | `api_parceiros.views.eventos` | 200, array JSON de `evento_para_api` |
| `POST /api/partner/events/<str:evento_id>/purchases` | `api_parceiros.views.comprar` | 202, `compra_para_api` |
| `GET /api/partner/tickets/<str:ticket_id>` | `api_parceiros.views.ingresso` | 200, `ingresso_para_api` |

Cada view é, de fora para dentro: `csrf_exempt` → `exigir_chave_parceiro` → checagem do método (método errado → 405 `{"error":"method_not_allowed"}` com o cabeçalho `Allow`). Assim a chave é conferida antes de qualquer outra coisa, inclusive do método, do corpo e da existência do evento ou do ingresso. As views não usam sessão, login nem `request.user`; não gravam cookie.

`/api/partner/events/` (com barra) não é rota da API e cai no 404 padrão do Django; o contrato fixo não tem barra.

## 3. Autenticação — `api_parceiros/auth.py`

`exigir_chave_parceiro(view)`: decorador que lê `request.headers.get("X-Api-Key")` e compara com `settings.CATRACA_CHAVE_PARCEIRO` usando `hmac.compare_digest` sobre os bytes UTF-8 (tempo constante). Responde 401 `{"error":"unauthorized"}` quando:

- o cabeçalho falta ou está vazio;
- a chave não bate;
- a configuração está vazia (`CATRACA_CHAVE_PARCEIRO = ""`): chave vazia nunca autentica, nem com cabeçalho vazio.

A chave de desenvolvimento é `chave-parceiro-dev` (`compose.yaml` e README, "Credenciais"). Nenhuma chave aparece em log.

## 4. Respostas JSON — `api_parceiros/respostas.py`

- `responder(dados, status)`: `JsonResponse(dados, status=status, safe=False)` com JSON compacto (separadores `,` e `:`, sem espaços), UTF-8 sem escapar acentos (`ensure_ascii=False`) e `Content-Type: application/json`. As chaves saem na ordem do brief, então o corpo é byte a byte previsível (ex.: `{"error":"unauthorized"}`), o que deixa o contrato conferir o JSON inteiro com `grep -F`/`grep -E`.
- `erro(codigo, status)`: `responder({"error": codigo}, status)`.

| Código | Status | Quando |
|---|---|---|
| `unauthorized` | 401 | chave ausente, vazia ou errada; configuração vazia |
| `invalid_request` | 422 | corpo inválido (seção 6) |
| `event_not_available` | 404 | `EventoIndisponivel`: evento inexistente, em rascunho ou cancelado |
| `sold_out` | 409 | `IngressosEsgotados` |
| `ticket_not_found` | 404 | `IngressoNaoEncontrado` |
| `method_not_allowed` | 405 | método diferente do da rota (depois da chave) |

## 5. Serializadores — `api_parceiros/serializadores.py`

- `evento_para_api(evento) -> dict`: `{"id": evento.id_publico, "name": evento.nome, "startsAt": <início>, "priceCents": evento.preco_centavos, "availableSeats": vagas_disponiveis(evento)}`. `startsAt` = `timezone.localtime(evento.inicio)` (fuso `America/Sao_Paulo`) sem microssegundos, em `isoformat()`: `2027-06-15T21:00:00-03:00`. `priceCents` e `availableSeats` são inteiros.
- `ingresso_para_api(ingresso) -> dict`: `{"ticketId": id_publico, "code": codigo, "eventId": evento.id_publico, "status": status, "checkedIn": check_in_em is not None}`; `status` é o valor (`pending`, `confirmed`, `declined`, `cancelled`, `refunded`).
- `compra_para_api(ingresso) -> dict`: `{"ticketId": id_publico, "code": codigo, "status": status}` (na compra, sempre `pending`).

Os serializadores só leem atributos e chamam `vagas_disponiveis` do domínio.

## 6. Compra — `POST /api/partner/events/{eventId}/purchases`

1. Chave (seção 3) → 401.
2. **Leitura do corpo** (formato da requisição, não regra de negócio): decodifica o corpo como JSON UTF-8. Lança `ValidacaoError` (→ 422) quando o corpo é vazio, não é JSON, não é um objeto, ou `buyerEmail`/`cardNumber` falta ou não é string. O `Content-Type` da requisição não é exigido; campos extras são ignorados.
3. Chama `comprar_ingresso(evento_id, cartao=cardNumber, email_comprador=buyerEmail, canal=Ingresso.Canal.API, comprador=None)`. O domínio valida cartão (16 dígitos) e e-mail **antes** de tocar no banco, então e-mail mal formado e cartão inválido dão 422 mesmo com evento inexistente (422 antes de 404); depois, com a linha do evento travada, `EventoIndisponivel` (inexistente, rascunho, cancelado — cancelado é 404, não 409) e então `IngressosEsgotados`.
4. Tradução: `ValidacaoError` (inclui `CartaoInvalido`) → 422 `invalid_request`; `EventoIndisponivel` → 404 `event_not_available`; `IngressosEsgotados` → 409 `sold_out`; sucesso → 202 `compra_para_api`.

O ingresso fica com `canal=api`, `comprador` nulo, `email_comprador` = `buyerEmail` normalizado (minúsculo, sem espaços nas pontas, como o domínio já faz), `valor_centavos` = preço vigente e só o final do cartão. A resposta não espera o gateway (R06). Nenhum erro cria ingresso nem cobrança.

## 7. Listagem e consulta

- `GET /api/partner/events`: `[evento_para_api(e) for e in eventos_a_venda()]` (publicados, ordenados pelo início; rascunho e cancelado ficam fora). Sem eventos: `[]`.
- `GET /api/partner/tickets/{ticketId}`: `consultar_ingresso(ticket_id)` → 200 `ingresso_para_api`; `IngressoNaoEncontrado` → 404 `ticket_not_found`. Vale para ingresso de qualquer canal (vitrine ou API).

## 8. `scripts/rajada-api.sh`

Bash + `curl` + utilitários POSIX (sem `jq`, sem Python no host). Uso: `./scripts/rajada-api.sh [rodadas]` (padrão 5).

- Porta de `CATRACA_PORTA` (padrão 8000); chave de `CATRACA_CHAVE_PARCEIRO` (padrão `chave-parceiro-dev`, a do README).
- Faz login como `org.a@catraca.test` pelo formulário `/contas/entrar/` (cookie + `csrfmiddlewaretoken`) num diretório temporário próprio (`mktemp -d`, apagado na saída).
- Em cada rodada, cria pela interface um evento novo de lotação 5 (`/organizador/eventos/novo/`, data no ano seguinte), pega o id no `Location` e publica (`/organizador/eventos/<id>/publicar/`).
- Dispara o comando do passo 15: `seq 30 | xargs -P 30 -I{} curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-Api-Key: …" -H "Content-Type: application/json" -d '{"buyerEmail":"rajada{}@example.com","cardNumber":"4000000000000001"}' "$API/api/partner/events/<id>/purchases"`, guarda os 30 códigos e imprime `sort | uniq -c`.
- A rodada passa só com exatamente 30 respostas, 5 `202` e 25 `409`. Imprime `rodada N (<id>): OK` ou `FALHOU`; no fim, `rajada-api: OK (N rodadas)` com código 0, ou `rajada-api: FALHOU` com código 1. Falha de login, de criação ou de publicação também sai com código ≠ 0.

## 9. Testes

`api_parceiros/tests/` com o client do Django (`client.get(url, HTTP_X_API_KEY=…)`, `client.post(url, corpo, content_type="application/json", HTTP_X_API_KEY=…)`); um `conftest.py` fixa a chave de teste em `settings.CATRACA_CHAVE_PARCEIRO` (autouse) e cria organizador, participante e eventos pelos serviços do domínio. Evento cancelado e check-in (de F07 e F05) são simulados nos testes com `update` direto no banco.

- `test_auth.py`: 401 nas três rotas sem chave, com chave errada e com chave vazia, inclusive com corpo inválido e evento/ingresso inexistente; configuração vazia nunca autentica; chave certa passa; comparação com `hmac.compare_digest`; views isentas de CSRF (POST com `Client(enforce_csrf_checks=True)` passa); nenhuma resposta grava cookie.
- `test_eventos.py`: listagem só com publicados, na ordem do início, com exatamente os cinco campos e o formato de `startsAt`; `availableSeats` = `vagas_disponiveis` (pendente ocupa, recusado libera); rascunho e cancelado fora; lista vazia `[]`; JSON compacto e `Content-Type`.
- `test_compras.py`: 202 com exatamente três campos e o ingresso gravado (`canal=api`, comprador nulo, e-mail, preço, final); cada corpo inválido → 422 sem criar nada; 422 antes de 404; 404 para inexistente, rascunho e cancelado (inclusive cancelado lotado: 404, não 409); 409 sem vaga sem criar nada; 405 para método errado.
- `test_ingressos.py`: consulta com exatamente cinco campos, nos cinco status; `checkedIn` verdadeiro com `check_in_em`; ingresso da vitrine consultável com o mesmo `code`; 404 `ticket_not_found`.
- `test_camada.py`: o grep do F04-CA10 em Python (nenhum `objects.create`, `objects.update`, `filter(…).update` nem `.save(` em `api_parceiros/` fora de `tests/`); o script `scripts/rajada-api.sh` existe, é executável e usa `xargs -P 30`.

## 10. Critérios cross desta feature

- **XF-05 [F02→F04]**: evento criado como rascunho pela gestão não aparece em `GET /api/partner/events`; publicado, aparece com o mesmo `id` da URL de gestão, `priceCents` 10000 e `availableSeats` igual à lotação.
- **XF-06 [F03→F04]**: mesma lotação e mesmo gateway na API e na vitrine: compra da API que ocupa a última vaga faz a vitrine mostrar "Ingressos esgotados"; compra da vitrine que ocupa a última vaga faz a API responder 409 `sold_out`; final `0001` pela API `confirmed` em até 5 s; `0004` pela API `pending` aos 30 s (com `availableSeats` 0) e `declined` antes de 45 s, devolvendo a vaga; ingresso da vitrine consultável na API com o mesmo `code`.

## 11. Decisões menores

- A API não exige `Content-Type: application/json` na requisição: o corpo é lido como JSON de qualquer forma (o avaliador sempre manda o cabeçalho; ser tolerante não muda nenhum caso do brief).
- `buyerEmail` é gravado normalizado em minúsculas, como o e-mail das contas.
- Ingresso de evento cancelado continua consultável (com o status que o cancelamento der, na F07).
- 405 com JSON em vez do HTML vazio do Django, para a API só responder JSON nas suas rotas.
