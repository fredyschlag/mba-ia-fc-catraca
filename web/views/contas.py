"""Telas de contas: cadastro de participante, entrar e sair (F01).

As views só chamam o domínio (`cadastrar_participante`) ou a autenticação do Django e
traduzem o resultado em resposta.
"""

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from dominio.excecoes import ValidacaoError
from dominio.servicos.contas import cadastrar_participante
from web.acesso import destino_depois_de_entrar, next_da_requisicao
from web.forms import CadastroForm, EntrarForm

MSG_CREDENCIAIS_INVALIDAS = "E-mail ou senha inválidos."


def _contexto(request, form, **extra):
    return {"form": form, "next": next_da_requisicao(request) or "", **extra}


@require_http_methods(["GET", "POST"])
def cadastro(request):
    if request.user.is_authenticated:
        return redirect(destino_depois_de_entrar(request, request.user))

    if request.method == "GET":
        return render(request, "web/contas/cadastro.html", _contexto(request, CadastroForm()))

    form = CadastroForm(request.POST)
    form.is_valid()  # sem validação própria; só popula cleaned_data
    dados = form.cleaned_data
    try:
        usuario = cadastrar_participante(dados["nome"], dados["email"], dados["senha"])
    except ValidacaoError as erro:
        for campo, mensagens in erro.erros.items():
            for mensagem in mensagens:
                form.add_error(campo, mensagem)
        return render(request, "web/contas/cadastro.html", _contexto(request, form))

    login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(destino_depois_de_entrar(request, usuario))


@require_http_methods(["GET", "POST"])
def entrar(request):
    if request.user.is_authenticated:
        return redirect(destino_depois_de_entrar(request, request.user))

    if request.method == "GET":
        return render(request, "web/contas/entrar.html", _contexto(request, EntrarForm()))

    form = EntrarForm(request.POST)
    form.is_valid()
    dados = form.cleaned_data
    usuario = None
    if dados["email"] and dados["senha"]:
        usuario = authenticate(request, username=dados["email"], password=dados["senha"])
    if usuario is None:
        contexto = _contexto(request, form, erro_entrar=MSG_CREDENCIAIS_INVALIDAS)
        return render(request, "web/contas/entrar.html", contexto)

    login(request, usuario)
    return redirect(destino_depois_de_entrar(request, usuario))


@require_POST
def sair(request):
    logout(request)
    return redirect("/")
