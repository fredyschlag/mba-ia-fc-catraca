import pytest

from dominio.models import Usuario

SENHA = "Senha-Teste-123"


@pytest.fixture
def participante(db):
    return Usuario.objects.create_user(
        "participante.teste@example.com", SENHA, nome="Paula Participante"
    )


@pytest.fixture
def organizador(db):
    return Usuario.objects.create_user(
        "organizador.teste@example.com",
        SENHA,
        nome="Otávio Organizador",
        papel=Usuario.Papel.ORGANIZADOR,
    )


@pytest.fixture
def client_participante(client, participante):
    client.force_login(participante)
    return client


@pytest.fixture
def client_organizador(client, organizador):
    client.force_login(organizador)
    return client
