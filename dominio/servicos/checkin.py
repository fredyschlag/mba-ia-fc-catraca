"""Check-in na porta do evento (F05).

Regra R10: a primeira situação verdadeira, nesta ordem, define a mensagem exibida:
1. o código não existe ou é de outro evento → "Ingresso inválido para este evento";
2. o evento está cancelado → "Evento cancelado";
3. o ingresso não está confirmado → "Ingresso não confirmado";
4. o ingresso já passou pelo check-in → "Ingresso já utilizado";
5. senão → "Entrada liberada" (grava `check_in_em`; o status continua `confirmed`).

Atomicidade: numa transação, trava a linha do evento (a mesma trava da compra, da edição e do
cancelamento) e depois a do ingresso. Check-ins simultâneos do mesmo código esperam um pelo
outro; o segundo já enxerga `check_in_em` preenchido e devolve "Ingresso já utilizado".
"""

import enum
import re

from django.db import transaction
from django.utils import timezone

from dominio.excecoes import EventoNaoEncontrado
from dominio.models import Evento, Ingresso

_RE_CODIGO = re.compile(r"[A-Z0-9]{8}")


class ResultadoCheckIn(enum.StrEnum):
    """As cinco mensagens exatas de R10, na ordem em que são avaliadas."""

    INVALIDO = "Ingresso inválido para este evento"
    EVENTO_CANCELADO = "Evento cancelado"
    NAO_CONFIRMADO = "Ingresso não confirmado"
    JA_UTILIZADO = "Ingresso já utilizado"
    ENTRADA_LIBERADA = "Entrada liberada"


def normalizar_codigo(codigo) -> str:
    """Sem espaços nas pontas e com as letras em maiúsculas; `None` vira ""."""
    return ("" if codigo is None else str(codigo)).strip().upper()


def fazer_check_in(organizador, evento_id, codigo) -> ResultadoCheckIn:
    """Check-in do código no evento do `organizador` (R10).

    Lança `EventoNaoEncontrado` se o evento não existe ou é de outro organizador (R13), sem
    olhar o código nem mudar nada. Só "Entrada liberada" escreve no banco.
    """
    codigo = normalizar_codigo(codigo)
    with transaction.atomic():
        try:
            evento = Evento.objects.select_for_update().get(
                id_publico=evento_id, organizador=organizador
            )
        except Evento.DoesNotExist as erro:
            raise EventoNaoEncontrado(evento_id) from erro
        if not _RE_CODIGO.fullmatch(codigo):
            return ResultadoCheckIn.INVALIDO
        try:
            ingresso = Ingresso.objects.select_for_update().get(codigo=codigo, evento=evento)
        except Ingresso.DoesNotExist:
            return ResultadoCheckIn.INVALIDO
        if evento.status == Evento.Status.CANCELADO:
            return ResultadoCheckIn.EVENTO_CANCELADO
        if ingresso.status != Ingresso.Status.CONFIRMADO:
            return ResultadoCheckIn.NAO_CONFIRMADO
        if ingresso.check_in_em is not None:
            return ResultadoCheckIn.JA_UTILIZADO
        ingresso.check_in_em = timezone.now()
        ingresso.save(update_fields=["check_in_em"])
        return ResultadoCheckIn.ENTRADA_LIBERADA
