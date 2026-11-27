# Spec — F03 Compra, lotação e gateway (W3)

- PRD: [docs/prd.md](../../prd.md), seções 3.2 (F03), 6 (F03-CA01…CA14) e 7 (XF-02, XF-03, XF-04, atribuídos a esta feature).
- Regras: R03, R05, R06, R07, R08, R09; base de R11 e R12.
- Consome: W0 (`Usuario`), F01 (`participante_requerido`, participante autenticado), F02 (`Evento`, `evento_a_venda`, `editar_evento` com `_validar_edicao`, slot `#compra`).
- Plano: [plano.md](plano.md) · Contrato: [contrato.md](contrato.md).

## 1. Escopo

O participante compra um ingresso por vez na vitrine com um número de cartão. A compra nasce pendente, ocupa vaga e é respondida sem esperar o gateway; nunca passa da lotação, nem sob compras simultâneas (R07). Um gateway simulado, num worker em container próprio, aprova ou recusa conforme o final do cartão e o atraso da tabela do brief; a resposta só muda ingresso pendente. O participante vê os próprios ingressos em "Meus ingressos". O preço vigente é gravado no ingresso; a lotação não pode ficar abaixo das vagas ocupadas.

Fica fora: API de parceiros (F04), check-in (F05, mas o campo `check_in_em` nasce aqui), painel (F06), cancelamento (F07).

## 2. Domínio

### 2.1 Modelos (migration nova `dominio/0003_ingresso_cobranca`)

**`dominio.Ingresso`**

| Campo | Tipo | Regra |
|---|---|---|
| `id_publico` | `CharField(12, unique)` | `tkt_` + 8 de `[a-z0-9]` (mesmo gerador do evento); colisão → outro, até 5 tentativas |
| `codigo` | `CharField(8, unique)` | 8 caracteres de `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (maiúsculas e dígitos, sem `I`, `O`, `0` e `1`); `CheckConstraint codigo ~ '^[A-Z0-9]{8}$'`; colisão → outro |
| `evento` | `ForeignKey(Evento, PROTECT, related_name="ingressos")` | |
| `comprador` | `ForeignKey(Usuario, PROTECT, null=True, related_name="ingressos")` | nulo nas compras da API |
| `email_comprador` | `EmailField(254)` | e-mail do participante (vitrine) ou `buyerEmail` (API) |
| `canal` | `CharField(10)` com `TextChoices` | `vitrine`, `api` |
| `status` | `CharField(10)` com `TextChoices` | `pending` "pendente", `confirmed` "confirmado", `declined` "recusado", `cancelled` "cancelado", `refunded` "estornado"; padrão `pending` |
| `valor_centavos` | `PositiveIntegerField` | preço do evento no momento da compra (R03, R12); `> 0` |
| `cartao_final` | `CharField(4)` | só os 4 últimos dígitos; `CheckConstraint ~ '^[0-9]{4}$'` |
| `check_in_em` | `DateTimeField(null=True)` | nulo; só a F05 preenche |
| `criado_em` | `DateTimeField(default=now)` | |

Índice em (`evento`, `status`) para a contagem de vagas.

**`dominio.CobrancaGateway`**

| Campo | Tipo | Regra |
|---|---|---|
| `ingresso` | `OneToOneField(Ingresso, CASCADE, related_name="cobranca")` | |
| `resultado` | `CharField` com `TextChoices` | `aprovado`, `recusado` (sorteado pelo final do cartão na compra) |
| `responder_em` | `DateTimeField` | criação + atraso sorteado |
| `processada_em` | `DateTimeField(null=True)` | nulo até o worker processar |

Índice parcial em `responder_em` com `processada_em IS NULL`.

### 2.2 Exceções (em `dominio/excecoes.py`)

- `CartaoInvalido(ValidacaoError)`: `erros = {"cartao": ["O número do cartão precisa ter 16 dígitos."]}`.
- `IngressosEsgotados(ErroDeDominio)`: sem vaga disponível; a vitrine exibe "Ingressos esgotados" (R07).
- `IngressoNaoEncontrado(ErroDeDominio)`.
- E-mail do comprador mal formado: `ValidacaoError({"email_comprador": ["Informe um e-mail válido."]})` (usado pela F04).

### 2.3 Gateway simulado — `dominio/servicos/gateway.py`

`GatewaySimulado` com a tabela do brief, pelo final (4 últimos dígitos) do cartão:

| Final | Resultado | Atraso sorteado (modo padrão) |
|---|---|---|
| `0001` | aprovado | uniforme em [2, 4] s |
| `0002` | recusado | [2, 4] s |
| `0003` | aprovado | [32, 38] s |
| `0004` | recusado | [32, 38] s |
| outro | recusado | [2, 4] s |

- `resultado_para(cartao) -> bool` (aprovado?) e `atraso_para(cartao, aleatorio=random) -> timedelta`. As faixas ficam dentro das do brief com folga: os rápidos confirmam antes de 5 s, os lentos seguem pendentes aos 30 s e estão resolvidos aos 45 s.
- **Fator de atraso só para testes.** `settings.GATEWAY_FATOR_ATRASO` vem da variável de ambiente de mesmo nome, com padrão `1`; o atraso sorteado é multiplicado por ele. O `compose.yaml` **não** define essa variável; só os testes a mudam (via `settings`).
- `aplicar_resposta_gateway(ingresso_id, aprovado) -> bool`: um único `UPDATE dominio_ingresso SET status = <confirmed|declined> WHERE id = <id> AND status = 'pending'` (`filter(...).update(...)`); devolve `True` se mudou uma linha, `False` se o ingresso não estava pendente (R08, R11). Nunca lê e grava em dois passos.
- `processar_cobrancas_vencidas(agora=None) -> int`: em lotes, numa transação, seleciona cobranças com `processada_em IS NULL` e `responder_em <= agora` com `select_for_update(skip_locked=True)`; para cada uma chama `aplicar_resposta_gateway` e marca `processada_em = agora` **mesmo quando não mudou nada** (F03-CA12). Devolve quantas processou.
- **Worker** (`python manage.py gateway_worker`, serviço `gateway` do Compose, já existente na W0): a cada 0,5 s chama `processar_cobrancas_vencidas`. Erros de banco (ex.: o Postgres reiniciando) são registrados no log e a volta seguinte tenta de novo, depois de `close_old_connections()`. Como as cobranças ficam no banco, derrubar e subir o ambiente não perde nenhuma: as vencidas são processadas na primeira volta (F03-CA14).

### 2.4 Compra e vagas — `dominio/servicos/compras.py`

- `vagas_ocupadas(evento) -> int`: ingressos `pending` + `confirmed` do evento (R05).
- `vagas_disponiveis(evento) -> int`: `0` se o evento está `cancelado`; senão `max(0, lotacao - vagas_ocupadas)` (R05).
- `comprar_ingresso(evento_id, *, cartao, email_comprador, canal, comprador=None) -> Ingresso`, nesta ordem:
  1. **Valida o cartão** (texto sem espaços nas pontas casando com `^[0-9]{16}$`; senão `CartaoInvalido`) e o e-mail do comprador (`validate_email`; senão `ValidacaoError`). Nada é lido do banco antes disso.
  2. Abre uma transação e **trava a linha do evento**: `Evento.objects.select_for_update().get(id_publico=evento_id)`. Inexistente, rascunho ou cancelado → `EventoIndisponivel` (R02).
  3. Com a linha travada, **conta as ocupadas** e, se `ocupadas >= lotacao`, lança `IngressosEsgotados` (R07). Em READ COMMITTED, a contagem feita depois de obter a trava enxerga os ingressos das transações que a seguraram antes, então duas compras do mesmo evento nunca contam as mesmas vagas livres.
  4. Cria o `Ingresso` `pending` com `valor_centavos = evento.preco_centavos` (R03, R12), `cartao_final = cartao[-4:]`, `canal`, `comprador`, `email_comprador` normalizado, `codigo` e `id_publico` novos; e a `CobrancaGateway` com `resultado_para(cartao)` e `responder_em = agora + atraso_para(cartao)`. Não espera o gateway (R06).
  O número inteiro do cartão nunca é gravado nem registrado em log.
- `ingressos_do_participante(usuario)`: os ingressos com `comprador = usuario`, com o evento, do mais novo para o mais antigo.
- `consultar_ingresso(ticket_id) -> Ingresso`: por `id_publico`; `IngressoNaoEncontrado` se não existe.
- **Extensão de `editar_evento` (R03).** `_validar_edicao` (F02), chamada com a linha do evento travada, passa a rejeitar `lotacao < vagas_ocupadas(evento)` com a mensagem exata "A lotação não pode ser menor que as vagas ocupadas (N)." no campo `lotacao`, onde N é o número de ocupadas. Compra, edição e (na F07) cancelamento usam a mesma trava, então são serializados.

## 3. Web

### 3.1 Bloco `#compra` no detalhe `/eventos/<id>/`

O detalhe (F02) passa a calcular `vagas_disponiveis(evento)` e o parcial `web/vitrine/_compra.html` mostra, dentro de `<section id="compra">`:

- sempre: `<p>Vagas disponíveis: <span data-campo="vagas-disponiveis">N</span></p>`;
- com vaga: para participante logado, o formulário `#form-compra` (`POST /eventos/<id>/comprar/`, campo `cartao`, botão "Comprar"); para visitante, no lugar do formulário, o link "Entre para comprar" (`/contas/entrar/?next=/eventos/<id>/`); para organizador, o texto "Compras são feitas com uma conta de participante.";
- sem vaga: `<p id="esgotado">Ingressos esgotados</p>` e nenhum formulário (R07);
- quando a compra falha: a mensagem de erro em `<p class="erro" id="erro-compra">`.

### 3.2 `POST /eventos/<id>/comprar/`

`participante_requerido` (mais externo; visitante → 302 `/contas/entrar/`, organizador → 403) e `require_POST`. Chama `comprar_ingresso(id, cartao=POST["cartao"], email_comprador=user.email, canal="vitrine", comprador=user)`:

| Resultado | Resposta |
|---|---|
| sucesso | 302 para `/meus-ingressos/`, com a mensagem "Compra registrada. O pagamento está sendo processado." |
| `CartaoInvalido` | 200 com o detalhe e "O número do cartão precisa ter 16 dígitos." em `#erro-compra` |
| `IngressosEsgotados` | 200 com o detalhe e "Ingressos esgotados" (`#erro-compra`; o bloco também mostra `#esgotado`) |
| `EventoIndisponivel` | 404 genérico (vale também quando o cartão é inválido e o evento não está à venda: o domínio acusa o cartão primeiro, e a vitrine, sem evento para reexibir, responde 404) |

Nenhum dos erros cria ingresso nem cobrança.

### 3.3 `GET /meus-ingressos/`

`participante_requerido`. `<table id="meus-ingressos">` com uma linha por ingresso de `ingressos_do_participante`; cada `<tr>`, com os seus três `<td>`, fica inteiro numa única linha do HTML: `<tr data-ingresso="<tkt_…>" data-status="<valor>">` e com `<td data-campo="evento">nome</td>`, `<td data-campo="status">rótulo</td>` (pendente, confirmado, recusado, cancelado, estornado) e `<td data-campo="codigo">CÓDIGO</td>`. Sem ingressos: "Você ainda não tem ingressos.". O status é lido do banco a cada carga (recarregar mostra o novo).

### 3.4 Edição de lotação na gestão

Nada muda na tela da F02: a mensagem de `_validar_edicao` chega no formulário de edição como as outras (200, `#form-evento` com o erro no campo lotação).

## 4. Testes

- `dominio/tests/test_compras.py`: compra cria pendente com preço gravado e só o final do cartão; cartão inválido (15, 17 dígitos, letras, vazio) e e-mail inválido sem criar nada; evento rascunho, cancelado e inexistente; esgotado; pendente ocupa vaga; recusado libera; cancelado zera; preço gravado × preço novo; lotação × ocupadas na edição; códigos únicos e no formato; consulta.
- `dominio/tests/test_gateway.py`: tabela de resultados; faixas de atraso com semente (1000 sorteios em cada faixa); fator multiplica; `aplicar_resposta_gateway` condicional nos cinco status; `processar_cobrancas_vencidas` processa só as vencidas e marca processada mesmo sem mudança; worker com `--voltas`.
- `dominio/tests/test_concorrencia.py` (F03-CA06): `django_db(transaction=True)`; 30 threads, uma `threading.Barrier(30)`, cada uma chama `comprar_ingresso` no mesmo evento de lotação 5 e fecha a própria conexão; exatamente 5 ingressos e 25 `IngressosEsgotados`; repetido em 10 eventos novos, e `vagas_ocupadas` termina em 5 em todos.
- `web/tests/test_compras.py`: bloco `#compra` (com vaga, sem vaga, visitante), compra pela tela, erros da tela, 404, visitante e organizador barrados, Meus ingressos só com os próprios, edição de lotação pela tela.

## 5. Critérios cross desta feature

- **XF-02 [F01→F03]**: conta criada pelo cadastro compra e vê o ingresso em Meus ingressos; o participante da seed não o vê; visitante no `POST` de compra vai para o login sem criar ingresso.
- **XF-03 [F02→F03]**: evento criado e publicado pela gestão aparece com o formulário e a compra funciona; enquanto rascunho, o `POST` de compra dava 404 sem criar ingresso.
- **XF-04 [F02→F03]**: na edição da gestão, com 2 ocupadas, lotação 1 é rejeitada com a mensagem da F03; preço "150,00" e lotação 3 aceitos; a compra seguinte grava 15000 e as anteriores continuam com 10000.

## 6. Decisões menores

- O código do ingresso evita `I`, `O`, `0` e `1` para não confundir na digitação do check-in; continua com 8 caracteres maiúsculos (letras e dígitos).
- Um participante pode comprar mais de um ingresso do mesmo evento, uma compra por vez (o brief não limita).
- O organizador não compra pela vitrine (403): compras são de participante (R06) ou do parceiro (F04).
