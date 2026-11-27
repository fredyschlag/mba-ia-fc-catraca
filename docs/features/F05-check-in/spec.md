# Spec — F05 Check-in (W4)

- PRD: [docs/prd.md](../../prd.md), seções 3.2 (F05), 6 (F05-CA01…CA08) e 7 (XF-07 e XF-08, atribuídos a esta feature, a consumidora).
- Regras: R10 (as cinco mensagens, na ordem), R04 (check-in na página de gestão), R13 (só o dono do evento).
- Consome: F02 (`evento_do_organizador`, slot `#check-in` em `web/organizador/gestao/_check_in.html`, `Evento.status`, página de gestão), F03 (`Ingresso.codigo`, `status`, `check_in_em`), F01 (`organizador_requerido`).
- Plano: [plano.md](plano.md) · Contrato: [contrato.md](contrato.md).

## 1. Escopo

Na página de gestão de um evento, o organizador dono informa o código de um ingresso e vê uma das cinco mensagens exatas de R10, escolhida pela primeira situação verdadeira da lista, na ordem. "Entrada liberada" grava `Ingresso.check_in_em` uma única vez, mesmo com check-ins simultâneos do mesmo código. O status do ingresso não muda: check-in não é status.

Fica fora: cancelar o evento (F07; aqui o evento cancelado é preparado direto no banco), contar check-ins no painel (F06), `checkedIn` na API (F04, que lê o mesmo campo).

**Paralelismo (W4).** A F05 não consome nada da F04 e só mexe em arquivos próprios (`dominio/servicos/checkin.py`, `web/views/checkin.py`, o parcial `_check_in.html`, testes novos); os arquivos compartilhados são só `web/urls.py` (uma rota) e `estado.json`.

## 2. Domínio — `dominio/servicos/checkin.py`

### 2.1 `ResultadoCheckIn`

`enum.StrEnum` cujos valores são as mensagens exatas de R10, sem ponto final, declaradas na ordem de avaliação:

| Ordem | Membro | Valor (texto exibido) | Situação |
|---|---|---|---|
| 1 | `INVALIDO` | "Ingresso inválido para este evento" | o código não existe ou é de outro evento (de qualquer organizador, inclusive quando o evento atual está cancelado) |
| 2 | `EVENTO_CANCELADO` | "Evento cancelado" | o evento está com `status = cancelado` (qualquer status do ingresso, com ou sem check-in) |
| 3 | `NAO_CONFIRMADO` | "Ingresso não confirmado" | o ingresso não está `confirmed` (`pending`, `declined`, `cancelled`, `refunded`) |
| 4 | `JA_UTILIZADO` | "Ingresso já utilizado" | `check_in_em` já preenchido |
| 5 | `ENTRADA_LIBERADA` | "Entrada liberada" | nenhuma das anteriores |

### 2.2 `normalizar_codigo(codigo) -> str`

`None` vira `""`; remove espaços (e outros brancos) nas pontas com `strip()` e passa as letras para maiúsculas com `upper()`. Nada além disso: espaços no meio não são removidos (o código fica inválido).

### 2.3 `fazer_check_in(organizador, evento_id, codigo) -> ResultadoCheckIn`

Numa única transação (`transaction.atomic()`):

1. Normaliza o código (2.2).
2. **Trava a linha do evento do dono**: `Evento.objects.select_for_update().get(id_publico=evento_id, organizador=organizador)` — a mesma trava de `comprar_ingresso`, `editar_evento` e, na F07, `cancelar_evento`. Evento inexistente ou de outro organizador → `EventoNaoEncontrado` (nada é lido sobre o código, nada muda).
3. Código fora do formato `^[A-Z0-9]{8}$` (vazio, longo, com espaço no meio, com caractere de controle) → `INVALIDO`, sem consultar ingresso (evita levar ao Postgres texto que ele rejeita, como `\x00`).
4. **Trava o ingresso do evento**: `Ingresso.objects.select_for_update().get(codigo=codigo, evento=evento)`. Não existe nesse evento (inexistente ou de outro evento) → `INVALIDO`.
5. `evento.status == cancelado` → `EVENTO_CANCELADO`.
6. `ingresso.status != confirmed` → `NAO_CONFIRMADO`.
7. `ingresso.check_in_em is not None` → `JA_UTILIZADO`.
8. Senão grava `check_in_em = timezone.now()` (`save(update_fields=["check_in_em"])`) e devolve `ENTRADA_LIBERADA`. O status continua `confirmed`.

Só o passo 8 escreve no banco; os resultados 1 a 4 não mudam nada.

**Atomicidade (F05-CA07).** Dois check-ins do mesmo código disputam primeiro a trava do evento e depois a do ingresso; o segundo só lê o ingresso depois que o primeiro fez commit e, em READ COMMITTED, já enxerga `check_in_em` preenchido, então devolve `JA_UTILIZADO`. A trava do ingresso também serializa o check-in com a resposta do gateway (`UPDATE … WHERE status = 'pending'`, que trava a mesma linha). Ordem das travas, sempre evento → ingresso, igual à da compra e à do cancelamento previsto na F07; o worker do gateway só trava a cobrança e o ingresso, nunca o evento, então não há ciclo de espera.

**Por que o evento também é travado.** O PRD exige travar o ingresso; travar antes o evento serializa o check-in com o cancelamento (F07): ou o check-in termina antes do cancelamento (e o ingresso confirmado com check-in vira `refunded` com `check_in_em` preservado), ou começa depois e lê `status = cancelado` → "Evento cancelado". Nunca "Entrada liberada" num evento já cancelado.

## 3. Web

### 3.1 Bloco `#check-in` — `web/templates/web/organizador/gestao/_check_in.html`

O parcial (incluído pela gestão da F02, que passa `evento` e `request`) passa a ter, dentro de `<section id="check-in">`:

- título `<h3>Check-in</h3>`;
- formulário `<form id="form-check-in" method="post" action="/organizador/eventos/<id>/check-in/">` com `{% csrf_token %}`, rótulo "Código do ingresso", campo `<input id="campo-codigo" name="codigo" type="text" autocomplete="off" required>` e botão "Fazer check-in";
- quando o contexto tem `check_in_resultado` (só na resposta do `POST`): `<p id="check-in-mensagem">TEXTO</p>`, com o valor exato do enum e nada mais dentro do elemento, numa linha só do HTML.

O campo aparece em qualquer status do evento, inclusive cancelado (decisão do PRD, F05-CA03: vale a lista de R10). O campo volta vazio depois de cada envio, pronto para o próximo código.

### 3.2 `POST /organizador/eventos/<str:evento_id>/check-in/` — `web/views/checkin.py`

View `check_in`, com `organizador_requerido` como decorador mais externo e `require_POST` logo abaixo:

| Quem / o quê | Resposta |
|---|---|
| visitante (qualquer método) | 302 para `/contas/entrar/` (a guarda não põe `next` em POST) |
| participante (qualquer método) | 403 genérico |
| organizador, `GET` | 405 |
| organizador, evento inexistente ou de outro organizador | 404 genérico (`404.html`): `evento_do_organizador` lança `EventoNaoEncontrado`; `fazer_check_in` nem é chamado, nada muda e o corpo não traz nenhuma mensagem de check-in nem dado do evento |
| organizador dono | 200 com a página de gestão inteira (`web/organizador/gestao.html`) e `#check-in-mensagem` com o resultado |

A view chama `evento_do_organizador(request.user, evento_id)` (404 se lançar), depois `fazer_check_in(request.user, evento_id, request.POST.get("codigo", ""))` (também traduz `EventoNaoEncontrado` em 404, caso o evento suma entre as duas chamadas) e renderiza `web/organizador/gestao.html` com `{"evento": evento, "check_in_resultado": resultado}`. Sem PRG: a resposta do próprio `POST` mostra a mensagem; recarregar a gestão com `GET` não mostra mensagem nenhuma. A view da gestão (F02) e o template `gestao.html` não mudam.

Rota em `web/urls.py`, nome `organizador_check_in`, logo depois de `publicar`. O teste da F01 que percorre todas as rotas sob `/organizador/` passa a cobrir esta também.

## 4. Testes

- `dominio/tests/test_checkin.py`: as cinco mensagens exatas e a ordem do enum; cada situação de R10 (inexistente; de outro evento do mesmo organizador e de outro organizador, confirmado; de outro evento num evento cancelado; evento cancelado com o ingresso em cada um dos cinco status, com e sem check-in; em evento publicado, cada um dos quatro status não confirmados (`pending`, `declined`, `cancelled`, `refunded`), com e sem `check_in_em`, sempre "Ingresso não confirmado" (item 3 antes do 4); já utilizado; entrada liberada com `check_in_em` gravado e status `confirmed`); normalização; código mal formado (vazio, `None`, longo, com `\x00`); evento em rascunho: todo código (inexistente ou de outro evento) é "Ingresso inválido para este evento" (`test_evento_em_rascunho_so_tem_codigos_invalidos`); evento de outro organizador e inexistente → `EventoNaoEncontrado` sem efeito; o SQL do check-in trava o evento e depois o ingresso (`FOR UPDATE`, nesta ordem); resultados rejeitados não escrevem.
- `dominio/tests/test_checkin_concorrencia.py` (F05-CA07), `test_check_ins_simultaneos_liberam_uma_unica_vez`: `django_db(transaction=True)`; constantes `CHECK_INS_SIMULTANEOS = 10` e `RODADAS = 10`; 10 threads liberadas juntas por `threading.Barrier(CHECK_INS_SIMULTANEOS)`, cada uma com a sua conexão (fechada no fim com `connection.close()`), fazem o check-in do mesmo código confirmado → exatamente 1 `ENTRADA_LIBERADA` e 9 `JA_UTILIZADO`; repetido em `RODADAS` = 10 ingressos novos.
- `web/tests/test_checkin.py`: bloco na gestão do dono (formulário, campo, CSRF, sem mensagem no `GET`); cada mensagem pela tela; normalização pela tela; 404 para outro organizador sem efeito e sem mensagem; visitante 302 e participante 403 sem efeito; `GET` 405; evento cancelado mantém o campo e responde "Evento cancelado"; a resposta do `POST` é a gestão inteira.

## 5. Critérios cross desta feature

- **XF-07 [F02→F05]**: o bloco `#check-in` aparece na gestão do dono; o organizador B, ao enviar um código pela URL de check-in de um evento de A, recebe 404 e nada muda.
- **XF-08 [F03→F05]**: o código exibido em Meus ingressos para um ingresso confirmado resulta em "Entrada liberada"; o de um pendente (final `0003`) em "Ingresso não confirmado"; o de um ingresso de outro evento em "Ingresso inválido para este evento".

## 6. Decisões menores

- Check-in de evento em rascunho segue a lista: como rascunho não vende, todo código dá "Ingresso inválido para este evento" (contrato C-07 e `test_evento_em_rascunho_so_tem_codigos_invalidos`).
- O código digitado não é ecoado na resposta e o campo volta sem `value`; só a mensagem aparece (no 404, nem ela). Conferido no contrato (C-04) e em `test_resposta_do_check_in_e_a_gestao_inteira`.
- Nenhuma mudança de modelo nem migration: `check_in_em` já existe desde a F03.
