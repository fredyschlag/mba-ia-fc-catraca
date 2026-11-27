"""Compra na vitrine e Meus ingressos (F03).

As views só chamam `dominio.servicos.compras` e traduzem as exceções: `CartaoInvalido` e
`IngressosEsgotados` → detalhe com a mensagem (200, nada criado); `EventoIndisponivel` → 404.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from dominio.excecoes import (
    MSG_INGRESSOS_ESGOTADOS,
    EventoIndisponivel,
    IngressosEsgotados,
    ValidacaoError,
)
from dominio.models import Ingresso
from dominio.servicos.compras import comprar_ingresso, ingressos_do_participante
from dominio.servicos.eventos import evento_a_venda
from web.acesso import participante_requerido
from web.views.vitrine import contexto_detalhe

MSG_COMPRA_REGISTRADA = "Compra registrada. O pagamento está sendo processado."


def _detalhe_com_erro(request, evento_id, mensagem):
    try:
        evento = evento_a_venda(evento_id)
    except EventoIndisponivel as erro:
        raise Http404 from erro
    contexto = contexto_detalhe(evento, erro_compra=mensagem)
    return render(request, "web/vitrine/detalhe.html", contexto)


@participante_requerido
@require_POST
def comprar(request, evento_id):
    try:
        comprar_ingresso(
            evento_id,
            cartao=request.POST.get("cartao", ""),
            email_comprador=request.user.email,
            canal=Ingresso.Canal.VITRINE,
            comprador=request.user,
        )
    except EventoIndisponivel as erro:
        raise Http404 from erro
    except IngressosEsgotados:
        return _detalhe_com_erro(request, evento_id, MSG_INGRESSOS_ESGOTADOS)
    except ValidacaoError as erro:
        mensagem = next(iter(erro.erros.values()))[0]
        return _detalhe_com_erro(request, evento_id, mensagem)
    messages.success(request, MSG_COMPRA_REGISTRADA)
    return redirect("/meus-ingressos/")


@participante_requerido
@require_GET
def meus_ingressos(request):
    ingressos = ingressos_do_participante(request.user)
    return render(request, "web/compras/meus_ingressos.html", {"ingressos": ingressos})
