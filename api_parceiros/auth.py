"""Autenticação da API de parceiros: só a chave do cabeçalho `X-Api-Key`.

A chave esperada é `settings.CATRACA_CHAVE_PARCEIRO` (valor de desenvolvimento no compose.yaml
e no README). A comparação é em tempo constante; configuração vazia nunca autentica. Sem chave
válida, a resposta é 401 `{"error":"unauthorized"}`, antes de qualquer outra checagem.
"""

import hmac
from functools import wraps

from django.conf import settings

from api_parceiros.respostas import erro

CABECALHO_CHAVE = "X-Api-Key"


def chave_valida(recebida) -> bool:
    """Verdadeiro só se a chave recebida é igual à configurada (e a configurada não é vazia)."""
    esperada = getattr(settings, "CATRACA_CHAVE_PARCEIRO", "") or ""
    if not esperada or not recebida:
        return False
    return hmac.compare_digest(recebida.encode("utf-8"), esperada.encode("utf-8"))


def exigir_chave_parceiro(view):
    """Decorador: 401 `unauthorized` sem `X-Api-Key` válida; senão chama a view."""

    @wraps(view)
    def com_chave(request, *args, **kwargs):
        if not chave_valida(request.headers.get(CABECALHO_CHAVE)):
            return erro("unauthorized", 401)
        return view(request, *args, **kwargs)

    return com_chave
