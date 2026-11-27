# Spec — F07 Cancelamento (W6)

- PRD: [docs/prd.md](../../prd.md), seções 3.2 (F07), 6 (F07-CA01…CA08) e 7 (XF-14…XF-19, atribuídos a esta feature).
- Regras: R11, R02, R05, R13 (e R08, R10, R12 nas combinações).
- Consome: F02 (`Evento.status`, `editar_evento`/`_validar_edicao`, `publicar_evento`, vitrine, página de gestão e o parcial `#evento-cancelar`), F03 (`Ingresso`, `aplicar_resposta_gateway` condicional, `vagas_disponiveis`, a trava da linha do evento), F04 (listagem, compra e consulta da API), F05 (caminho "Evento cancelado" de `fazer_check_in`), F06 (`painel_do_evento`).
- Plano: [plano.md](plano.md) · Contrato: [contrato.md](contrato.md).

## 1. Escopo

O organizador cancela um evento publicado pela página de gestão. O cancelamento é síncrono e irreversível: na mesma transação que trava o evento, o evento passa a `cancelado`, os ingressos `confirmed` passam a `refunded` e os `pending` a `cancelled`; o evento sai da vitrine e da API, não vende, não edita e não republica. Uma resposta do gateway que chegue depois não muda nada (o `UPDATE … WHERE status='pending'` da F03 não encontra mais o ingresso pendente).

## 2. Domínio

### 2.1 Exceções (em `dominio/excecoes.py`)

- `EventoCancelado(ErroDeDominio)`, mensagem "Evento cancelado não pode ser alterado." (nome e texto do PRD 3.2).
- `CancelamentoNaoPermitido(ErroDeDominio)`, mensagem "Só evento publicado pode ser cancelado." (evento em rascunho).

### 2.2 `dominio/servicos/cancelamento.py`

`cancelar_evento(organizador, evento_id) -> Evento`, numa transação:

1. trava a linha do evento do dono (`select_for_update`, a mesma trava da compra, da edição e do check-in; outro organizador ou inexistente → `EventoNaoEncontrado`);
2. já `cancelado` → devolve sem mudar nada (idempotente); `rascunho` → `CancelamentoNaoPermitido`;
3. grava `status = cancelado`;
4. um único `UPDATE` nos ingressos do evento com `status IN ('pending', 'confirmed')`: `status = CASE WHEN status = 'confirmed' THEN 'refunded' ELSE 'cancelled' END` (`Ingresso.objects.filter(...).update(status=Case(When(...), default=...))`). `declined`, `cancelled` e `refunded` não mudam; `check_in_em` não muda (um confirmado com check-in vira `refunded` e continua com `checkedIn: true`).

**Corrida com o gateway (R11).** O `UPDATE` do cancelamento e o `UPDATE … WHERE status = 'pending'` de `aplicar_resposta_gateway` disputam a mesma linha do ingresso; o Postgres serializa os dois pela trava da linha e reavalia o `WHERE` com a versão já gravada:

- se a aprovação grava primeiro, o ingresso está `confirmed` quando o cancelamento o lê (ou o relê depois de esperar a trava) e o `CASE` o passa a `refunded`;
- se o cancelamento grava primeiro, a resposta encontra `cancelled` e não muda nada (devolve `False`).

- se a recusa grava primeiro, o ingresso sai do `IN ('pending', 'confirmed')` e continua `declined`.

Em nenhum caso o ingresso termina `confirmed` ou `pending` num evento cancelado. A análise vale para READ COMMITTED, o nível padrão do Django e do Postgres (o `settings` não define `isolation_level`): é nele que o `UPDATE` que esperou a trava reavalia o `WHERE` sobre a versão gravada; em REPEATABLE READ ou SERIALIZABLE ele falharia com erro de serialização. Fazer tudo num único `UPDATE` evita a janela que existiria com dois comandos (confirmados primeiro, pendentes depois). Compras novas não entram durante o cancelamento porque a compra trava a mesma linha do evento e, depois, encontra o evento `cancelado` (`EventoIndisponivel`).

### 2.3 Bloqueios e regras de estado do evento

- `editar_evento`: `_validar_edicao` (ponto de extensão da F02) lança `EventoCancelado` quando o evento está cancelado, antes de qualquer erro de campo. Nada é gravado.
- `publicar_evento`: em evento cancelado lança `EventoCancelado` (antes devolvia o evento sem mudar).
- `garantir_editavel(organizador, evento_id) -> Evento`: o evento do dono, ou `EventoCancelado` se cancelado (usado pelo `GET` do formulário de edição).
- Propriedades de `Evento` (regra de estado no domínio, lida pelos templates): `pode_ser_editado` (não cancelado), `pode_ser_publicado` (rascunho) e `pode_ser_cancelado` (publicado).
- Já existentes e inalterados: `eventos_a_venda`/`evento_a_venda` só com `publicado` (vitrine e API), `comprar_ingresso` → `EventoIndisponivel` em cancelado, `vagas_disponiveis` → 0 em cancelado, `fazer_check_in` → "Evento cancelado" (F05), `painel_do_evento` com `refunded` em Estornados e fora da receita (F06).

## 3. Web

- Parcial `web/templates/web/organizador/gestao/_cancelar.html` (`<section id="evento-cancelar">`): quando `evento.pode_ser_cancelado`, o formulário `#form-cancelar` (`POST /organizador/eventos/<id>/cancelar/`, CSRF) com `onsubmit="return confirm('Cancelar este evento? Esta ação não pode ser desfeita.')"` e o botão "Cancelar evento"; quando o evento já está cancelado, o texto "Este evento foi cancelado."; em rascunho, nada.
- Parcial `_acoes.html` (F02): o link "Editar" só aparece com `evento.pode_ser_editado` e o botão "Publicar" com `evento.pode_ser_publicado`.
- `POST /organizador/eventos/<str:evento_id>/cancelar/` (view `web/views/cancelamento.py`, `organizador_requerido` por fora e `require_POST`): sucesso ou já cancelado → 302 para a gestão, com a mensagem "Evento cancelado."; `CancelamentoNaoPermitido` → 409 com a página `web/organizador/acao_rejeitada.html` e "Só evento publicado pode ser cancelado."; outro organizador ou inexistente → 404 genérico.
- `GET`/`POST` em `/editar/` e `POST` em `/publicar/` de evento cancelado → 409 com a mesma página `acao_rejeitada.html` e "Evento cancelado não pode ser alterado." (as views da F02 passam a traduzir `EventoCancelado`).
- Precedência (R13): evento inexistente ou de outro organizador → 404 genérico **antes** de qualquer 409, em cancelar, editar e publicar; o 404 não revela nome nem estado do evento.
- Não existe ação de reverter.

## 4. Testes

- `dominio/tests/test_cancelamento.py`: cancela publicado (confirmed → refunded inclusive com check-in, pending → cancelled, declined igual); idempotente; rascunho rejeitado; outro organizador; edição, publicação e `garantir_editavel` bloqueadas; sai da venda (`eventos_a_venda`, `evento_a_venda`, `comprar_ingresso`); vagas 0; propriedades `pode_ser_*`. Resposta tardia (F07-CA05), parametrizada com 0003 (aprovação) e 0004 (recusa): com `settings.GATEWAY_FATOR_ATRASO = 0.01` (o lento responde em ~0,35 s), compra, cancela, espera 0,5 s, roda `processar_cobrancas_vencidas()` e confere que o ingresso continua `cancelled` (e o confirmado `refunded`) e que a cobrança ficou com `processada_em` preenchido.
- `dominio/tests/test_cancelamento_concorrencia.py` (F07-CA06), com `django_db(transaction=True)`, a constante `REPETICOES = 50` e `threading.Barrier(2)`:
  - `test_corrida_aprovacao_e_cancelamento_nunca_deixa_confirmado`: 50 repetições, cada uma com um evento novo e um ingresso pendente; duas threads liberadas pela barreira chamam `aplicar_resposta_gateway(ingresso.id, True)` e `cancelar_evento`; o par (retorno da aprovação, status final) é sempre `(True, "refunded")` ou `(False, "cancelled")` — nunca um confirmado que vira `cancelled`, nem `confirmed`/`pending` em evento cancelado —, e o evento fica `cancelado`;
  - `test_aprovacao_que_espera_o_cancelamento_nao_muda_nada`: uma thread cancela dentro de uma transação aberta e a segura; a aprovação fica esperando a trava (confere que ainda não terminou), e, depois do commit, devolve `False` e o ingresso fica `cancelled`;
  - `test_cancelamento_que_espera_a_aprovacao_estorna`: uma thread aprova dentro de uma transação aberta e a segura; o cancelamento fica esperando a trava da linha do ingresso e, depois do commit, estorna (`refunded`).
- `web/tests/test_cancelamento.py`: bloco `#evento-cancelar` com confirmação só em publicado; POST cancela; rascunho 409; outro organizador 404 sem efeito; visitante 302 e participante 403; gestão de cancelado sem editar nem publicar; editar/publicar 409 com a mensagem; lista do organizador com "Cancelado".
- O teste da F02 `test_publicar_evento_so_a_partir_de_rascunho_e_idempotente` passa a esperar `EventoCancelado` ao publicar evento cancelado (mudança de comportamento prevista no PRD para a F07).

## 5. Critérios cross desta feature

- **XF-14 [F02→F07]**: sai da vitrine; gestão sem editar nem publicar; `POST` de editar e publicar rejeitados; lista do organizador com "Cancelado".
- **XF-15 [F03→F07]**: Meus ingressos com "estornado" e "cancelado" logo após; o pendente lento continua "cancelado" depois que o worker processa; vagas 0; compra pela vitrine recusada.
- **XF-16 [F04→F07]**: some de `GET /api/partner/events`; compra 404 `event_not_available`; em até 10 s o confirmado da API está `refunded` e o pendente (0003) `cancelled`, e continua `cancelled` 45 s após a compra.
- **XF-17 [F05→F07]**: code de ingresso que estava confirmado → "Evento cancelado"; code de outro evento → "Ingresso inválido para este evento".
- **XF-18 [F06→F07]**: cenário dos passos 12 a 14 → painel Confirmados 0, Pendentes 0, Check-ins 0, Vagas disponíveis 0, Receita "R$ 0,00", Estornados 1.
- **XF-19 [F04+F05+F06→F07]**: ingresso da API confirmado e com check-in; após o cancelamento, `status: "refunded"` e `checkedIn: true`; painel Estornados 1, Check-ins 0, Receita "R$ 0,00"; check-in do mesmo code → "Evento cancelado".
