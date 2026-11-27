# Catraca

Venda de ingressos para eventos pequenos (shows em bar, workshops, meetups): MVP do desafio "Catraca: do brief ao produto em modo agente" (MBA Full Cycle), construído por agentes a partir do [brief](docs/brief.md) e do [PRD](docs/prd.md).

## Como rodar

**Pré-requisitos:** Linux ou macOS (no Windows, WSL), Git e Docker com **Compose v2.20 ou mais novo** (confira com `docker compose version`). Nenhum Python, uv ou chave de pagamento no host: tudo roda em container, e o gateway de pagamento é simulado.

```bash
git clone <url>
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
| Pasta de cada feature (spec, plano, contrato, avaliações) | `docs/features/<ID>-<slug>/` — a preencher a partir da F01 |
| Estado do projeto | [estado.json](estado.json) |
| Porta de entrada dos agentes | [AGENTS.md](AGENTS.md) (o [CLAUDE.md](CLAUDE.md) aponta para ele) |
| PRs da wave paralela (W4: F04 ∥ F05) | a preencher na F04/F05 |

## Decisões

- **Stack e por quê.** Python 3.13 com uv (dependências fixadas em `pyproject.toml` e `uv.lock`), Django 5.2 LTS, PostgreSQL 17, telas renderizadas no servidor com templates Django, gunicorn (4 workers × 8 threads) e um worker do gateway em container próprio. Django dá autenticação, sessões, CSRF, formulários e migrations prontos, o que deixa o esforço nas regras do brief; Postgres dá travas de linha (`SELECT … FOR UPDATE`) e atualizações condicionais, que são a base das garantias de lotação e de cancelamento. Tudo sobe com Docker Compose, porque a máquina do avaliador só tem Docker, Git e Node. O código é dividido em camadas: `dominio` (regras), `web` (telas) e `api_parceiros` (JSON); web e API só chamam serviços do domínio.
- **Como R07 foi garantida sob concorrência.** A preencher na F03 (prova com rajada pela API na F04).
- **Como a resposta assíncrona do gateway foi implementada.** A preencher na F03 (corrida com o cancelamento na F07).
- **Como a avaliação foi isolada do implementador.** Cada feature é avaliada por uma sessão nova, de contexto vazio, que não participou da implementação. Antes de começar, essa sessão confere que `git rev-parse HEAD` é o sha pedido e que a árvore está limpa; depois exercita só os itens do contrato e escreve apenas o relatório, sem tocar em código, contrato ou `estado.json`. Quem commita o relatório, sem alterá-lo, é a sessão de implementação, no mesmo commit que atualiza o `estado.json`.
