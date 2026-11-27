"""Painel do evento (F06): os seis números de R12, contando as vendas da vitrine e da API.

Definições (R12): Confirmados = ingressos `confirmed` (com ou sem check-in); Pendentes =
`pending`; Check-ins = `confirmed` com `check_in_em`; Vagas disponíveis = R05
(`compras.vagas_disponiveis`); Receita = soma de `valor_centavos` dos `confirmed` (o preço gravado
em cada compra, R03); Estornados = `refunded`. Recusados e cancelados não entram em nenhum número.
Nada é guardado em cache: cada chamada lê o banco.
"""

from dataclasses import dataclass

from django.db.models import Count, Q, Sum

from dominio.models import Ingresso
from dominio.servicos.compras import vagas_disponiveis

_CONFIRMADO = Ingresso.Status.CONFIRMADO


@dataclass(frozen=True)
class Painel:
    confirmados: int
    pendentes: int
    check_ins: int
    vagas_disponiveis: int
    receita_centavos: int
    estornados: int


def painel_do_evento(evento) -> Painel:
    """Os seis números do painel do evento, numa única consulta agregada (mais a de vagas)."""
    numeros = Ingresso.objects.filter(evento=evento).aggregate(
        confirmados=Count("id", filter=Q(status=_CONFIRMADO)),
        pendentes=Count("id", filter=Q(status=Ingresso.Status.PENDENTE)),
        check_ins=Count("id", filter=Q(status=_CONFIRMADO, check_in_em__isnull=False)),
        receita=Sum("valor_centavos", filter=Q(status=_CONFIRMADO)),
        estornados=Count("id", filter=Q(status=Ingresso.Status.ESTORNADO)),
    )
    return Painel(
        confirmados=numeros["confirmados"],
        pendentes=numeros["pendentes"],
        check_ins=numeros["check_ins"],
        vagas_disponiveis=vagas_disponiveis(evento),
        receita_centavos=numeros["receita"] or 0,
        estornados=numeros["estornados"],
    )
