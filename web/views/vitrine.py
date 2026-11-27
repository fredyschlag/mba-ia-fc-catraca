"""Vitrine pública (F02): lista de eventos à venda e detalhe de cada um.

As views só chamam `eventos_a_venda` e `evento_a_venda` e traduzem `EventoIndisponivel` em 404.
"""

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from dominio.excecoes import EventoIndisponivel
from dominio.servicos.eventos import evento_a_venda, eventos_a_venda


@require_GET
def vitrine(request):
    return render(request, "web/vitrine/lista.html", {"eventos": eventos_a_venda()})


@require_GET
def detalhe(request, evento_id):
    try:
        evento = evento_a_venda(evento_id)
    except EventoIndisponivel as erro:
        raise Http404 from erro
    return render(request, "web/vitrine/detalhe.html", {"evento": evento})
