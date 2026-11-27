import pytest

pytestmark = pytest.mark.django_db


def test_saude_responde_200(client):
    resposta = client.get("/saude/")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_vitrine_responde_200(client):
    resposta = client.get("/")
    assert resposta.status_code == 200
    assert b'id="vitrine"' in resposta.content


def test_404_generico_sem_detalhes_de_debug(client, settings):
    settings.DEBUG = False
    resposta = client.get("/nao-existe/")
    assert resposta.status_code == 404
    assert "Página não encontrada".encode() in resposta.content
    assert b"urlpatterns" not in resposta.content
    assert b"Traceback" not in resposta.content
