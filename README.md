# Catraca

Venda de ingressos para eventos pequenos (shows em bar, workshops, meetups): MVP do desafio "Catraca: do brief ao produto em modo agente" (MBA Full Cycle), construído por agentes a partir do [brief](docs/brief.md) e do [PRD](docs/prd.md).

## Como rodar

**Pré-requisitos:** Linux ou macOS (no Windows, WSL), Git e Docker com **Compose v2.20 ou mais novo** (confira com `docker compose version`). Nenhum Python, uv ou chave de pagamento no host: tudo roda em container, e o gateway de pagamento é simulado.

```bash
git clone https://github.com/fredyschlag/mba-ia-fc-catraca.git
cd mba-ia-fc-catraca
./scripts/up.sh
```

| O quê | Comando |
|---|---|
| Subir (banco, migrations, seed, web, worker do gateway) | `./scripts/up.sh` |
| Derrubar tudo que a subida e os gates iniciaram (o banco é mantido) | `./scripts/down.sh` |
| Rodar os gates (lint, checagens do Django, migrations pendentes, testes) | `./scripts/gates.sh` |

A subida termina quando o produto está saudável e imprime os endereços. Para outra porta (ex.: duas worktrees ao mesmo tempo): `CATRACA_PORTA=8001 ./scripts/up.sh` e `CATRACA_PORTA=8001 ./scripts/down.sh`. Para começar com o banco vazio: `docker compose --profile '*' down -v` e depois `./scripts/up.sh`.

## Endereços

| Variável do Fluxo do avaliador | Endereço |
|---|---|
| `$WEB` (produto) | `http://localhost:8000` |
| `$API` (API de parceiros) | `http://localhost:8000` (rotas em `/api/partner/...`) |

## Credenciais

> **Valores de desenvolvimento**, criados pela seed a cada subida e válidos só no ambiente local. Não são segredos e não servem para nada além deste projeto.

| Conta | E-mail | Senha |
|---|---|---|
| Organizador A | `org.a@catraca.test` | `catraca123` |
| Organizador B | `org.b@catraca.test` | `catraca123` |
| Participante da seed | `participante@catraca.test` | `catraca123` |

| Chave de parceiro (`$KEY`, cabeçalho `X-Api-Key`) |
|---|
| `chave-parceiro-dev` |

## Mapa dos artefatos

| Artefato | Onde |
|---|---|
| Brief (regras R01–R13) | [docs/brief.md](docs/brief.md) |
| PRD (features, Provides/Consumes, grafo, waves, critérios, matrizes) | [docs/prd.md](docs/prd.md) |
| Critérios de harness da W0 (H-01…H-08) | [docs/prd.md](docs/prd.md), seção 6.0 |
| Modelos de contrato e de relatório de avaliação | [docs/modelos/](docs/modelos/) |
| Pasta de cada feature (spec, plano, contrato, avaliações) | `docs/features/<ID>-<slug>/`: [F01](docs/features/F01-contas-acesso/), [F02](docs/features/F02-eventos-vitrine/), [F03](docs/features/F03-compra-lotacao-gateway/), [F04](docs/features/F04-api-parceiros/), [F05](docs/features/F05-check-in/), [F06](docs/features/F06-painel/), [F07](docs/features/F07-cancelamento/); relatórios em `avaliacoes/` de cada uma |
| Estado do projeto | [estado.json](estado.json) |
| Porta de entrada dos agentes | [AGENTS.md](AGENTS.md) (o [CLAUDE.md](CLAUDE.md) aponta para ele) |
| PRs da wave paralela (W4: F04 ∥ F05) | [F05: Check-in (#5)](https://github.com/fredyschlag/mba-ia-fc-catraca/pull/5) e [F04: API de parceiros (#6)](https://github.com/fredyschlag/mba-ia-fc-catraca/pull/6); como se intercalaram, ver "Paralelismo da W4" abaixo |

## Paralelismo da W4

F04 e F05 foram implementadas ao mesmo tempo, cada uma por um subagente na sua worktree (`../catraca-F04`, porta 8001, branch `feat/F04-api-parceiros`; `../catraca-F05`, porta 8002, branch `feat/F05-check-in`), com commit e push a cada etapa. Horários dos commits de cada PR (America/Sao_Paulo, 2026-11-27, `gh pr view <n> --json commits`):

| PR | Primeiro commit | Último commit |
|---|---|---|
| [#5 F05 Check-in](https://github.com/fredyschlag/mba-ia-fc-catraca/pull/5) | `1ed58e9` 14:39:39 | `7b810bc` 18:11:58 |
| [#6 F04 API de parceiros](https://github.com/fredyschlag/mba-ia-fc-catraca/pull/6) | `f9b7751` 14:39:43 | `a7f19fa` 18:24:03 |

O primeiro commit de cada PR é anterior ao último commit do outro, e as etapas de implementação se intercalaram entre 14:46 e 14:55 (F05: 14:47:59, 14:49:19, 14:50:55, 14:52:51; F04: 14:48:14, 14:49:07, 14:50:33, 14:51:21, 14:53:08, 14:55:31). O #5 entrou primeiro; o #6 recebeu a main na própria branch e resolveu o único conflito, no `estado.json` (linhas vizinhas da F04 e da F05), sem mudar código; depois do merge os gates e o contrato da F04 rodaram de novo e a reavaliação foi feita sobre o código integrado.

## Decisões

- **Stack e por quê.** Python 3.13 com uv (dependências fixadas em `pyproject.toml` e `uv.lock`), Django 5.2 LTS, PostgreSQL 17, telas renderizadas no servidor com templates Django, gunicorn (4 workers × 8 threads) e um worker do gateway em container próprio. Django dá autenticação, sessões, CSRF, formulários e migrations prontos, o que deixa o esforço nas regras do brief; Postgres dá travas de linha (`SELECT … FOR UPDATE`) e atualizações condicionais, que são a base das garantias de lotação e de cancelamento. Tudo sobe com Docker Compose, porque a máquina do avaliador só tem Docker, Git e Node. O código é dividido em camadas: `dominio` (regras), `web` (telas) e `api_parceiros` (JSON); web e API só chamam serviços do domínio.
- **Como R07 foi garantida sob concorrência.** A compra (`dominio/servicos/compras.py::comprar_ingresso`, usada pela vitrine e pela API) roda numa transação que primeiro trava a linha do evento com `SELECT … FOR UPDATE`; só com a trava ela confere se o evento está à venda, conta as vagas ocupadas (pendentes + confirmados) e cria o ingresso. Duas compras do mesmo evento esperam uma pela outra, e em READ COMMITTED a contagem feita depois da trava já enxerga o ingresso da transação anterior, então ninguém conta a mesma vaga livre duas vezes. A edição de lotação usa a mesma trava (lotação nunca abaixo das ocupadas). O servidor atende de verdade em paralelo (gunicorn com 4 workers × 8 threads, Postgres com `max_connections=200`). A prova tem duas camadas: um teste pytest contra o Postgres do Compose com 30 threads liberadas juntas por uma barreira, num evento de lotação 5, repetido em 10 eventos (sempre 5 ingressos e 25 esgotados), e a rajada de 30 `curl` em paralelo do contrato da F03 (e da API na F04), que dá sempre 5 compras aceitas e 25 recusadas.
- **Como a resposta assíncrona do gateway foi implementada.** A compra responde na hora com o ingresso `pending` e grava uma `CobrancaGateway` com o resultado sorteado pelo final do cartão e o momento em que a resposta "chega" (2–4 s para os rápidos e 32–38 s para os lentos, dentro das faixas do brief e com folga para o "em até 5 s" e para o "ainda pendente aos 30 s"). Um worker em container próprio (`python manage.py gateway_worker`, serviço `gateway`) processa a cada 0,5 s as cobranças vencidas e aplica a resposta com um único `UPDATE … SET status = … WHERE id = … AND status = 'pending'`: a resposta só muda ingresso pendente, então uma resposta que chega depois do cancelamento do evento não muda nada (R11). As cobranças ficam no banco, então derrubar e subir o ambiente não perde nenhuma. O cartão nunca é gravado inteiro (só os 4 últimos dígitos). O atraso pode ser encurtado só nos testes, pela variável `GATEWAY_FATOR_ATRASO`, que não existe no `compose.yaml`.
- **Como o cancelamento convive com a resposta tardia do gateway (R11).** `cancelar_evento` (`dominio/servicos/cancelamento.py`) é síncrono: na mesma transação que trava a linha do evento (a mesma trava da compra, da edição e do check-in), grava o evento como cancelado e passa os ingressos num único `UPDATE … SET status = CASE WHEN status = 'confirmed' THEN 'refunded' ELSE 'cancelled' END WHERE status IN ('pending', 'confirmed')`. A resposta do gateway é outro `UPDATE … WHERE status = 'pending'`. Em READ COMMITTED, o Postgres serializa os dois pela trava da linha do ingresso e reavalia o `WHERE` sobre a versão gravada: se a aprovação chega antes, o cancelamento estorna; se o cancelamento chega antes, a resposta não encontra mais o pendente e não muda nada. Um único comando evita a janela que haveria entre estornar os confirmados e cancelar os pendentes. Prova: teste com 50 corridas soltas e dois testes que seguram cada uma das operações com a transação aberta (`dominio/tests/test_cancelamento_concorrencia.py`), e o contrato da F07 com um cartão lento real cancelado antes de 30 s e conferido depois de 45 s. Evento cancelado não aparece na vitrine nem na API, não vende (a compra encontra o evento cancelado com a trava), não edita nem republica (409), e o check-in responde "Evento cancelado".
- **Como a receita do painel usa o preço de cada compra (R12, R03).** A compra grava o preço vigente no ingresso (`valor_centavos`); mudar o preço do evento só afeta compras seguintes. O painel (`painel_do_evento`) soma `valor_centavos` só dos ingressos `confirmed`, numa consulta agregada; estornados, pendentes, recusados e cancelados não entram na receita, e Check-ins conta só confirmados com check-in. Vendas da vitrine e da API são o mesmo `Ingresso` e contam igual.
- **Como a avaliação foi isolada do implementador.** Quem implementou nunca avaliou. A F01 foi avaliada por uma sessão nova, de contexto vazio. Da F02 à F07, a avaliação ficou com um subagente novo, também de contexto vazio, que a sessão de implementação lançou passando só o sha, a pasta, a porta e o contrato. Antes de começar, o avaliador confere que `git rev-parse HEAD` é o sha pedido e que a árvore está limpa. Depois exercita só os itens do contrato e escreve apenas o relatório, sem tocar em código, contrato ou `estado.json`. Quem commita o relatório, sem alterá-lo, é a sessão de implementação, no mesmo commit que atualiza o `estado.json`. Uma reprovação gera um relatório novo, de outro avaliador novo, e nunca a edição do anterior. Foi o que aconteceu com a F04: reprovada com 12/13 e aprovada com 13/13 depois da correção.
