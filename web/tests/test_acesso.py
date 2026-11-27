import re
import uuid

import pytest
from django.test import Client, RequestFactory
from django.urls import get_resolver
from django.urls.resolvers import RoutePattern, URLResolver

from web.acesso import destino_depois_de_entrar
from web.tests import urls_de_teste

pytestmark = pytest.mark.django_db

LOGIN = "/contas/entrar/"


@pytest.fixture
def urls_com_views_de_teste(settings):
    settings.ROOT_URLCONF = "web.tests.urls_de_teste"
    urls_de_teste.CHAMADAS.clear()
    return urls_de_teste.CHAMADAS


def _cliente(usuario=None):
    cliente = Client()
    if usuario is not None:
        cliente.force_login(usuario)
    return cliente


def test_organizador_requerido_por_papel(urls_com_views_de_teste, participante, organizador):
    visitante = _cliente().get("/teste/organizador/?x=1")
    assert visitante.status_code == 302
    assert visitante["Location"] == "/contas/entrar/?next=/teste/organizador/%3Fx%3D1"

    barrado = _cliente(participante).get("/teste/organizador/")
    assert barrado.status_code == 403
    assert b"Acesso negado" in barrado.content
    assert b"area-do-organizador" not in barrado.content

    liberado = _cliente(organizador).get("/teste/organizador/")
    assert liberado.status_code == 200
    assert liberado.content == b"area-do-organizador"
    assert urls_com_views_de_teste == [("organizador", "GET")]


def test_participante_requerido_por_papel(urls_com_views_de_teste, participante, organizador):
    visitante = _cliente().get("/teste/participante/")
    assert visitante.status_code == 302
    assert visitante["Location"] == "/contas/entrar/?next=/teste/participante/"

    barrado = _cliente(organizador).get("/teste/participante/")
    assert barrado.status_code == 403
    assert b"Acesso negado" in barrado.content

    liberado = _cliente(participante).get("/teste/participante/")
    assert liberado.status_code == 200
    assert liberado.content == b"area-do-participante"
    assert urls_com_views_de_teste == [("participante", "GET")]


@pytest.mark.parametrize("caminho", ["/teste/organizador/", "/teste/participante/"])
@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
def test_guardas_em_post_de_visitante_nao_executam_a_view(urls_com_views_de_teste, caminho, metodo):
    resposta = getattr(_cliente(), metodo)(caminho)

    assert resposta.status_code == 302
    assert resposta["Location"] == LOGIN
    assert urls_com_views_de_teste == []


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("/organizador/", "/organizador/"),
        ("/eventos/evt_ab12cd34/", "/eventos/evt_ab12cd34/"),
        ("/organizador/?aba=painel", "/organizador/?aba=painel"),
        ("https://evil.example/", None),
        ("http://localhost:8000/organizador/", None),
        ("//evil.example/", None),
        ("/\\evil.example", None),
        ("javascript:alert(1)", None),
        ("organizador/", None),
        ("/organizador/\n", None),
        ("", None),
        (None, None),
    ],
)
def test_destino_depois_de_entrar(participante, organizador, valor, esperado):
    fabrica = RequestFactory()
    dados = {} if valor is None else {"next": valor}

    for usuario, padrao in ((participante, "/"), (organizador, "/organizador/")):
        para_post = fabrica.post(LOGIN, dados)
        para_get = fabrica.get(LOGIN, dados)
        assert destino_depois_de_entrar(para_post, usuario) == (esperado or padrao)
        assert destino_depois_de_entrar(para_get, usuario) == (esperado or padrao)


# --- /organizador/ e #usuario-logado ---------------------------------------------------


def _bloco_usuario(resposta):
    html = resposta.content.decode()
    return html.split('id="usuario-logado"', 1)[1].split("</nav>", 1)[0]


def test_area_do_organizador_por_papel(participante, organizador):
    visitante = _cliente().get("/organizador/")
    assert visitante.status_code == 302
    assert visitante["Location"] == "/contas/entrar/?next=/organizador/"

    barrado = _cliente(participante).get("/organizador/")
    assert barrado.status_code == 403
    assert b"Acesso negado" in barrado.content
    assert b"Meus eventos" not in barrado.content

    liberado = _cliente(organizador).get("/organizador/")
    assert liberado.status_code == 200
    assert b'id="meus-eventos"' in liberado.content
    assert b"Meus eventos" in liberado.content


def test_usuario_logado_por_papel(participante, organizador):
    visitante = _bloco_usuario(_cliente().get("/"))
    assert 'href="/contas/entrar/"' in visitante
    assert "Entrar" in visitante
    assert 'href="/contas/cadastro/"' in visitante
    assert "Criar conta" in visitante
    assert "Sair" not in visitante

    do_participante = _bloco_usuario(_cliente(participante).get("/"))
    assert "Paula Participante" in do_participante
    assert '<a href="/meus-ingressos/">Meus ingressos</a>' in do_participante
    assert 'action="/contas/sair/"' in do_participante
    assert "csrfmiddlewaretoken" in do_participante
    assert "Sair" in do_participante
    assert "Área do organizador" not in do_participante

    do_organizador = _bloco_usuario(_cliente(organizador).get("/organizador/"))
    assert "Otávio Organizador" in do_organizador
    assert '<a href="/organizador/">Área do organizador</a>' in do_organizador
    assert "Sair" in do_organizador
    assert "Meus ingressos" not in do_organizador


def test_usuario_logado_escapa_o_nome(participante):
    participante.nome = "<script>alert(1)</script>"
    participante.save()

    bloco = _bloco_usuario(_cliente(participante).get("/"))

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in bloco
    assert "<script>" not in bloco


# --- todas as rotas sob /organizador/ ---------------------------------------------------

_VALORES_FICTICIOS = {
    "IntConverter": 999999,
    "StringConverter": "inexistente",
    "SlugConverter": "inexistente",
    "PathConverter": "inexistente",
    "UUIDConverter": uuid.UUID("00000000-0000-4000-8000-000000000000"),
}


def _rotas(padroes, prefixo=""):
    """(rota completa, padrão) de cada URLPattern, entrando nos include()."""
    for padrao in padroes:
        rota = prefixo + str(padrao.pattern)
        if isinstance(padrao, URLResolver):
            yield from _rotas(padrao.url_patterns, rota)
        else:
            yield rota, padrao


def _urls_do_organizador():
    urls = []
    for rota, padrao in _rotas(get_resolver().url_patterns):
        if not rota.startswith("organizador/"):
            continue
        assert isinstance(padrao.pattern, RoutePattern), (
            f"use path() nas rotas do organizador: {rota}"
        )

        def preencher(achado, conversores=padrao.pattern.converters):
            conversor = conversores[achado.group("nome")]
            valor = _VALORES_FICTICIOS[type(conversor).__name__]
            return conversor.to_url(valor)

        urls.append("/" + re.sub(r"<(?:\w+:)?(?P<nome>\w+)>", preencher, rota))
    return urls


def test_rotas_do_organizador_barram_visitante_e_participante(participante):
    urls = _urls_do_organizador()
    assert "/organizador/" in urls

    for url in urls:
        for metodo in ("get", "post"):
            resposta = getattr(_cliente(), metodo)(url)
            assert resposta.status_code == 302, f"visitante {metodo.upper()} {url}"
            assert resposta["Location"].startswith(LOGIN), f"visitante {metodo.upper()} {url}"

            resposta = getattr(_cliente(participante), metodo)(url)
            assert resposta.status_code == 403, f"participante {metodo.upper()} {url}"
