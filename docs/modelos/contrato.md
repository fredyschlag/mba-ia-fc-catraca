# Contrato — <ID> <Nome da feature>

> Modelo: copie para `docs/features/<ID>-<slug>/contrato.md` e preencha. O contrato é o acordo entre quem implementa e quem avalia: o avaliador exercita **só** o que está aqui, item por item. Cada item precisa ser verificável por comando ou efeito observável, com resultado esperado sem ambiguidade (textos exatos entre aspas, status HTTP, contagens).

- Feature: <ID> — <Nome> (wave <Wn>)
- PRD: [docs/prd.md](../../prd.md), seções 3.2 (Provides/Consumes), 6 (critérios da feature) e 7 (critérios cross)
- Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

## 1. Pré-requisitos de ambiente

- Commit avaliado: o sha informado no pedido de avaliação (branch `<branch>` ou `main`).
- `./scripts/down.sh` e depois `./scripts/up.sh` terminam com código 0; `$WEB` = `http://localhost:<porta>`.
- Contas da seed (README, seção "Credenciais"): organizador A, organizador B, participante.
- Chave de parceiro: `$KEY` do README (quando a feature usa a API).
- Dados preparados: <eventos, ingressos ou estados necessários e como criá-los>.
- Ferramentas no host: Docker, Git e `curl`. Navegador é opcional.

## 2. Itens verificáveis

Numerados C-01, C-02, … Cada item diz como verificar e o resultado esperado. Um item pode ser um teste automatizado (comando pytest com o nome do teste) ou um passo HTTP com `curl`.

**Itens de interface** (telas, formulários, mensagens) são verificáveis de uma destas duas formas, sem depender de navegador:

- **`curl` com cookie de sessão e CSRF**, com login feito pelo próprio formulário de login: um `GET` na página do formulário guarda os cookies (`-c`) e o `csrftoken`; o `POST` reenvia os cookies (`-b`) e manda o token no campo `csrfmiddlewaretoken`. As requisições seguintes usam o mesmo arquivo de cookies. Exemplo (rotas e campos são os da spec da feature):

  ```bash
  JAR=$(mktemp)
  curl -s -c "$JAR" "$WEB/<rota do login>" >/dev/null
  CSRF=$(awk '$6 == "csrftoken" {print $7}' "$JAR")
  curl -s -b "$JAR" -c "$JAR" -o /dev/null -w '%{http_code}\n' \
    --data-urlencode "csrfmiddlewaretoken=$CSRF" \
    --data-urlencode "<campo e-mail>=org.a@catraca.test" \
    --data-urlencode "<campo senha>=catraca123" \
    "$WEB/<rota do login>"
  curl -s -b "$JAR" "$WEB/<página>" | grep -F "<texto esperado>"
  ```

- **Teste com o client do Django**, citando o nome do teste no item: `./scripts/gates.sh -k <nome_do_teste>` (ou o caminho completo `arquivo.py::nome_do_teste`), com resultado esperado `1 passed`.

Screenshot é opcional: pode complementar a evidência, mas nenhum item depende dele. **Os textos esperados vão entre aspas, exatos** (ex.: "Ingressos esgotados"), como aparecem no HTML ou no JSON, para serem conferidos com `grep -F`.

| Item | Como verificar (comando ou passo) | Resultado esperado |
|---|---|---|
| C-01 | `./scripts/gates.sh` | Código de saída 0; todas as etapas OK. |
| C-02 | `<comando ou passo>` | `<resultado exato>` |
| C-03 | … | … |

## 3. Mapeamento critério do PRD → itens

Todo critério `<ID>-CAyy` da feature e todo `XF-zz` atribuído a esta feature aparece aqui com pelo menos um item.

| Critério do PRD | Itens |
|---|---|
| <ID>-CA01 | C-02 |
| <ID>-CA02 | C-03, C-04 |
| XF-zz [Fx→Fy] | C-0n |

## 4. Fora deste contrato

- <O que não é verificado aqui e por quê (coberto por outra feature, fora de escopo etc.)>
