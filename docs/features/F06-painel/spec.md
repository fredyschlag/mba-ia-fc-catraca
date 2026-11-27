# Spec — F06 Painel (W5)

- PRD: [docs/prd.md](../../prd.md), seções 3.2 (F06), 6 (F06-CA01…CA05) e 7 (XF-09, XF-10, XF-11, XF-12, XF-13, atribuídos a esta feature).
- Regras: R12, R04, R05, R13 (e R03 pela receita com o preço gravado).
- Consome: F02 (página de gestão e o parcial `#painel`, `evento_do_organizador`, lotação editável), F03 (`Ingresso.status`, `valor_centavos`, `vagas_disponiveis`), F04 (ingressos `canal=api` criados pela API, que entram nos números como os da vitrine), F05 (`check_in_em` preenchido por `fazer_check_in`).
- Plano: [plano.md](plano.md) · Contrato: [contrato.md](contrato.md).

## 1. Escopo

A página de gestão de cada evento mostra o painel com os seis números de R12, contando as vendas da vitrine e da API. Fica fora: cancelamento e estornos de fato (F07); aqui "Estornados" só conta ingressos `refunded`, que nesta wave só existem preparados em teste.

## 2. Domínio — `dominio/servicos/painel.py`

`Painel` é um `dataclass(frozen=True)` com `confirmados`, `pendentes`, `check_ins`, `vagas_disponiveis`, `receita_centavos` e `estornados` (inteiros).

`painel_do_evento(evento) -> Painel` faz **exatamente duas consultas**: uma agregada sobre os ingressos do evento (`aggregate` com `Count(..., filter=Q(...))` e `Sum("valor_centavos", filter=Q(status="confirmed"))`) para cinco números, e a de `compras.vagas_disponiveis(evento)` (a mesma regra R05 da compra, sem duplicá-la). Como são duas leituras, uma compra feita entre elas pode aparecer só nas vagas; recarregar a página mostra o estado atual. Calcula:

| Número | Definição (R12) |
|---|---|
| `confirmados` | ingressos `confirmed`, com ou sem check-in |
| `pendentes` | ingressos `pending` |
| `check_ins` | ingressos `confirmed` com `check_in_em` preenchido |
| `vagas_disponiveis` | `dominio.servicos.compras.vagas_disponiveis(evento)` (R05: lotação − pendentes − confirmados; 0 em cancelado) |
| `receita_centavos` | soma de `valor_centavos` dos `confirmed` (preço gravado em cada compra, R03); 0 se não há confirmados |
| `estornados` | ingressos `refunded` |

`declined` e `cancelled` não entram em nenhum número. Canal (vitrine ou API) não muda nada. Nada é guardado em cache: cada chamada lê o banco.

## 3. Web

- Template tag `web/templatetags/painel.py` com a inclusion tag `bloco_painel evento`, que devolve `{"painel": painel_do_evento(evento)}` e renderiza `web/organizador/gestao/_painel_conteudo.html`; cada `<dd data-metrica="…">` mostra só `{{ painel.<campo> }}` (a receita com `|reais`). O parcial `_painel.html` (F02) passa a ser `{% load painel %}<section id="painel">{% bloco_painel evento %}</section>`. A view e o template de gestão não mudam.
- Conteúdo: título "Painel" e uma lista `<dl>` com seis pares, cada um numa linha só do HTML: `<dt>Confirmados</dt><dd data-metrica="confirmados">3</dd>`, e assim por diante com os rótulos "Confirmados", "Pendentes", "Check-ins", "Vagas disponíveis", "Receita" e "Estornados" e os `data-metrica` `confirmados`, `pendentes`, `check-ins`, `vagas-disponiveis`, `receita` e `estornados`. A receita sai com o filtro `reais` ("R$ 350,00"); os outros, como inteiros.
- O template não calcula nada: só mostra os campos de `Painel` (F06-CA04).
- Outro organizador: a gestão já responde 404 com a página genérica (F02), então o bloco nunca é renderizado para ele (F06-CA05).

## 4. Testes

- `dominio/tests/test_painel.py`: fixture com ingressos nos cinco status (vitrine e API), confirmados com e sem check-in; definições de cada número; receita com preços diferentes (dois a 10000 e um a 15000 → 35000) mesmo com o preço atual do evento mudado; pendentes, recusados, cancelados e estornados fora da receita; evento cancelado com vagas 0; uma única consulta para os agregados.
- `web/tests/test_painel.py`: bloco na gestão com os seis rótulos e `data-metrica`; formato "R$ 350,00" e "R$ 0,00"; recarregar mostra o estado atual; outro organizador recebe 404 sem `id="painel"`.

## 5. Critérios cross desta feature

- **XF-09 [F02→F06]**: "Vagas disponíveis" acompanha a lotação editada na gestão (2 → 3 com 2 ocupadas: 0 → 1).
- **XF-10 [F03→F06]**: duas compras a R$ 100,00, preço para R$ 150,00 e lotação 3, mais uma compra, todas confirmadas → Confirmados 3, Pendentes 0, Vagas 0, Receita "R$ 350,00"; uma compra 0004 aparece em Pendentes enquanto pendente e sai de lá sem entrar em nenhum outro número quando é recusada.
- **XF-11 [F04→F06]**: rajada de 30 pela API num evento de lotação 5 → Confirmados 5 e Vagas 0 em até 10 s; compra pela API com final 0003 aparece em Pendentes.
- **XF-12 [F05→F06]**: check-in de um confirmado sobe Check-ins em 1 sem mudar Confirmados nem Receita; check-ins rejeitados não mudam nenhum número.
- **XF-13 [F04+F05→F06]**: ingresso da API com 0001 confirmado faz check-in com o `code` da resposta 202 → "Entrada liberada"; a API passa a mostrar `checkedIn: true` e `status: "confirmed"`; o painel o conta em Confirmados e Check-ins e soma o valor na Receita; o `code` de um ingresso da API de outro evento → "Ingresso inválido para este evento".
