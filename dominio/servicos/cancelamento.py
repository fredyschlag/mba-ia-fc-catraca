"""Cancelamento de evento (F07).

R11: o organizador cancela um evento publicado e o cancelamento é irreversível. É síncrono: na
mesma transação que trava a linha do evento (a mesma trava da compra, da edição e do check-in),
o evento passa a `cancelado` e um único `UPDATE` passa os ingressos `confirmed` a `refunded` e
os `pending` a `cancelled`.

Corrida com o gateway: o `UPDATE` daqui e o `UPDATE … WHERE status = 'pending'` de
`aplicar_resposta_gateway` disputam a linha do ingresso e o Postgres os serializa, reavaliando o
`WHERE` sobre a versão já gravada. Se a aprovação grava antes, o ingresso está `confirmed` e o
`CASE` o estorna; se o cancelamento grava antes, a resposta encontra `cancelled` e não muda nada.
Um único comando evita a janela que haveria entre "estornar confirmados" e "cancelar pendentes".
"""

from django.db import transaction
from django.db.models import Case, Value, When

from dominio.excecoes import CancelamentoNaoPermitido
from dominio.models import Evento, Ingresso
from dominio.servicos.eventos import _travar_evento_do_organizador


def cancelar_evento(organizador, evento_id) -> Evento:
    """Cancela o evento publicado do `organizador` (R11). Já cancelado: devolve sem mudar nada.

    Lança `EventoNaoEncontrado` (inexistente ou de outro organizador) ou
    `CancelamentoNaoPermitido` (rascunho).
    """
    with transaction.atomic():
        evento = _travar_evento_do_organizador(organizador, evento_id)
        if evento.status == Evento.Status.CANCELADO:
            return evento
        if evento.status != Evento.Status.PUBLICADO:
            raise CancelamentoNaoPermitido()
        evento.status = Evento.Status.CANCELADO
        evento.save(update_fields=["status"])
        Ingresso.objects.filter(
            evento=evento,
            status__in=[Ingresso.Status.PENDENTE, Ingresso.Status.CONFIRMADO],
        ).update(
            status=Case(
                When(status=Ingresso.Status.CONFIRMADO, then=Value(Ingresso.Status.ESTORNADO)),
                default=Value(Ingresso.Status.CANCELADO),
            )
        )
        return evento
