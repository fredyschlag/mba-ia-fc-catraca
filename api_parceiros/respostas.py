"""Respostas JSON da API de parceiros.

JSON compacto (sem espaços), UTF-8 sem escapar acentos e com as chaves na ordem em que os
serializadores as montam (a ordem do brief), para o corpo ser previsível byte a byte.
"""

from django.http import JsonResponse

_JSON = {"separators": (",", ":"), "ensure_ascii": False}


def responder(dados, status=200) -> JsonResponse:
    """`dados` em JSON com `Content-Type: application/json`."""
    return JsonResponse(dados, status=status, safe=False, json_dumps_params=_JSON)


def erro(codigo: str, status: int) -> JsonResponse:
    """`{"error":"<codigo>"}` com o status HTTP dado."""
    return responder({"error": codigo}, status)
