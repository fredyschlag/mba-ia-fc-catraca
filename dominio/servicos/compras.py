"""Compra, vagas e Meus ingressos (F03).

Regras: R05 (vagas ocupadas = pendentes + confirmados; disponíveis = lotação − ocupadas, zero em
cancelado), R06 (a compra nasce pendente, ocupa vaga e não espera o gateway), R07 (nunca passa da
lotação, nem com compras simultâneas), R09 (código único), R03/R12 (preço gravado no ingresso).

Garantia de R07: `comprar_ingresso` trava a linha do evento com `SELECT … FOR UPDATE` antes de
contar as ocupadas. Duas compras do mesmo evento esperam uma pela outra; em READ COMMITTED, a
contagem feita depois de obter a trava já enxerga o ingresso criado pela transação anterior.
A edição de lotação (`editar_evento`) e o cancelamento (F07) usam a mesma trava.
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from dominio.excecoes import (
    CartaoInvalido,
    EventoIndisponivel,
    IngressoNaoEncontrado,
    IngressosEsgotados,
    ValidacaoError,
)
from dominio.models import (
    CobrancaGateway,
    Evento,
    Ingresso,
    gerar_codigo_ingresso,
    gerar_id_ingresso,
)
from dominio.servicos.gateway import GatewaySimulado

MSG_EMAIL_COMPRADOR_INVALIDO = "Informe um e-mail válido."
MSG_LOTACAO_ABAIXO_DAS_OCUPADAS = "A lotação não pode ser menor que as vagas ocupadas ({})."

STATUS_QUE_OCUPAM = (Ingresso.Status.PENDENTE, Ingresso.Status.CONFIRMADO)

_RE_CARTAO = re.compile(r"^[0-9]{16}$")
_TENTATIVAS = 5


def vagas_ocupadas(evento) -> int:
    """Ingressos pendentes + confirmados do evento (R05)."""
    return Ingresso.objects.filter(evento=evento, status__in=STATUS_QUE_OCUPAM).count()


def vagas_disponiveis(evento) -> int:
    """Lotação − ocupadas; zero em evento cancelado (R05)."""
    if evento.status == Evento.Status.CANCELADO:
        return 0
    return max(0, evento.lotacao - vagas_ocupadas(evento))


def validar_cartao(cartao) -> str:
    """O número sem espaços nas pontas, se tiver exatamente 16 dígitos; senão `CartaoInvalido`."""
    numero = ("" if cartao is None else str(cartao)).strip()
    if not _RE_CARTAO.match(numero):
        raise CartaoInvalido()
    return numero


def validar_email_comprador(email) -> str:
    """O e-mail normalizado (minúsculo, sem espaços nas pontas); senão `ValidacaoError`."""
    normalizado = ("" if email is None else str(email)).strip().lower()
    try:
        if not normalizado or len(normalizado) > 254:
            raise ValidationError("vazio ou longo")
        validate_email(normalizado)
    except ValidationError as erro:
        raise ValidacaoError({"email_comprador": [MSG_EMAIL_COMPRADOR_INVALIDO]}) from erro
    return normalizado


def _criar_ingresso(evento, *, numero, email, canal, comprador) -> Ingresso:
    """Cria o ingresso e a cobrança; troca código e id se colidirem (savepoint por tentativa)."""
    agora = timezone.now()
    for tentativa in range(_TENTATIVAS):
        try:
            with transaction.atomic():
                ingresso = Ingresso.objects.create(
                    id_publico=gerar_id_ingresso(),
                    codigo=gerar_codigo_ingresso(),
                    evento=evento,
                    comprador=comprador,
                    email_comprador=email,
                    canal=canal,
                    status=Ingresso.Status.PENDENTE,
                    valor_centavos=evento.preco_centavos,
                    cartao_final=numero[-4:],
                    criado_em=agora,
                )
                break
        except IntegrityError:
            if tentativa == _TENTATIVAS - 1:
                raise
    aprovado = GatewaySimulado.resultado_para(numero)
    CobrancaGateway.objects.create(
        ingresso=ingresso,
        resultado=(
            CobrancaGateway.Resultado.APROVADO if aprovado else CobrancaGateway.Resultado.RECUSADO
        ),
        responder_em=agora + GatewaySimulado.atraso_para(numero),
        criada_em=agora,
    )
    return ingresso


def comprar_ingresso(evento_id, *, cartao, email_comprador, canal, comprador=None) -> Ingresso:
    """Compra um ingresso do evento. Devolve o ingresso `pending`, sem esperar o gateway.

    Ordem: valida cartão e e-mail (sem tocar no banco) → trava o evento → confere se está à
    venda → conta as ocupadas → cria ingresso e cobrança. Lança `CartaoInvalido`,
    `ValidacaoError` (e-mail), `EventoIndisponivel` ou `IngressosEsgotados`.
    """
    numero = validar_cartao(cartao)
    email = validar_email_comprador(email_comprador)
    with transaction.atomic():
        try:
            evento = Evento.objects.select_for_update().get(id_publico=evento_id)
        except Evento.DoesNotExist as erro:
            raise EventoIndisponivel(evento_id) from erro
        if evento.status != Evento.Status.PUBLICADO:
            raise EventoIndisponivel(evento_id)
        if vagas_ocupadas(evento) >= evento.lotacao:
            raise IngressosEsgotados()
        return _criar_ingresso(evento, numero=numero, email=email, canal=canal, comprador=comprador)


def ingressos_do_participante(usuario):
    """Os ingressos comprados pelo participante, do mais novo para o mais antigo (R09)."""
    return Ingresso.objects.filter(comprador=usuario).select_related("evento").order_by("-id")


def consultar_ingresso(ticket_id) -> Ingresso:
    """O ingresso com esse id público, de qualquer canal; senão `IngressoNaoEncontrado`."""
    try:
        return Ingresso.objects.select_related("evento").get(id_publico=ticket_id)
    except Ingresso.DoesNotExist as erro:
        raise IngressoNaoEncontrado(ticket_id) from erro


def validar_lotacao_contra_ocupadas(evento, nova_lotacao, erros) -> None:
    """R03: com a linha do evento travada, a lotação não fica menor que as ocupadas."""
    if nova_lotacao is None:
        return
    ocupadas = vagas_ocupadas(evento)
    if nova_lotacao < ocupadas:
        erros["lotacao"] = [MSG_LOTACAO_ABAIXO_DAS_OCUPADAS.format(ocupadas)]
