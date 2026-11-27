# AGENTS.md — porta de entrada dos agentes

Catraca: venda de ingressos para eventos pequenos (MVP do desafio Full Cycle). Este arquivo diz como subir o projeto, quais regras seguir, como cada feature anda e onde está cada artefato. Leia inteiro antes de começar. CLAUDE.md só aponta para cá.

## Comandos

Só Docker é necessário no host. Nada de Python ou uv fora de container.

| O quê | Comando |
|---|---|
| Subir tudo (db, migrate + seed, web, gateway) e esperar ficar saudável | `./scripts/up.sh` |
| Derrubar tudo que a subida e os gates iniciaram (mantém o volume do banco) | `./scripts/down.sh` |
| Rodar os gates: ruff check, ruff format --check, `manage.py check`, `makemigrations --check --dry-run`, pytest | `./scripts/gates.sh` (argumentos extras vão para o pytest, ex.: `./scripts/gates.sh -k seed`) |
| Rodar um comando no container de desenvolvimento, com arquivos criados com o seu usuário | `./scripts/dev.sh <comando>` (ex.: `./scripts/dev.sh python manage.py makemigrations dominio`, `./scripts/dev.sh ruff format .`) |
| Gerar ou atualizar o `uv.lock` | `./scripts/lock.sh` |
| Ver logs | `docker compose logs -f web gateway` |
| Começar do zero (apaga o banco deste projeto) | `docker compose --profile '*' down -v` e depois `./scripts/up.sh` |

**Worktree em outra porta.** O nome do projeto Compose vem da pasta, então cada worktree já tem containers, rede e volume próprios. Só a porta precisa mudar:

```bash
CATRACA_PORTA=8001 ./scripts/up.sh
CATRACA_PORTA=8001 ./scripts/down.sh
```

Duas cópias na mesma pasta exigem também `COMPOSE_PROJECT_NAME=<outro-nome>` nos dois comandos.

## Endereços

- `$WEB` = `http://localhost:8000` (ou a porta de `CATRACA_PORTA`)
- `$API` = `http://localhost:8000`; as rotas ficam em `/api/partner/...`
- Healthcheck: `GET /saude/` → 200 `{"status": "ok"}`
- Credenciais de desenvolvimento e chave de parceiro: [README.md](README.md#credenciais)

## Regras do projeto

1. **Regra de negócio só no domínio.** Modelos e serviços com as regras R01–R13 ficam em `dominio/` (`dominio/servicos/<assunto>.py`). `web/` e `api_parceiros/` só chamam serviços do domínio e traduzem exceções em resposta. Nada de regra em view ou template.
2. **Gates verdes antes de dizer "pronto".** `./scripts/gates.sh` precisa sair com código 0. Mostre a saída.
3. **Nunca leia, peça ou exiba `.env` nem segredos.** O projeto não usa `.env`: os valores de desenvolvimento ficam no `compose.yaml`.
4. **Gateway sempre simulado.** Nenhuma chave de pagamento real, em lugar nenhum. O atraso só muda em testes, via `GATEWAY_FATOR_ATRASO`, que nunca aparece no `compose.yaml`.
5. **Commit só com autorização do Fredy**, sem linha `Co-Authored-By`. Push também só com autorização; o PR é aberto pelo Fredy.
6. **Relatório de avaliação nunca é editado depois de commitado.** Reavaliação gera arquivo novo.
7. **O brief é a referência.** [docs/brief.md](docs/brief.md) não é editado; o [PRD](docs/prd.md) fixa features, Provides/Consumes, critérios e waves. Mudar um nome provido exige atualizar o PRD e os contratos afetados.
8. **O modelo de usuário e a seed são da W0.** Não troque o `AUTH_USER_MODEL` nem reescreva a migration `dominio/0001`; mudanças no usuário entram em migrations novas.
9. **Versões fixadas.** Dependência nova entra no `pyproject.toml` com versão exata, seguida de `./scripts/lock.sh`.

## Fluxo de cada feature (sessão de implementação)

Toda feature é feita na branch `feat/<ID>-<slug>` (ex.: `feat/F01-contas-acesso`) e entra na main por PR, aberto pelo Fredy. Uma feature só começa quando todas as provedoras dela (PRD, seções 3 e 4) estão `concluida` no `estado.json` e já estão na main.

1. Conferir no `estado.json` da main que as provedoras estão `concluida`; criar a branch `feat/<ID>-<slug>` a partir da main.
2. Ler AGENTS.md, [docs/brief.md](docs/brief.md) e a feature no [PRD](docs/prd.md) (seções 3, 6, 7 e 8).
3. Escrever `docs/features/<ID>-<slug>/spec.md` (decisões técnicas), `plano.md` (etapas) e `contrato.md` (segue [docs/modelos/contrato.md](docs/modelos/contrato.md)); no `estado.json`, status `em_andamento` e a branch.
4. **PARAR** para revisão do Fredy e da sessão de orientação.
5. Implementar seguindo o plano, com testes.
6. Rodar `./scripts/gates.sh` até ficar verde e conferir os itens do contrato que dependem do ambiente no ar (`./scripts/up.sh`).
7. Atualizar `estado.json` (status `em_avaliacao`) e **PARAR**, mostrando o resumo e a mensagem de commit proposta.
8. Depois da avaliação: commitar o relatório **sem alterá-lo**, no mesmo commit que atualiza o `estado.json` (status `reprovada` ou `concluida` e caminho do relatório). Se reprovada, corrigir e voltar ao passo 6; a reavaliação gera um relatório novo.

**Wave paralela (W4: F04 ∥ F05).** Cada feature fica na sua worktree, com a sua branch e a sua porta (`CATRACA_PORTA`, ver "Worktree em outra porta"), e entra na main pelo seu próprio PR.

## Fluxo de avaliação (sessão de avaliação)

- Sessão nova, de contexto vazio: quem implementou não avalia.
- Lê o contrato da feature e exercita cada item no commit indicado, com o ambiente subido por `./scripts/up.sh`.
- Só escreve o arquivo do relatório, novo, em `docs/features/<ID>-<slug>/avaliacoes/<AAAA-MM-DDTHHMM>-<sha7>.md`, seguindo [docs/modelos/relatorio-avaliacao.md](docs/modelos/relatorio-avaliacao.md). Não commita, não toca no `estado.json`, não corrige código, não edita contrato nem relatórios anteriores.
- Quem commita o relatório é a sessão de implementação da feature (passo 8 acima).
- Item reprovado volta para a sessão de implementação; depois da correção, uma nova avaliação gera um novo relatório.

## estado.json

Memória do projeto entre sessões. Precisa bater com a realidade.

- `status`: `pendente` → `em_andamento` (começou a spec) → `em_avaliacao` (gates verdes, aguardando avaliador) → `reprovada` (relatório mais recente reprova algum item) ou `concluida` (relatório mais recente aprova tudo). Como o commit do relatório vai na branch da feature, `concluida` só chega à main junto com o merge do PR.
- `relatorio`: caminho do relatório mais recente; atualizado no mesmo commit que adiciona o relatório.
- `branch` e `pr`: preenchidos quando existirem.
- Quem atualiza: só a sessão de implementação da feature, ao começar, ao pedir avaliação e ao commitar o relatório. A sessão de avaliação nunca toca no `estado.json`.

## Mapa dos artefatos

| Artefato | Onde |
|---|---|
| Brief (regras R01–R13) | [docs/brief.md](docs/brief.md) |
| PRD (features, grafo, waves, critérios, matrizes) | [docs/prd.md](docs/prd.md) |
| Critérios de harness da W0 (H-01…H-08) | [docs/prd.md](docs/prd.md), seção 6.0 |
| Modelos de contrato e relatório | [docs/modelos/](docs/modelos/) |
| Spec, plano, contrato e avaliações de cada feature | `docs/features/<ID>-<slug>/` (`F01-contas-acesso`, `F02-eventos-vitrine`, `F03-compra-lotacao-gateway`, `F04-api-parceiros`, `F05-check-in`, `F06-painel`, `F07-cancelamento`) |
| Estado do projeto | [estado.json](estado.json) |
| Código: domínio, telas, API | `dominio/`, `web/`, `api_parceiros/`; configuração em `catraca/` |
| Ambiente | `compose.yaml`, `Dockerfile`, `scripts/` |
| Instruções para humanos | [README.md](README.md) |
