"""Views da API de parceiros (contrato fixo do brief).

Cada view é, de fora para dentro: `csrf_exempt` → `exigir_chave_parceiro` → método. Não usam
sessão nem login. Só chamam serviços do domínio e traduzem as exceções em resposta JSON:
`ValidacaoError` (inclui `CartaoInvalido`) → 422, `EventoIndisponivel` → 404,
`IngressosEsgotados` → 409, `IngressoNaoEncontrado` → 404. A ordem 422 > 404 > 409 vem do
domínio: `comprar_ingresso` valida cartão e e-mail antes de olhar o evento.
"""

import json
from functools import wraps

from django.views.decorators.csrf import csrf_exempt

from api_parceiros.auth import exigir_chave_parceiro
from api_parceiros.respostas import erro, responder
from api_parceiros.serializadores import compra_para_api, evento_para_api, ingresso_para_api
from dominio.excecoes import (
    EventoIndisponivel,
    IngressoNaoEncontrado,
    IngressosEsgotados,
    ValidacaoError,
)
from dominio.models import Ingresso
from dominio.servicos.compras import comprar_ingresso, consultar_ingresso
from dominio.servicos.eventos import eventos_a_venda

MSG_CORPO_INVALIDO = "Envie um objeto JSON com buyerEmail e cardNumber (textos)."


def so_metodo(permitido: str):
    """405 `method_not_allowed` (com `Allow`) para outro método; vem depois da chave."""

    def decorador(view):
        @wraps(view)
        def com_metodo(request, *args, **kwargs):
            if request.method != permitido:
                resposta = erro("method_not_allowed", 405)
                resposta["Allow"] = permitido
                return resposta
            return view(request, *args, **kwargs)

        return com_metodo

    return decorador


def ler_corpo_da_compra(corpo: bytes) -> tuple[str, str]:
    """(buyerEmail, cardNumber) do corpo JSON; `ValidacaoError` se o formato não serve.

    Só confere o formato da requisição (objeto JSON com dois textos). E-mail e cartão são
    validados pelo domínio, em `comprar_ingresso`.
    """
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as falha:
        raise ValidacaoError({"corpo": [MSG_CORPO_INVALIDO]}) from falha
    if not isinstance(dados, dict):
        raise ValidacaoError({"corpo": [MSG_CORPO_INVALIDO]})
    email, cartao = dados.get("buyerEmail"), dados.get("cardNumber")
    if not isinstance(email, str) or not isinstance(cartao, str):
        raise ValidacaoError({"corpo": [MSG_CORPO_INVALIDO]})
    return email, cartao


@csrf_exempt
@exigir_chave_parceiro
@so_metodo("GET")
def eventos(request):
    """Eventos à venda (publicados), na ordem do início; `availableSeats` conforme R05."""
    return responder([evento_para_api(evento) for evento in eventos_a_venda()])


@csrf_exempt
@exigir_chave_parceiro
@so_metodo("POST")
def comprar(request, evento_id):
    """Compra de um ingresso pelo parceiro: 202 pendente, sem esperar o gateway (R06)."""
    try:
        email, cartao = ler_corpo_da_compra(request.body)
        ingresso = comprar_ingresso(
            evento_id,
            cartao=cartao,
            email_comprador=email,
            canal=Ingresso.Canal.API,
            comprador=None,
        )
    except ValidacaoError:
        return erro("invalid_request", 422)
    except EventoIndisponivel:
        return erro("event_not_available", 404)
    except IngressosEsgotados:
        return erro("sold_out", 409)
    return responder(compra_para_api(ingresso), 202)


@csrf_exempt
@exigir_chave_parceiro
@so_metodo("GET")
def ingresso(request, ticket_id):
    """Consulta de um ingresso de qualquer canal (vitrine ou API)."""
    try:
        encontrado = consultar_ingresso(ticket_id)
    except IngressoNaoEncontrado:
        return erro("ticket_not_found", 404)
    return responder(ingresso_para_api(encontrado))
