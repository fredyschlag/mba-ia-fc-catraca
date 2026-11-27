"""Vitrine pública (F02) e bloco de compra no detalhe (F03).

As views só chamam os serviços do domínio e traduzem `EventoIndisponivel` em 404.
"""

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from dominio.excecoes import EventoIndisponivel
from dominio.servicos.compras import vagas_disponiveis
from dominio.servicos.eventos import evento_a_venda, eventos_a_venda


@require_GET
def vitrine(request):
    return render(request, "web/vitrine/lista.html", {"eventos": eventos_a_venda()})


def contexto_detalhe(evento, **extra):
    return {"evento": evento, "vagas_disponiveis": vagas_disponiveis(evento), **extra}


@require_GET
def detalhe(request, evento_id):
    try:
        evento = evento_a_venda(evento_id)
    except EventoIndisponivel as erro:
        raise Http404 from erro
    return render(request, "web/vitrine/detalhe.html", contexto_detalhe(evento))
