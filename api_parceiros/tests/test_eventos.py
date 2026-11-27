import json
import re

import pytest

from api_parceiros.tests.conftest import (
    URL_EVENTOS,
    cancelar_no_banco,
    futuro,
    publicado,
    rascunho,
)
from dominio.models import Ingresso
from dominio.servicos import compras
from dominio.servicos.gateway import aplicar_resposta_gateway

pytestmark = pytest.mark.django_db


def _lista(api):
    resposta = api.get(URL_EVENTOS)
    assert resposta.status_code == 200
    return json.loads(resposta.content)


def _comprar(evento, cartao="4000000000000001"):
    return compras.comprar_ingresso(
        evento.id_publico, cartao=cartao, email_comprador="x@example.com", canal="api"
    )


def test_lista_vazia(api, organizador):
    rascunho(organizador)
    resposta = api.get(URL_EVENTOS)
    assert resposta.status_code == 200
    assert resposta.content == b"[]"


def test_lista_so_publicados_na_ordem_do_inicio(api, organizador):
    depois = publicado(organizador, nome="Depois", inicio=futuro(dias=60))
    antes = publicado(organizador, nome="Antes", inicio=futuro(dias=10))
    rascunho(organizador, nome="Rascunho", inicio=futuro(dias=5))
    assert [e["id"] for e in _lista(api)] == [antes.id_publico, depois.id_publico]


def test_evento_tem_exatamente_os_cinco_campos(api, organizador):
    evento = publicado(organizador, preco="100,00", lotacao="2")
    (item,) = _lista(api)
    assert list(item) == ["id", "name", "startsAt", "priceCents", "availableSeats"]
    assert item["id"] == evento.id_publico and re.fullmatch(r"evt_[a-z0-9]{8}", item["id"])
    assert item["name"] == "Jazz no Porão"
    assert item["priceCents"] == 10000 and type(item["priceCents"]) is int
    assert item["availableSeats"] == 2 and type(item["availableSeats"]) is int


def test_starts_at_iso_com_offset_de_sao_paulo(api, organizador):
    inicio = futuro(dias=45, hora="21:00")
    publicado(organizador, inicio=inicio)
    (item,) = _lista(api)
    assert item["startsAt"] == f"{inicio}:00-03:00"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", item["startsAt"])


def test_available_seats_igual_a_vagas_disponiveis(api, organizador):
    evento = publicado(organizador, lotacao="3")
    assert _lista(api)[0]["availableSeats"] == 3
    pendente = _comprar(evento)
    assert _lista(api)[0]["availableSeats"] == 2
    _comprar(evento)
    assert _lista(api)[0]["availableSeats"] == 1
    aplicar_resposta_gateway(pendente.pk, aprovado=False)
    assert Ingresso.objects.get(pk=pendente.pk).status == Ingresso.Status.RECUSADO
    assert _lista(api)[0]["availableSeats"] == 2 == compras.vagas_disponiveis(evento)


def test_rascunho_e_cancelado_ficam_fora(api, organizador):
    a_venda = publicado(organizador, nome="À venda")
    cancelado = publicado(organizador, nome="Cancelado")
    _comprar(cancelado)
    cancelar_no_banco(cancelado)
    rascunho(organizador, nome="Rascunho")
    assert [e["id"] for e in _lista(api)] == [a_venda.id_publico]


def test_json_compacto_e_content_type(api, organizador):
    evento = publicado(organizador, inicio=futuro(dias=45, hora="20:30"), preco="50,00")
    resposta = api.get(URL_EVENTOS)
    assert resposta["Content-Type"] == "application/json"
    inicio = futuro(dias=45, hora="20:30")
    esperado = (
        f'[{{"id":"{evento.id_publico}","name":"Jazz no Porão","startsAt":"{inicio}:00-03:00",'
        f'"priceCents":5000,"availableSeats":2}}]'
    )
    assert resposta.content.decode("utf-8") == esperado
