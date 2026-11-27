import pytest
from django.test import Client

from api_parceiros.tests.conftest import (
    CHAVE,
    URL_EVENTOS,
    corpo_compra,
    publicado,
    url_compra,
    url_ingresso,
)
from dominio.models import CobrancaGateway, Ingresso

pytestmark = pytest.mark.django_db

UNAUTHORIZED = b'{"error":"unauthorized"}'


def _tres_rotas(api, evento_id, chave):
    return [
        api.get(URL_EVENTOS, chave=chave),
        api.post(url_compra(evento_id), corpo_compra(), chave=chave),
        api.get(url_ingresso("tkt_naoexiste"), chave=chave),
    ]


def _confere_401(respostas):
    for resposta in respostas:
        assert resposta.status_code == 401
        assert resposta.content == UNAUTHORIZED
        assert resposta["Content-Type"] == "application/json"


def test_sem_chave_responde_401_nas_tres_rotas(api, organizador):
    evento = publicado(organizador)
    _confere_401(_tres_rotas(api, evento.id_publico, None))
    assert Ingresso.objects.count() == 0


def test_chave_errada_responde_401_nas_tres_rotas(api, organizador):
    evento = publicado(organizador)
    for chave in ("errada", CHAVE + "x", CHAVE[:-1], CHAVE.upper(), " " + CHAVE):
        _confere_401(_tres_rotas(api, evento.id_publico, chave))
    assert Ingresso.objects.count() == 0


def test_chave_vazia_no_cabecalho_responde_401(api, organizador):
    evento = publicado(organizador)
    _confere_401(_tres_rotas(api, evento.id_publico, ""))


def test_configuracao_vazia_nunca_autentica(api, organizador, settings):
    evento = publicado(organizador)
    settings.CATRACA_CHAVE_PARCEIRO = ""
    for chave in (None, "", "qualquer"):
        _confere_401(_tres_rotas(api, evento.id_publico, chave))
    assert Ingresso.objects.count() == 0


def test_401_vem_antes_de_corpo_invalido_e_inexistentes(api):
    for chave in (None, "errada"):
        _confere_401(
            [
                api.post(url_compra("evt_zzzzzzzz"), "isto não é json", chave=chave),
                api.post(url_compra("evt_zzzzzzzz"), corpo_compra(cartao="123"), chave=chave),
                api.post(url_compra("evt_zzzzzzzz"), corpo_compra(), chave=chave),
                api.get(url_ingresso("tkt_naoexiste"), chave=chave),
                api.client.get(url_compra("evt_zzzzzzzz"), HTTP_X_API_KEY=chave or "x"),
            ]
        )
    assert Ingresso.objects.count() == 0
    assert CobrancaGateway.objects.count() == 0


def test_chave_certa_passa(api, organizador):
    evento = publicado(organizador)
    for resposta in _tres_rotas(api, evento.id_publico, CHAVE):
        assert resposta.status_code != 401


def test_comparacao_em_tempo_constante(api, monkeypatch):
    import api_parceiros.auth as auth

    chamadas = []
    original = auth.hmac.compare_digest

    def espiao(a, b):
        chamadas.append((a, b))
        return original(a, b)

    monkeypatch.setattr(auth.hmac, "compare_digest", espiao)
    assert api.get(URL_EVENTOS, chave="errada").status_code == 401
    assert api.get(URL_EVENTOS).status_code != 401
    assert chamadas == [(b"errada", CHAVE.encode()), (CHAVE.encode(), CHAVE.encode())]


def test_api_isenta_de_csrf_e_sem_cookie(organizador):
    evento = publicado(organizador)
    client = Client(enforce_csrf_checks=True)
    compra = client.post(
        url_compra(evento.id_publico),
        data=corpo_compra(),
        content_type="application/json",
        HTTP_X_API_KEY=CHAVE,
    )
    assert compra.status_code not in (401, 403)
    for resposta in (compra, client.get(URL_EVENTOS, HTTP_X_API_KEY=CHAVE)):
        assert not resposta.cookies
        assert "Set-Cookie" not in resposta


def test_metodo_errado_responde_405_depois_da_chave(api, client):
    assert client.post(URL_EVENTOS).status_code == 401
    resposta = client.post(URL_EVENTOS, HTTP_X_API_KEY=CHAVE)
    assert resposta.status_code == 405
    assert resposta.content == b'{"error":"method_not_allowed"}'
    assert resposta["Allow"] == "GET"
    resposta = client.get(url_compra("evt_zzzzzzzz"), HTTP_X_API_KEY=CHAVE)
    assert (resposta.status_code, resposta["Allow"]) == (405, "POST")
    resposta = client.delete(url_ingresso("tkt_naoexiste"), HTTP_X_API_KEY=CHAVE)
    assert (resposta.status_code, resposta["Allow"]) == (405, "GET")
