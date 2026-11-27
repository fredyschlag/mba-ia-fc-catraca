"""Bloco #check-in na gestão e POST /organizador/eventos/<id>/check-in/ (F05)."""

import re
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from dominio.models import Evento, Ingresso, Usuario
from dominio.servicos import compras, eventos
from web.tests.conftest import SENHA

pytestmark = pytest.mark.django_db

MENSAGENS = [
    "Ingresso inválido para este evento",
    "Evento cancelado",
    "Ingresso não confirmado",
    "Ingresso já utilizado",
    "Entrada liberada",
]


def _futuro(dias=30):
    dia = timezone.localtime(timezone.now() + timedelta(days=dias)).date()
    return f"{dia.isoformat()}T21:00"


def _evento(organizador, nome="Show na Porta"):
    dados = {
        "nome": nome,
        "inicio": _futuro(),
        "local": "Bar",
        "lotacao": "10",
        "preco": "100,00",
    }
    criado = eventos.criar_evento(organizador, dados)
    return eventos.publicar_evento(organizador, criado.id_publico)


def _ingresso(evento, status="confirmed"):
    ingresso = compras.comprar_ingresso(
        evento.id_publico, cartao="4000000000000001", email_comprador="x@example.com", canal="api"
    )
    Ingresso.objects.filter(pk=ingresso.pk).update(status=status)
    ingresso.refresh_from_db()
    return ingresso


@pytest.fixture
def organizador_b(db):
    return Usuario.objects.create_user(
        "organizador.b.teste@example.com", SENHA, nome="Bia B", papel=Usuario.Papel.ORGANIZADOR
    )


def _url(evento_id):
    return f"/organizador/eventos/{evento_id}/check-in/"


def _bloco(html):
    return html.split('<section id="check-in">', 1)[1].split("</section>", 1)[0]


def _mensagem(resposta):
    achadas = re.findall(r'<p id="check-in-mensagem">([^<]*)</p>', resposta.content.decode())
    assert len(achadas) == 1, achadas
    return achadas[0]


def _check_in(cliente, evento, codigo):
    resposta = cliente.post(_url(evento.id_publico), {"codigo": codigo})
    assert resposta.status_code == 200
    return _mensagem(resposta)


def test_gestao_do_dono_mostra_bloco_check_in(organizador):
    evento = _evento(organizador)
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(organizador)

    resposta = cliente.get(f"/organizador/eventos/{evento.id_publico}/")

    assert resposta.status_code == 200
    html = resposta.content.decode()
    bloco = _bloco(html)
    acao = f'action="/organizador/eventos/{evento.id_publico}/check-in/"'
    assert '<form id="form-check-in" method="post" ' + acao + ">" in bloco
    assert 'name="codigo"' in bloco
    assert 'name="csrfmiddlewaretoken"' in bloco
    assert "Código do ingresso" in bloco
    assert 'id="check-in-mensagem"' not in html


def test_check_in_pela_tela_mostra_cada_mensagem(client_organizador, organizador):
    evento = _evento(organizador)
    confirmado = _ingresso(evento)
    pendente = _ingresso(evento, status="pending")
    recusado = _ingresso(evento, status="declined")
    de_outro = _ingresso(_evento(organizador, nome="Outro"))

    assert _check_in(client_organizador, evento, "ZZZZZZZZ") == MENSAGENS[0]
    assert _check_in(client_organizador, evento, de_outro.codigo) == MENSAGENS[0]
    assert _check_in(client_organizador, evento, pendente.codigo) == MENSAGENS[2]
    assert _check_in(client_organizador, evento, recusado.codigo) == MENSAGENS[2]
    assert _check_in(client_organizador, evento, confirmado.codigo) == MENSAGENS[4]
    assert _check_in(client_organizador, evento, confirmado.codigo) == MENSAGENS[3]

    confirmado.refresh_from_db()
    assert confirmado.status == "confirmed" and confirmado.check_in_em is not None
    assert Ingresso.objects.filter(check_in_em__isnull=False).count() == 1


def test_check_in_pela_tela_normaliza_o_codigo(client_organizador, organizador):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)

    assert _check_in(client_organizador, evento, f"  {ingresso.codigo.lower()}  ") == MENSAGENS[4]
    assert _check_in(client_organizador, evento, f" {ingresso.codigo}") == MENSAGENS[3]


def test_check_in_de_outro_organizador_responde_404_sem_efeito(client, organizador, organizador_b):
    evento = _evento(organizador, nome="Evento Secreto de A")
    ingresso = _ingresso(evento)
    client.force_login(organizador_b)

    for alvo in (evento.id_publico, "evt_zzzzzzzz"):
        resposta = client.post(_url(alvo), {"codigo": ingresso.codigo})
        html = resposta.content.decode()
        assert resposta.status_code == 404
        assert "Página não encontrada" in html
        assert "check-in" not in html
        assert "Evento Secreto de A" not in html
        assert ingresso.codigo not in html
        assert not [m for m in MENSAGENS if m in html]

    ingresso.refresh_from_db()
    assert ingresso.check_in_em is None


def test_check_in_de_visitante_e_participante_e_barrado_sem_efeito(
    client, organizador, participante
):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)

    visitante = Client().post(_url(evento.id_publico), {"codigo": ingresso.codigo})
    assert visitante.status_code == 302
    assert visitante["Location"] == "/contas/entrar/"

    client.force_login(participante)
    barrado = client.post(_url(evento.id_publico), {"codigo": ingresso.codigo})
    assert barrado.status_code == 403
    assert not [m for m in MENSAGENS if m in barrado.content.decode()]
    assert client.get(_url(evento.id_publico)).status_code == 403

    ingresso.refresh_from_db()
    assert ingresso.check_in_em is None


def test_check_in_por_get_responde_405(client_organizador, organizador):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)

    resposta = client_organizador.get(_url(evento.id_publico), {"codigo": ingresso.codigo})

    assert resposta.status_code == 405
    ingresso.refresh_from_db()
    assert ingresso.check_in_em is None


def test_evento_cancelado_mantem_o_campo_e_responde_evento_cancelado(
    client_organizador, organizador, organizador_b
):
    evento = _evento(organizador)
    confirmado = _ingresso(evento)
    pendente = _ingresso(evento, status="pending")
    de_b = _ingresso(_evento(organizador_b, nome="De B"))
    Evento.objects.filter(pk=evento.pk).update(status=Evento.Status.CANCELADO)

    gestao = client_organizador.get(f"/organizador/eventos/{evento.id_publico}/")
    bloco = _bloco(gestao.content.decode())
    assert 'id="form-check-in"' in bloco and 'name="codigo"' in bloco

    assert _check_in(client_organizador, evento, confirmado.codigo) == MENSAGENS[1]
    assert _check_in(client_organizador, evento, pendente.codigo) == MENSAGENS[1]
    assert _check_in(client_organizador, evento, de_b.codigo) == MENSAGENS[0]
    assert _check_in(client_organizador, evento, "ZZZZZZZZ") == MENSAGENS[0]
    assert not Ingresso.objects.filter(check_in_em__isnull=False).exists()


def test_resposta_do_check_in_e_a_gestao_inteira(client_organizador, organizador):
    evento = _evento(organizador, nome="Gestão Completa")
    ingresso = _ingresso(evento)

    resposta = client_organizador.post(_url(evento.id_publico), {"codigo": ingresso.codigo})

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Location" not in resposta
    assert 'id="evento-dados"' in html and "Gestão Completa" in html
    assert 'id="painel"' in html and 'id="evento-cancelar"' in html
    assert _mensagem(resposta) == "Entrada liberada"
    campo = re.search(r'<input id="campo-codigo"[^>]*>', html).group(0)
    assert "value=" not in campo
    assert ingresso.codigo not in html
    assert (
        'id="check-in-mensagem"'
        not in client_organizador.get(f"/organizador/eventos/{evento.id_publico}/").content.decode()
    )
