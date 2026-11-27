"""Views da API de parceiros (contrato fixo do brief).

Cada view é, de fora para dentro: `csrf_exempt` → `exigir_chave_parceiro` → método. Não usam
sessão nem login. Só chamam serviços do domínio e traduzem as exceções em resposta JSON.
"""

from functools import wraps

from django.views.decorators.csrf import csrf_exempt

from api_parceiros.auth import exigir_chave_parceiro
from api_parceiros.respostas import erro, responder
from api_parceiros.serializadores import evento_para_api
from dominio.servicos.eventos import eventos_a_venda


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
    return erro("not_implemented", 501)


@csrf_exempt
@exigir_chave_parceiro
@so_metodo("GET")
def ingresso(request, ticket_id):
    return erro("not_implemented", 501)
