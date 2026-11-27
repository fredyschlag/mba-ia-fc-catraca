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


def test_seed_rodada_de_novo_preserva_o_hash_das_senhas():
    call_command("seed")
    hashes = dict(Usuario.objects.values_list("email", "password"))

    call_command("seed")

    assert dict(Usuario.objects.values_list("email", "password")) == hashes
    _confere_contas()


def test_seed_restaura_a_senha_de_desenvolvimento_trocada():
    call_command("seed")
    u = Usuario.objects.get(email="participante@catraca.test")
    u.set_password("senha-trocada-1")
    u.save()
    hash_trocado = u.password
    assert authenticate(username=u.email, password=SENHA_DEV) is None

    call_command("seed")

    u.refresh_from_db()
    assert u.password != hash_trocado
    assert authenticate(username=u.email, password="catraca123") == u
    assert authenticate(username=u.email, password="senha-trocada-1") is None


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
