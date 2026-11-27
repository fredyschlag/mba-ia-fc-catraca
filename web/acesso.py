"""Guardas de acesso e destino depois de entrar (F01).

As guardas são decoradores de view e devem ser sempre o decorador mais externo, para que
respondam antes de qualquer outro (inclusive `require_GET`/`require_POST`).
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

DESTINO_ORGANIZADOR = "/organizador/"
DESTINO_PARTICIPANTE = "/"

_METODOS_COM_NEXT = {"GET", "HEAD"}


def _mandar_para_o_login(request):
    """302 para o login; `next` só em GET/HEAD (voltar a um endereço só-POST daria 405)."""
    if request.method in _METODOS_COM_NEXT:
        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
    return redirect(settings.LOGIN_URL)


def _guarda(tem_acesso):
    def decorador(view):
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            usuario = request.user
            if not usuario.is_authenticated:
                return _mandar_para_o_login(request)
            if not tem_acesso(usuario):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return envolvida

    return decorador


organizador_requerido = _guarda(lambda usuario: usuario.eh_organizador)
organizador_requerido.__doc__ = (
    "Visitante → 302 para o login; autenticado sem papel organizador → 403 genérico."
)

participante_requerido = _guarda(lambda usuario: usuario.eh_participante)
participante_requerido.__doc__ = "Visitante → 302 para o login; organizador → 403 genérico."


def caminho_interno(valor) -> str | None:
    """Devolve `valor` se for um caminho interno seguro para redirecionar; senão None."""
    if not valor or not isinstance(valor, str):
        return None
    if not valor.startswith("/") or valor.startswith("//") or valor.startswith("/\\"):
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in valor):
        return None
    if not url_has_allowed_host_and_scheme(valor, allowed_hosts=set()):
        return None
    return valor


def destino_padrao(usuario) -> str:
    return DESTINO_ORGANIZADOR if usuario.eh_organizador else DESTINO_PARTICIPANTE


def next_da_requisicao(request) -> str | None:
    """O `next` aceito: do POST no envio do formulário, do GET na exibição."""
    dados = request.POST if request.method == "POST" else request.GET
    return caminho_interno(dados.get("next"))


def destino_depois_de_entrar(request, usuario) -> str:
    return next_da_requisicao(request) or destino_padrao(usuario)
