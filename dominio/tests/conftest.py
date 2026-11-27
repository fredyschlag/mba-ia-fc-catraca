from datetime import timedelta

import pytest
from django.utils import timezone

from dominio.models import Usuario


def futuro(dias=30, hora="21:00") -> str:
    """Data e hora local no futuro, no formato do <input type="datetime-local">."""
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


@pytest.fixture
def organizador(db):
    return Usuario.objects.create_user(
        "org.teste.a@example.com", "x" * 10, nome="Org A", papel=Usuario.Papel.ORGANIZADOR
    )


@pytest.fixture
def organizador_b(db):
    return Usuario.objects.create_user(
        "org.teste.b@example.com", "x" * 10, nome="Org B", papel=Usuario.Papel.ORGANIZADOR
    )


@pytest.fixture
def participante(db):
    return Usuario.objects.create_user("part.teste@example.com", "x" * 10, nome="Part")
