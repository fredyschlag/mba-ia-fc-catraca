import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command

from dominio.models import Usuario
from dominio.seed import CONTAS_DEV, SENHA_DEV

pytestmark = pytest.mark.django_db

PAPEIS_ESPERADOS = {
    "org.a@catraca.test": "organizador",
    "org.b@catraca.test": "organizador",
    "participante@catraca.test": "participante",
}


def _confere_contas():
    assert Usuario.objects.count() == 3
    assert {u.email: u.papel for u in Usuario.objects.all()} == PAPEIS_ESPERADOS
    for conta in CONTAS_DEV:
        assert authenticate(username=conta["email"], password=SENHA_DEV) is not None


def test_seed_cria_as_tres_contas():
    call_command("seed")
    _confere_contas()


def test_seed_rodada_duas_vezes_nao_duplica_e_senhas_valem():
    call_command("seed")
    call_command("seed")
    _confere_contas()


def test_seed_redefine_senha_e_papel_alterados():
    call_command("seed")
    u = Usuario.objects.get(email="org.a@catraca.test")
    u.set_password("outra-senha")
    u.papel = "participante"
    u.save()

    call_command("seed")

    u.refresh_from_db()
    assert u.papel == "organizador"
    assert authenticate(username="org.a@catraca.test", password=SENHA_DEV) == u
