import json
from datetime import timedelta

import pytest
from django.utils import timezone

from dominio.models import Evento, Usuario
from dominio.servicos import eventos

CHAVE = "chave-de-teste-da-api"
CARTAO = "4000000000000001"
URL_EVENTOS = "/api/partner/events"


def url_compra(evento_id):
    return f"/api/partner/events/{evento_id}/purchases"


def url_ingresso(ticket_id):
    return f"/api/partner/tickets/{ticket_id}"


def futuro(dias=30, hora="21:00") -> str:
    dia = timezone.localtime(timezone.now() + timedelta(days=dias)).date()
    return f"{dia.isoformat()}T{hora}"


def dados_evento(**extra):
    dados = {
        "nome": "Jazz no Porão",
        "inicio": futuro(),
        "local": "Bar do Porão",
        "lotacao": "2",
        "preco": "100,00",
    }
    dados.update(extra)
    return dados


def rascunho(organizador, **extra) -> Evento:
    return eventos.criar_evento(organizador, dados_evento(**extra))


def publicado(organizador, **extra) -> Evento:
    return eventos.publicar_evento(organizador, rascunho(organizador, **extra).id_publico)


def cancelar_no_banco(evento) -> None:
    """Simula o cancelamento (F07) só para os testes."""
    Evento.objects.filter(pk=evento.pk).update(status=Evento.Status.CANCELADO)


def corpo_compra(email="ana@example.com", cartao=CARTAO):
    return {"buyerEmail": email, "cardNumber": cartao}


@pytest.fixture(autouse=True)
def _chave_de_teste(settings):
    settings.CATRACA_CHAVE_PARCEIRO = CHAVE


@pytest.fixture
def organizador(db):
    return Usuario.objects.create_user(
        "org.api@example.com", "x" * 10, nome="Org API", papel=Usuario.Papel.ORGANIZADOR
    )


@pytest.fixture
def participante(db):
    return Usuario.objects.create_user("part.api@example.com", "x" * 10, nome="Part API")


class Api:
    """Client do Django com a chave de parceiro; `chave=None` não manda o cabeçalho."""

    def __init__(self, client):
        self.client = client

    @staticmethod
    def _extra(chave):
        return {} if chave is None else {"HTTP_X_API_KEY": chave}

    def get(self, url, chave=CHAVE):
        return self.client.get(url, **self._extra(chave))

    def post(self, url, corpo=None, chave=CHAVE):
        if corpo is None:
            corpo = corpo_compra()
        if not isinstance(corpo, str | bytes):
            corpo = json.dumps(corpo)
        return self.client.post(
            url, data=corpo, content_type="application/json", **self._extra(chave)
        )


@pytest.fixture
def api(client):
    return Api(client)
