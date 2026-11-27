import json
import re

import pytest
from django.test import Client

from api_parceiros.tests.conftest import (
    URL_EVENTOS,
    cancelar_no_banco,
    corpo_compra,
    publicado,
    rascunho,
    url_compra,
)
from dominio.models import CobrancaGateway, Ingresso, Usuario

pytestmark = pytest.mark.django_db

INVALID = b'{"error":"invalid_request"}'
NOT_AVAILABLE = b'{"error":"event_not_available"}'
SOLD_OUT = b'{"error":"sold_out"}'

CORPOS_INVALIDOS = [
    "isto não é json",
    "",
    "[]",
    '"texto"',
    "null",
    "{}",
    '{"cardNumber":"4000000000000001"}',
    '{"buyerEmail":"ana@example.com"}',
    '{"buyerEmail":"ana@example.com","cardNumber":4000000000000001}',
    '{"buyerEmail":123,"cardNumber":"4000000000000001"}',
    '{"buyerEmail":null,"cardNumber":"4000000000000001"}',
    '{"buyerEmail":"ana-sem-arroba","cardNumber":"4000000000000001"}',
    '{"buyerEmail":"ana@","cardNumber":"4000000000000001"}',
    '{"buyerEmail":"","cardNumber":"4000000000000001"}',
    '{"buyerEmail":"ana@example.com","cardNumber":"123"}',
    '{"buyerEmail":"ana@example.com","cardNumber":"400000000000000A"}',
    '{"buyerEmail":"ana@example.com","cardNumber":"40000000000000011"}',
    '{"buyerEmail":"ana@example.com","cardNumber":""}',
    b"\xff\xfe",
]


def _nada_criado():
    assert Ingresso.objects.count() == 0
    assert CobrancaGateway.objects.count() == 0


def test_compra_responde_202_pendente_com_tres_campos(api, organizador):
    evento = publicado(organizador)
    resposta = api.post(url_compra(evento.id_publico), corpo_compra())
    assert resposta.status_code == 202
    assert resposta["Content-Type"] == "application/json"
    dados = json.loads(resposta.content)
    assert list(dados) == ["ticketId", "code", "status"]
    assert dados["status"] == "pending"
    assert re.fullmatch(r"tkt_[a-z0-9]{8}", dados["ticketId"])
    assert re.fullmatch(r"[A-Z0-9]{8}", dados["code"])
    assert resposta.content.decode() == (
        f'{{"ticketId":"{dados["ticketId"]}","code":"{dados["code"]}","status":"pending"}}'
    )


def test_compra_grava_canal_api_sem_comprador(api, organizador):
    evento = publicado(organizador, preco="100,00")
    resposta = api.post(url_compra(evento.id_publico), corpo_compra(email=" Ana@Example.com "))
    dados = json.loads(resposta.content)
    ingresso = Ingresso.objects.get(id_publico=dados["ticketId"])
    assert ingresso.codigo == dados["code"]
    assert ingresso.evento_id == evento.pk
    assert ingresso.canal == Ingresso.Canal.API
    assert ingresso.comprador is None
    assert ingresso.email_comprador == "ana@example.com"
    assert ingresso.status == Ingresso.Status.PENDENTE
    assert ingresso.valor_centavos == 10000
    assert ingresso.cartao_final == "0001"
    assert ingresso.cobranca.processada_em is None
    assert not Usuario.objects.filter(email="ana@example.com").exists()


@pytest.mark.parametrize("corpo", CORPOS_INVALIDOS)
def test_corpo_invalido_responde_422_sem_criar(api, organizador, corpo):
    evento = publicado(organizador)
    resposta = api.post(url_compra(evento.id_publico), corpo)
    assert resposta.status_code == 422
    assert resposta.content == INVALID
    _nada_criado()


def test_422_antes_de_404(api, organizador):
    rascunho_ = rascunho(organizador)
    cancelado = publicado(organizador, lotacao="1")
    api.post(url_compra(cancelado.id_publico), corpo_compra())
    cancelar_no_banco(cancelado)
    lotado = publicado(organizador, lotacao="1")
    api.post(url_compra(lotado.id_publico), corpo_compra())
    antes = Ingresso.objects.count()
    for evento_id in (
        "evt_zzzzzzzz",
        rascunho_.id_publico,
        cancelado.id_publico,
        lotado.id_publico,
    ):
        for corpo in ("nada", corpo_compra(cartao="123"), corpo_compra(email="ana@")):
            resposta = api.post(url_compra(evento_id), corpo)
            assert (resposta.status_code, resposta.content) == (422, INVALID)
    assert Ingresso.objects.count() == antes


@pytest.mark.parametrize("situacao", ["inexistente", "rascunho", "cancelado"])
def test_evento_indisponivel_responde_404(api, organizador, situacao):
    if situacao == "inexistente":
        evento_id = "evt_zzzzzzzz"
    elif situacao == "rascunho":
        evento_id = rascunho(organizador).id_publico
    else:
        evento = publicado(organizador)
        cancelar_no_banco(evento)
        evento_id = evento.id_publico
    resposta = api.post(url_compra(evento_id), corpo_compra())
    assert (resposta.status_code, resposta.content) == (404, NOT_AVAILABLE)
    _nada_criado()


def test_cancelado_lotado_responde_404_e_nao_409(api, organizador):
    evento = publicado(organizador, lotacao="1")
    assert api.post(url_compra(evento.id_publico), corpo_compra()).status_code == 202
    assert api.post(url_compra(evento.id_publico), corpo_compra()).content == SOLD_OUT
    cancelar_no_banco(evento)
    resposta = api.post(url_compra(evento.id_publico), corpo_compra())
    assert (resposta.status_code, resposta.content) == (404, NOT_AVAILABLE)
    assert Ingresso.objects.count() == 1


def test_sem_vaga_responde_409_sem_criar(api, organizador):
    evento = publicado(organizador, lotacao="2")
    for cartao in ("4000000000000001", "4000000000000004"):
        assert (
            api.post(url_compra(evento.id_publico), corpo_compra(cartao=cartao)).status_code == 202
        )
    resposta = api.post(url_compra(evento.id_publico), corpo_compra())
    assert (resposta.status_code, resposta.content) == (409, SOLD_OUT)
    assert resposta["Content-Type"] == "application/json"
    assert Ingresso.objects.count() == 2
    assert CobrancaGateway.objects.count() == 2
    assert json.loads(api.get(URL_EVENTOS).content)[0]["availableSeats"] == 0


def test_compra_da_api_esgota_a_vitrine(api, organizador, participante):
    evento = publicado(organizador, lotacao="1")
    assert api.post(url_compra(evento.id_publico), corpo_compra()).status_code == 202
    vitrine = Client()
    vitrine.force_login(participante)
    detalhe = vitrine.get(f"/eventos/{evento.id_publico}/").content.decode()
    assert '<p id="esgotado">Ingressos esgotados</p>' in detalhe
    assert 'id="form-compra"' not in detalhe
    resposta = vitrine.post(
        f"/eventos/{evento.id_publico}/comprar/", {"cartao": "4000000000000001"}
    )
    assert resposta.status_code == 200
    assert 'id="erro-compra">Ingressos esgotados<' in resposta.content.decode()
    assert Ingresso.objects.count() == 1


def test_compra_da_vitrine_esgota_a_api(api, organizador, participante):
    evento = publicado(organizador, lotacao="1")
    vitrine = Client()
    vitrine.force_login(participante)
    resposta = vitrine.post(
        f"/eventos/{evento.id_publico}/comprar/", {"cartao": "4000000000000001"}
    )
    assert resposta.status_code == 302
    resposta = api.post(url_compra(evento.id_publico), corpo_compra())
    assert (resposta.status_code, resposta.content) == (409, SOLD_OUT)
    assert Ingresso.objects.count() == 1
