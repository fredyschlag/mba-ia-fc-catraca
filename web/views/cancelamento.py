"""Cancelamento de evento pela página de gestão (F07).

A view só chama `cancelar_evento` e traduz as exceções: `EventoNaoEncontrado` → 404 genérico
(R13); `CancelamentoNaoPermitido` (rascunho) → 409 com a mensagem do domínio.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from dominio.excecoes import CancelamentoNaoPermitido, EventoNaoEncontrado
from dominio.servicos.cancelamento import cancelar_evento
from dominio.servicos.eventos import evento_do_organizador
from web.acesso import organizador_requerido
from web.views.organizador import acao_rejeitada


@organizador_requerido
@require_POST
def cancelar(request, evento_id):
    try:
        evento = cancelar_evento(request.user, evento_id)
    except EventoNaoEncontrado as erro:
        raise Http404 from erro
    except CancelamentoNaoPermitido as erro:
        return acao_rejeitada(request, evento_do_organizador(request.user, evento_id), str(erro))
    messages.success(request, "Evento cancelado.")
    return redirect(f"/organizador/eventos/{evento.id_publico}/")
