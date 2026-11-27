"""Serializadores da API de parceiros: só leem atributos e chamam serviços do domínio.

As chaves saem na ordem do contrato fixo do brief.
"""

from django.utils import timezone

from dominio.servicos.compras import vagas_disponiveis


def inicio_iso(inicio) -> str:
    """ISO 8601 com offset, no fuso do projeto (America/Sao_Paulo), sem microssegundos."""
    local = timezone.localtime(inicio, timezone.get_default_timezone())
    return local.replace(microsecond=0).isoformat()


def evento_para_api(evento) -> dict:
    return {
        "id": evento.id_publico,
        "name": evento.nome,
        "startsAt": inicio_iso(evento.inicio),
        "priceCents": evento.preco_centavos,
        "availableSeats": vagas_disponiveis(evento),
    }


def ingresso_para_api(ingresso) -> dict:
    return {
        "ticketId": ingresso.id_publico,
        "code": ingresso.codigo,
        "eventId": ingresso.evento.id_publico,
        "status": ingresso.status,
        "checkedIn": ingresso.check_in_em is not None,
    }


def compra_para_api(ingresso) -> dict:
    return {
        "ticketId": ingresso.id_publico,
        "code": ingresso.codigo,
        "status": ingresso.status,
    }
