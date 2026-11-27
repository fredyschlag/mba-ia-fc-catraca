"""Check-in na página de gestão (F05).

`organizador_requerido` é o decorador mais externo. A view só chama o domínio
(`evento_do_organizador` e `fazer_check_in`) e traduz `EventoNaoEncontrado` (inexistente ou de
outro organizador, R13) em 404 genérico, sem efeito. O resultado volta na própria resposta do
POST: a gestão inteira, com a mensagem de R10 em `#check-in-mensagem`.
"""

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_POST

from dominio.excecoes import EventoNaoEncontrado
from dominio.servicos.checkin import fazer_check_in
from dominio.servicos.eventos import evento_do_organizador
from web.acesso import organizador_requerido


@organizador_requerido
@require_POST
def check_in(request, evento_id):
    try:
        evento = evento_do_organizador(request.user, evento_id)
        resultado = fazer_check_in(request.user, evento_id, request.POST.get("codigo", ""))
    except EventoNaoEncontrado as erro:
        raise Http404 from erro
    contexto = {"evento": evento, "check_in_resultado": resultado}
    return render(request, "web/organizador/gestao.html", contexto)
