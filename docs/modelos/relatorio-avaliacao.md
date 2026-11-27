# Relatório de avaliação — <ID> <Nome da feature>

> Modelo: salve como `docs/features/<ID>-<slug>/avaliacoes/<AAAA-MM-DDTHHMM>-<sha7>.md`. Um arquivo por avaliação. **Depois de commitado, este arquivo nunca é editado**: reavaliação gera um relatório novo.

| Campo | Valor |
|---|---|
| Data e hora | <AAAA-MM-DD HH:MM (America/Sao_Paulo)> |
| Commit avaliado | <sha completo, 40 caracteres> |
| Branch | <branch ou main> |
| Ferramenta | <ex.: Claude Code (desktop), versão> |
| Modelo | <ex.: claude-opus-5-5> |
| Ambiente | <SO, versão do Docker e do Compose, porta usada, `./scripts/up.sh` OK> |
| Contrato | [contrato.md](../contrato.md) no commit avaliado |
| Isolamento | <sessão nova de contexto vazio, distinta da sessão de implementação> |

## Vereditos por item

Um item por linha, na ordem do contrato. Veredito: **APROVADO** ou **REPROVADO**. Evidência: saída de comando, resposta HTTP (status e corpo) ou screenshot (caminho do arquivo), suficiente para outra pessoa conferir.

| Item | Veredito | Evidência |
|---|---|---|
| C-01 | APROVADO | `./scripts/gates.sh` → código 0; `10 passed in 3.2s` |
| C-02 | REPROVADO | `curl -s -w '%{http_code}' …` → `500` (esperado `404`); corpo: `…` |

## Observações

- <Desvios, itens que dependem de outra feature, riscos percebidos. Sem correções de código.>

## Veredito final

**<APROVADO | REPROVADO>** — <n> de <total> itens aprovados. <Se reprovado: itens que voltam para correção.>
