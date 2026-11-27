from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from dominio.models import Evento, Ingresso, Usuario
from dominio.servicos import compras, eventos
from dominio.servicos.cancelamento import cancelar_evento
from web.tests.conftest import SENHA

pytestmark = pytest.mark.django_db

MSG_CANCELADO = "Evento cancelado não pode ser alterado."


def _dados(**extra):
    dia = timezone.localtime(timezone.now() + timedelta(days=30)).date()
    dados = {
        "nome": "Show",
        "inicio": f"{dia}T21:00",
        "local": "Bar",
        "lotacao": "5",
        "preco": "50,00",
    }
    dados.update(extra)
    return dados


@pytest.fixture
def evento(organizador):
    criado = eventos.criar_evento(organizador, _dados())
    return eventos.publicar_evento(organizador, criado.id_publico)


def _url(evento, acao=""):
    return f"/organizador/eventos/{evento.id_publico}/{acao}"


def test_bloco_cancelar_so_em_publicado_com_confirmacao(client_organizador, organizador, evento):
    html = client_organizador.get(_url(evento)).content.decode()
    bloco = html.split('id="evento-cancelar"', 1)[1].split("</section>", 1)[0]
    assert 'id="form-cancelar"' in bloco
    assert f'action="{_url(evento, "cancelar/")}"' in bloco
    assert 'onsubmit="return confirm(' in bloco
    rascunho = eventos.criar_evento(organizador, _dados(nome="Rascunho"))
    html = client_organizador.get(_url(rascunho)).content.decode()
    assert 'id="form-cancelar"' not in html


def test_cancelar_pela_gestao(client_organizador, evento):
    ingresso = compras.comprar_ingresso(
        evento.id_publico, cartao="4000000000000001", email_comprador="a@example.com", canal="api"
    )
    Ingresso.objects.filter(pk=ingresso.pk).update(status="confirmed")
    assert client_organizador.get(_url(evento, "cancelar/")).status_code == 405
    resposta = client_organizador.post(_url(evento, "cancelar/"))
    assert (resposta.status_code, resposta["Location"]) == (302, _url(evento))
    evento.refresh_from_db()
    ingresso.refresh_from_db()
    assert (evento.status, ingresso.status) == ("cancelado", "refunded")
    assert "Evento cancelado." in client_organizador.get(_url(evento)).content.decode()
    assert Client().get(f"/eventos/{evento.id_publico}/").status_code == 404


def test_cancelar_rascunho_pela_tela_responde_409(client_organizador, organizador):
    rascunho = eventos.criar_evento(organizador, _dados())
    resposta = client_organizador.post(_url(rascunho, "cancelar/"))
    assert resposta.status_code == 409
    assert "Só evento publicado pode ser cancelado." in resposta.content.decode()
    rascunho.refresh_from_db()
    assert rascunho.status == "rascunho"


def test_outro_organizador_nao_cancela(evento):
    outro = Usuario.objects.create_user(
        "outro.cancela@example.com", SENHA, nome="Outro", papel=Usuario.Papel.ORGANIZADOR
    )
    cliente = Client()
    cliente.force_login(outro)
    resposta = cliente.post(_url(evento, "cancelar/"))
    assert resposta.status_code == 404
    assert "Show" not in resposta.content.decode().split("<main>", 1)[1]
    evento.refresh_from_db()
    assert evento.status == "publicado"


def test_visitante_e_participante_nao_cancelam(client_participante, evento):
    resposta = Client().post(_url(evento, "cancelar/"))
    assert (resposta.status_code, resposta["Location"]) == (302, "/contas/entrar/")
    assert client_participante.post(_url(evento, "cancelar/")).status_code == 403
    evento.refresh_from_db()
    assert evento.status == "publicado"


def test_gestao_de_cancelado_sem_editar_nem_publicar(client_organizador, organizador, evento):
    cancelar_evento(organizador, evento.id_publico)
    html = client_organizador.get(_url(evento)).content.decode()
    assert _url(evento, "editar/") not in html
    assert _url(evento, "publicar/") not in html
    assert 'id="form-cancelar"' not in html
    assert 'data-campo="status">Cancelado<' in html
    assert "Este evento foi cancelado." in html


def test_editar_e_publicar_cancelado_respondem_409(client_organizador, organizador, evento):
    cancelar_evento(organizador, evento.id_publico)
    respostas = [
        client_organizador.get(_url(evento, "editar/")),
        client_organizador.post(_url(evento, "editar/"), _dados(nome="Ressuscitado")),
        client_organizador.post(_url(evento, "publicar/")),
    ]
    for resposta in respostas:
        assert resposta.status_code == 409
        assert MSG_CANCELADO in resposta.content.decode()
    evento.refresh_from_db()
    assert (evento.nome, evento.status) == ("Show", Evento.Status.CANCELADO)


def test_lista_do_organizador_mostra_cancelado(client_organizador, organizador, evento):
    cancelar_evento(organizador, evento.id_publico)
    html = client_organizador.get("/organizador/").content.decode()
    assert f'data-evento="{evento.id_publico}" data-status="cancelado"' in html
    assert ">Cancelado<" in html
