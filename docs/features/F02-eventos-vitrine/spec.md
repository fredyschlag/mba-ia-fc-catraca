# Spec — F02 Eventos e vitrine (W2)

- PRD: [docs/prd.md](../../prd.md), seções 3.2 (F02), 6 (F02-CA01…CA09) e 7 (XF-01, atribuído a esta feature).
- Regras: R01, R02, R04, R13.
- Consome: W0 (`Usuario` com `papel`, seed), F01 (`organizador_requerido`, `/organizador/`). Usa também o `base.html` e as páginas 404/403 genéricas da W0/F01, que são infraestrutura e não Provides.
- Plano: [plano.md](plano.md) · Contrato: [contrato.md](contrato.md).

## 1. Escopo

O organizador cria eventos (nascem em rascunho), edita, publica e vê a lista dos próprios eventos; cada evento tem uma página de gestão com URL própria, com slots vazios para cancelamento (F07), check-in (F05) e painel (F06). O visitante vê a vitrine (`/`) com os eventos publicados e o detalhe de cada um (`/eventos/<id>/`), com o slot `#compra` vazio (F03).

Fica fora: compra, lotação × vagas ocupadas (F03 estende `editar_evento`), cancelamento e bloqueio de edição de cancelado (F07).

## 2. Domínio

### 2.1 Modelo `dominio.Evento` (migration nova `dominio/0002_evento`)

| Campo | Tipo | Regra |
|---|---|---|
| `id_publico` | `CharField(12, unique)` | `evt_` + 8 caracteres de `[a-z0-9]`, gerado com `secrets`; é o id da URL e da API. Colisão na gravação → gera outro (até 5 tentativas). |
| `organizador` | `ForeignKey(Usuario, PROTECT, related_name="eventos")` | o usuário logado que criou |
| `nome` | `CharField(150)` | obrigatório |
| `inicio` | `DateTimeField` | com fuso (`USE_TZ`); no futuro ao criar e ao editar (R01) |
| `local` | `CharField(200)` | obrigatório |
| `lotacao` | `PositiveIntegerField` | 1 a 100000; `CheckConstraint lotacao >= 1` |
| `preco_centavos` | `PositiveIntegerField` | 1 a 100000000 (R$ 1.000.000,00); `CheckConstraint preco_centavos > 0` |
| `status` | `CharField(20)` com `TextChoices` | `rascunho` ("Rascunho"), `publicado` ("Publicado"), `cancelado` ("Cancelado"); padrão `rascunho`; `CheckConstraint` com os três valores |
| `criado_em` | `DateTimeField(default=timezone.now)` | |

Ordenação padrão: `inicio`, depois `id`. O valor `cancelado` já existe no modelo para a F07 não precisar de migration de choices; nenhuma ação da F02 o grava.

### 2.2 Exceções (em `dominio/excecoes.py`)

- `EventoNaoEncontrado(ErroDeDominio)`: o evento não existe ou é de outro organizador. As views traduzem para 404 com a página genérica.
- `EventoIndisponivel(ErroDeDominio)`: o evento não existe ou não está à venda (rascunho ou cancelado). As views da vitrine traduzem para 404.
- Erros de campo usam o `ValidacaoError` da F01 (`erros` = campo → mensagens).

### 2.3 Validação dos dados — `dominio/servicos/eventos.py`

`dados` é um dicionário com `nome`, `inicio`, `local`, `lotacao` e `preco`. Os valores podem chegar como texto (formulário) ou já tipados (`datetime`, `int`). Todos os erros são juntados e lançados num único `ValidacaoError`. Mensagens exatas:

| Campo | Situação | Mensagem |
|---|---|---|
| `nome` | vazio (depois de tirar espaços) | "Informe o nome do evento." |
| `nome` | mais de 150 caracteres | "O nome pode ter no máximo 150 caracteres." |
| `inicio` | vazio | "Informe a data e a hora de início." |
| `inicio` | texto fora dos formatos aceitos | "Informe a data e a hora no formato AAAA-MM-DD HH:MM." |
| `inicio` | não está no futuro (`<= agora`) | "A data de início precisa estar no futuro." |
| `local` | vazio | "Informe o local." |
| `local` | mais de 200 caracteres | "O local pode ter no máximo 200 caracteres." |
| `lotacao` | vazio | "Informe a lotação." |
| `lotacao` | não é inteiro, ou é menor que 1 | "A lotação precisa ser um número inteiro maior ou igual a 1." |
| `lotacao` | maior que 100000 | "A lotação pode ser no máximo 100000." |
| `preco` | vazio | "Informe o preço." |
| `preco` | texto fora do formato | "Informe o preço em reais, por exemplo 100,00." |
| `preco` | zero ou negativo | "O preço precisa ser maior que zero." |
| `preco` | maior que R$ 1.000.000,00 | "O preço pode ser no máximo R$ 1.000.000,00." |

- **Início.** Formatos aceitos: `AAAA-MM-DDTHH:MM` (o do `<input type="datetime-local">`), `AAAA-MM-DD HH:MM`, ambos com `:SS` opcional. Sem fuso no texto, vale `America/Sao_Paulo` (`TIME_ZONE`). Um `datetime` com fuso é usado como está.
- **Preço.** Texto sem espaços nas pontas que casa com `^-?\d+([.,]\d{1,2})?$`; vírgula ou ponto como separador decimal; "100", "100,00" e "100.00" viram `10000` centavos; "120,5" vira `12050`. Separador de milhar não é aceito. Um `int` é tratado como reais inteiros. Negativo casa com o formato e cai em "maior que zero".
- **Lotação.** Texto `^-?\d+$` (sem espaços nas pontas) ou `int`; "2.5", "abc" e "" não são inteiros.

### 2.4 Serviços — `dominio/servicos/eventos.py`

| Serviço | Comportamento |
|---|---|
| `criar_evento(organizador, dados) -> Evento` | Valida (2.3) e cria com `status=rascunho`, `organizador` = quem chamou e `id_publico` novo. |
| `editar_evento(organizador, evento_id, dados) -> Evento` | Numa transação: `select_for_update()` na linha do evento filtrada pelo dono (`EventoNaoEncontrado` se não existe ou é de outro); valida todos os campos (2.3, inclusive início no futuro); chama `_validar_edicao(evento, novos_valores, erros)`, ponto de extensão onde a F03 acrescenta a regra lotação × vagas ocupadas e a F07 o bloqueio de cancelado; grava. Vale em rascunho e em publicado. |
| `publicar_evento(organizador, evento_id) -> Evento` | Numa transação com a linha travada: `rascunho` → `publicado`; já `publicado` → devolve sem mudar nada. (Cancelado fica para a F07.) |
| `eventos_do_organizador(organizador) -> QuerySet[Evento]` | Só os do organizador, ordenados por início. |
| `evento_do_organizador(organizador, evento_id) -> Evento` | Busca por `id_publico` e dono; `EventoNaoEncontrado` se não existe ou é de outro. |
| `eventos_a_venda() -> QuerySet[Evento]` | `status=publicado`, ordenados por início. Rascunho e cancelado ficam fora. |
| `evento_a_venda(evento_id) -> Evento` | Publicado com esse `id_publico`; `EventoIndisponivel` caso contrário. |

`evento_id` é sempre o `id_publico` (string). Um `evento_id` que não tem o formato `evt_…` simplesmente não é encontrado.

## 3. Web

### 3.1 Formatação

`web/templatetags/catraca.py` com o filtro `reais` (`10000` → "R$ 100,00"; `123456` → "R$ 1.234,56"), usado pela vitrine, pela gestão e, depois, pelo painel (F06). Data e hora saem com `|date:"d/m/Y H:i"` no fuso `America/Sao_Paulo` (ex.: "15/06/2027 21:00").

### 3.2 Vitrine — `GET /` e `GET /eventos/<id>/`

- `/` (público): uma única `<section id="vitrine">` com o título "Eventos à venda" e uma lista `<ul>`; cada evento de `eventos_a_venda()` é um `<li class="evento">` com um link `<a href="/eventos/<id>/">` no nome, a data e hora, o local e o preço, cada dado uma vez. Sem eventos: "Nenhum evento à venda no momento.".
- `/eventos/<id>/` (público): `evento_a_venda(id)`; `EventoIndisponivel` → 404 genérico. Mostra nome, data e hora, local e preço em `<section id="evento-detalhe">` e o slot `<section id="compra"></section>` (parcial `web/vitrine/_compra.html`, vazio até a F03).

### 3.3 Área do organizador

Todas as views com `organizador_requerido` como decorador mais externo (o teste da F01 que percorre `/organizador/` passa a cobrir as rotas novas sem mudança). As rotas usam `path()` com `<str:evento_id>` (conversor que o teste da F01 já sabe preencher), e `organizador/eventos/novo/` é registrada **antes** de `organizador/eventos/<str:evento_id>/`, para não ser capturada por ela. A vitrine usa `eventos/<str:evento_id>/`.

| Rota | Métodos | Comportamento |
|---|---|---|
| `/organizador/` | GET | `<section id="meus-eventos">` com "Meus eventos", o link "Novo evento" (`href="/organizador/eventos/novo/"`) e uma tabela com nome (link para a gestão), início e status pelo rótulo ("Rascunho", "Publicado", "Cancelado"), só de `eventos_do_organizador`. Cada linha abre com `<tr class="evento" data-evento="<id>" data-status="<valor do status>">`, numa linha só do HTML. Sem eventos: "Você ainda não tem eventos.". |
| `/organizador/eventos/novo/` | GET, POST | Formulário `#form-evento` com `nome`, `inicio` (`type="datetime-local"`), `local`, `lotacao` (`type="number"`) e `preco` (texto). POST válido → `criar_evento` e 302 para a gestão do evento; inválido → 200 com o formulário, as mensagens da tabela 2.3 e os valores digitados. |
| `/organizador/eventos/<id>/` | GET | Página de gestão (3.4). Evento inexistente ou de outro organizador → 404 genérico. |
| `/organizador/eventos/<id>/editar/` | GET, POST | Formulário preenchido com os valores atuais (início em `AAAA-MM-DDTHH:MM` local, preço "100,00"); POST válido → `editar_evento` e 302 para a gestão; inválido → 200 com as mensagens. Outro organizador → 404. |
| `/organizador/eventos/<id>/publicar/` | POST | `publicar_evento` e 302 para a gestão. Ordem: guarda (visitante 302, participante 403), depois método (`GET` → 405 para qualquer organizador), depois o dono (outro organizador → 404). |

Mensagens de sucesso (framework `messages`, exibidas pelo `base.html`): "Evento criado.", "Evento atualizado.", "Evento publicado.".

### 3.4 Página de gestão — `/organizador/eventos/<id>/`

`web/templates/web/organizador/gestao.html`, com:

- `<section id="evento-dados">`: `<h2 data-campo="nome">` com o nome e uma lista `<dl>` com "Início", "Local", "Lotação", "Preço" e "Status", cada valor num `<dd data-campo="inicio|local|lotacao|preco|status">`, com o valor colado às tags (sem espaço nem quebra de linha): `data-campo="inicio">15/06/2027 21:00<`, `data-campo="preco">R$ 100,00<`, `data-campo="status">Publicado<`.
- `<section id="evento-acoes">`: link "Editar" (`href="/organizador/eventos/<id>/editar/"`) e, só em rascunho, o formulário `POST` para `/organizador/eventos/<id>/publicar/` com o botão "Publicar".
- Os slots, cada um num parcial próprio em `web/templates/web/organizador/gestao/`: `_cancelar.html` (`<section id="evento-cancelar">`), `_check_in.html` (`<section id="check-in">`) e `_painel.html` (`<section id="painel">`). Na F02 estão vazios. Cada parcial recebe `evento` (e o `request`) do contexto da gestão; F07, F05 e F06 preenchem cada um o seu parcial e buscam o que precisam com uma template tag própria (`web/templatetags/<assunto>.py`, que só chama o serviço do domínio), sem mexer na view nem no template de gestão. Assim as features da W4 em paralelo não editam o mesmo trecho.

### 3.5 Erros de outro organizador e de visitante

- Outro organizador: `EventoNaoEncontrado` → `Http404` → página 404 genérica (`404.html`), sem nome, local, lotação nem preço do evento. O POST não tem efeito.
- Visitante em qualquer rota da área: 302 para `/contas/entrar/?next=<caminho>` (GET) ou `/contas/entrar/` (POST), sem dados (guarda da F01).
- Participante em qualquer rota da área: 403 genérico (guarda da F01).

## 4. Testes

- `dominio/tests/test_eventos.py`: serviços (criação com os três formatos de preço, cada linha da tabela 2.3, início no passado ao criar e ao editar, edição, publicação idempotente, filtros por dono, vitrine só com publicados e na ordem do início, `evento_a_venda` com rascunho e inexistente, formato de `id_publico`).
- `web/tests/test_eventos.py`: telas com o client do Django (vitrine e detalhe, criar, editar, publicar, gestão com dados, ações e slots, lista só com os próprios, 404 sem dados para outro organizador, participante sem criar evento, visitante na gestão vai para o login).
- O teste da F01 `test_rotas_do_organizador_barram_visitante_e_participante` passa a percorrer também as rotas novas, sem mudança.

## 5. Como a F02 entrega XF-01 e prepara as seguintes

- **XF-01 [F01→F02]**: o organizador A da seed entra e cria um evento, que fica com `organizador` = A e só aparece na lista de A; o participante da seed recebe 403 em `GET /organizador/eventos/novo/` e o `POST` não cria evento; deslogado, a gestão de um evento de A redireciona para o login sem mostrar dados. Coberto no contrato.
- Para a F03: `Evento`, `evento_a_venda`, `editar_evento` com `_validar_edicao` e o slot `#compra`.
- Para a F04: `eventos_a_venda`, `Evento.id_publico`.
- Para F05, F06 e F07: `evento_do_organizador`, `Evento.status` e os parciais `#check-in`, `#painel` e `#evento-cancelar`.

## 6. Decisões menores

- A vitrine mostra todo evento publicado, mesmo que o início já tenha passado: o brief só pede "publicado e não cancelado" (R02) e as datas do fluxo têm folga.
- O preço sempre aparece com centavos ("R$ 100,00"), igual ao formato do painel.
- Limites de lotação (100000) e preço (R$ 1.000.000,00) só evitam estouro de inteiro; o brief não fixa máximo.
