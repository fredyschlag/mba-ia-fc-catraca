"""Área do organizador (F01: guarda; F02: lista, novo, gestão, editar e publicar).

Toda view deste módulo usa `organizador_requerido` como decorador mais externo; o teste
`test_rotas_do_organizador_barram_visitante_e_participante` cobra isso de cada rota.
As views só chamam `dominio.servicos.eventos` e traduzem as exceções: `EventoNaoEncontrado`
(inexistente ou de outro organizador, R13) → 404 genérico; `ValidacaoError` → formulário com
as mensagens.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from dominio.excecoes import EventoNaoEncontrado, ValidacaoError
from dominio.servicos import eventos as servico
from web.acesso import organizador_requerido
from web.forms import EventoForm


def _gestao(evento):
    return redirect(f"/organizador/eventos/{evento.id_publico}/")


def _evento_ou_404(request, evento_id):
    try:
        return servico.evento_do_organizador(request.user, evento_id)
    except EventoNaoEncontrado as erro:
        raise Http404 from erro


def _valores_iniciais(evento):
    reais, centavos = divmod(evento.preco_centavos, 100)
    return {
        "nome": evento.nome,
        "inicio": timezone.localtime(evento.inicio).strftime("%Y-%m-%dT%H:%M"),
        "local": evento.local,
        "lotacao": str(evento.lotacao),
        "preco": f"{reais},{centavos:02d}",
    }


def _form_com_erros(form, erro):
    for campo, mensagens in erro.erros.items():
        for mensagem in mensagens:
            form.add_error(campo if campo in form.fields else None, mensagem)
    return form


@organizador_requerido
@require_GET
def inicio(request):
    eventos = servico.eventos_do_organizador(request.user)
    return render(request, "web/organizador/inicio.html", {"eventos": eventos})


@organizador_requerido
@require_http_methods(["GET", "POST"])
def novo(request):
    if request.method == "GET":
        return render(request, "web/organizador/form_evento.html", {"form": EventoForm()})
    form = EventoForm(request.POST)
    form.is_valid()
    try:
        evento = servico.criar_evento(request.user, form.cleaned_data)
    except ValidacaoError as erro:
        contexto = {"form": _form_com_erros(form, erro)}
        return render(request, "web/organizador/form_evento.html", contexto)
    messages.success(request, "Evento criado.")
    return _gestao(evento)


@organizador_requerido
@require_GET
def gestao(request, evento_id):
    evento = _evento_ou_404(request, evento_id)
    return render(request, "web/organizador/gestao.html", {"evento": evento})


@organizador_requerido
@require_http_methods(["GET", "POST"])
def editar(request, evento_id):
    evento = _evento_ou_404(request, evento_id)
    if request.method == "GET":
        form = EventoForm(initial=_valores_iniciais(evento))
        return render(request, "web/organizador/form_evento.html", {"form": form, "evento": evento})
    form = EventoForm(request.POST)
    form.is_valid()
    try:
        servico.editar_evento(request.user, evento_id, form.cleaned_data)
    except EventoNaoEncontrado as erro:
        raise Http404 from erro
    except ValidacaoError as erro:
        contexto = {"form": _form_com_erros(form, erro), "evento": evento}
        return render(request, "web/organizador/form_evento.html", contexto)
    messages.success(request, "Evento atualizado.")
    return _gestao(evento)


@organizador_requerido
@require_POST
def publicar(request, evento_id):
    try:
        evento = servico.publicar_evento(request.user, evento_id)
    except EventoNaoEncontrado as erro:
        raise Http404 from erro
    messages.success(request, "Evento publicado.")
    return _gestao(evento)
