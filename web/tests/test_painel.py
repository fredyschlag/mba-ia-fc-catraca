import re
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from dominio.models import Ingresso, Usuario
from dominio.servicos import compras, eventos
from web.tests.conftest import SENHA

pytestmark = pytest.mark.django_db

ROTULOS = ["Confirmados", "Pendentes", "Check-ins", "Vagas disponíveis", "Receita", "Estornados"]
METRICAS = ["confirmados", "pendentes", "check-ins", "vagas-disponiveis", "receita", "estornados"]


def _dados(**extra):
    dia = timezone.localtime(timezone.now() + timedelta(days=30)).date()
    dados = {
        "nome": "Show",
        "inicio": f"{dia}T21:00",
        "local": "Bar",
        "lotacao": "3",
        "preco": "100,00",
    }
    dados.update(extra)
    return dados


@pytest.fixture
def evento(organizador):
    criado = eventos.criar_evento(organizador, _dados())
    return eventos.publicar_evento(organizador, criado.id_publico)


def _confirmado(evento):
    ingresso = compras.comprar_ingresso(
        evento.id_publico, cartao="4000000000000001", email_comprador="a@example.com", canal="api"
    )
    Ingresso.objects.filter(pk=ingresso.pk).update(status="confirmed")
    return ingresso


def _metricas(cliente, evento):
    html = cliente.get(f"/organizador/eventos/{evento.id_publico}/").content.decode()
    return dict(re.findall(r'data-metrica="([a-z-]+)">([^<]*)<', html))


def test_bloco_painel_na_gestao_com_rotulos_e_metricas(client_organizador, evento):
    html = client_organizador.get(f"/organizador/eventos/{evento.id_publico}/").content.decode()
    assert html.count('id="painel"') == 1
    for rotulo, metrica in zip(ROTULOS, METRICAS, strict=True):
        assert re.search(rf"<dt>{rotulo}</dt><dd data-metrica=\"{metrica}\">", html)
    assert _metricas(client_organizador, evento) == {
        "confirmados": "0",
        "pendentes": "0",
        "check-ins": "0",
        "vagas-disponiveis": "3",
        "receita": "R$ 0,00",
        "estornados": "0",
    }


def test_receita_no_formato_reais(client_organizador, organizador, evento):
    _confirmado(evento)
    _confirmado(evento)
    eventos.editar_evento(organizador, evento.id_publico, _dados(preco="150,00"))
    _confirmado(evento)
    assert _metricas(client_organizador, evento)["receita"] == "R$ 350,00"


def test_recarregar_mostra_estado_atual(client_organizador, evento):
    assert _metricas(client_organizador, evento)["pendentes"] == "0"
    ingresso = compras.comprar_ingresso(
        evento.id_publico, cartao="4000000000000004", email_comprador="a@example.com", canal="api"
    )
    assert _metricas(client_organizador, evento)["pendentes"] == "1"
    Ingresso.objects.filter(pk=ingresso.pk).update(status="declined")
    metricas = _metricas(client_organizador, evento)
    assert (metricas["pendentes"], metricas["vagas-disponiveis"]) == ("0", "3")


def test_outro_organizador_nao_ve_o_painel(evento):
    outro = Usuario.objects.create_user(
        "outro.org@example.com", SENHA, nome="Outro", papel=Usuario.Papel.ORGANIZADOR
    )
    _confirmado(evento)
    cliente = Client()
    cliente.force_login(outro)
    resposta = cliente.get(f"/organizador/eventos/{evento.id_publico}/")
    assert resposta.status_code == 404
    html = resposta.content.decode()
    assert 'id="painel"' not in html and "data-metrica" not in html
