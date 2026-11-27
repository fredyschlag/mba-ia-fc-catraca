import re

import pytest
from django.test import Client

from dominio.models import Usuario
from web.tests.conftest import SENHA

pytestmark = pytest.mark.django_db

CADASTRO = "/contas/cadastro/"
ENTRAR = "/contas/entrar/"
SAIR = "/contas/sair/"


def _cadastrar(cliente, **dados):
    base = {"nome": "Ana Teste", "email": "ana.teste@example.com", "senha": "Senha-F01-secreta"}
    base.update(dados)
    return cliente.post(CADASTRO, base)


def _sessao_ativa(cliente):
    return "_auth_user_id" in cliente.session


# --- falha de CSRF --------------------------------------------------------------------


def test_falha_de_csrf_usa_pagina_403_generica():
    resposta = Client(enforce_csrf_checks=True).post(SAIR)
    assert resposta.status_code == 403
    assert b"Acesso negado" in resposta.content
    assert b"CSRF" not in resposta.content


# --- cadastro -------------------------------------------------------------------------


def test_cadastro_get_mostra_campos(client):
    resposta = client.get(CADASTRO)
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert 'id="form-cadastro"' in html
    nomes = set(re.findall(r'name="(nome|email|senha|csrfmiddlewaretoken)"', html))
    assert nomes == {"nome", "email", "senha", "csrfmiddlewaretoken"}
    assert 'type="password"' in html
    assert "Criar conta" in html


def test_cadastro_valido_cria_participante_entra_e_vai_para_vitrine(client):
    resposta = _cadastrar(client, email="  Ana.Teste@Example.COM ")

    assert resposta.status_code == 302
    assert resposta["Location"] == "/"
    usuario = Usuario.objects.get()
    assert usuario.email == "ana.teste@example.com"
    assert usuario.papel == Usuario.Papel.PARTICIPANTE
    assert usuario.password.startswith("pbkdf2_sha256$") or usuario.password.startswith("md5$")
    assert "Senha-F01-secreta" not in usuario.password
    assert _sessao_ativa(client)

    vitrine = client.get("/").content.decode()
    bloco = vitrine.split('id="usuario-logado"', 1)[1].split("</nav>", 1)[0]
    assert "Ana Teste" in bloco


@pytest.mark.parametrize(
    ("dados", "mensagens"),
    [
        ({"email": "ANA.TESTE@example.com"}, ["Já existe uma conta com este e-mail."]),
        ({"email": "ana@"}, ["Informe um e-mail válido."]),
        ({"nome": "   "}, ["Informe o seu nome."]),
        ({"email": ""}, ["Informe o seu e-mail."]),
        ({"senha": ""}, ["Informe uma senha."]),
        ({"senha": "1234567"}, ["A senha precisa ter pelo menos 8 caracteres."]),
        (
            {"nome": "", "email": "", "senha": ""},
            ["Informe o seu nome.", "Informe o seu e-mail.", "Informe uma senha."],
        ),
    ],
)
def test_cadastro_invalido_reexibe_formulario_sem_criar_usuario(client, dados, mensagens):
    Usuario.objects.create_user("ana.teste@example.com", SENHA, nome="Ana Original")
    antes = Usuario.objects.count()

    resposta = _cadastrar(client, **dados)
    html = resposta.content.decode()

    assert resposta.status_code == 200
    for mensagem in mensagens:
        assert mensagem in html
    assert Usuario.objects.count() == antes
    assert not _sessao_ativa(client)
    senha_enviada = dados.get("senha", "Senha-F01-secreta")
    if senha_enviada:
        assert senha_enviada not in html


def test_cadastro_invalido_reexibe_nome_e_email(client):
    resposta = _cadastrar(client, nome="Caio", email="caio@example.com", senha="1234567")
    html = resposta.content.decode()

    assert 'value="Caio"' in html
    assert 'value="caio@example.com"' in html
    assert "1234567" not in html


def test_cadastro_ignora_papel_organizador_e_flags_de_equipe(client):
    resposta = _cadastrar(
        client,
        email="esperto@example.com",
        papel="organizador",
        is_staff="1",
        is_superuser="1",
    )

    assert resposta.status_code == 302
    usuario = Usuario.objects.get(email="esperto@example.com")
    assert usuario.papel == Usuario.Papel.PARTICIPANTE
    assert not usuario.is_staff
    assert not usuario.is_superuser
    assert client.get("/organizador/").status_code == 403


def test_cadastro_exige_csrf():
    cliente = Client(enforce_csrf_checks=True)
    resposta = _cadastrar(cliente)

    assert resposta.status_code == 403
    assert b"Acesso negado" in resposta.content
    assert Usuario.objects.count() == 0


def test_cadastro_respeita_next_interno(client):
    pagina = client.get(CADASTRO, {"next": "/eventos/evt_ab12cd34/"}).content.decode()
    assert 'name="next" value="/eventos/evt_ab12cd34/"' in pagina

    resposta = _cadastrar(client, next="/eventos/evt_ab12cd34/")
    assert resposta.status_code == 302
    assert resposta["Location"] == "/eventos/evt_ab12cd34/"

    outro = Client()
    resposta = _cadastrar(outro, email="outro@example.com", next="https://evil.example/")
    assert resposta["Location"] == "/"


# --- entrar ---------------------------------------------------------------------------


@pytest.mark.parametrize("em_maiusculas", [False, True])
def test_entrar_valido_leva_ao_destino_padrao_do_papel(participante, organizador, em_maiusculas):
    for usuario, destino in ((organizador, "/organizador/"), (participante, "/")):
        cliente = Client()
        endereco = usuario.email.upper() if em_maiusculas else usuario.email
        resposta = cliente.post(ENTRAR, {"email": endereco, "senha": SENHA})

        assert resposta.status_code == 302
        assert resposta["Location"] == destino
        assert cliente.session["_auth_user_id"] == str(usuario.pk)


def test_entrar_get_mostra_formulario(client):
    html = client.get(ENTRAR, {"next": "/organizador/"}).content.decode()

    assert 'id="form-entrar"' in html
    assert 'name="next" value="/organizador/"' in html
    assert 'type="password"' in html


@pytest.mark.parametrize(
    ("email", "senha"),
    [
        ("organizador.teste@example.com", "senha-errada"),
        ("ninguem@example.com", SENHA),
        ("inativo@example.com", SENHA),
        ("", ""),
        ("organizador.teste@example.com", ""),
    ],
)
def test_entrar_invalido_mostra_mensagem_sem_sessao(client, organizador, email, senha):
    Usuario.objects.create_user("inativo@example.com", SENHA, nome="Inativo", is_active=False)

    resposta = client.post(ENTRAR, {"email": email, "senha": senha})
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert '<p class="erro" id="erro-entrar">E-mail ou senha inválidos.</p>' in html
    assert not _sessao_ativa(client)
    assert "sessionid" not in resposta.cookies
    if senha:
        assert senha not in html


@pytest.mark.parametrize(
    ("valor", "destino"),
    [
        ("/organizador/", "/organizador/"),
        ("/eventos/evt_ab12cd34/", "/eventos/evt_ab12cd34/"),
        ("https://evil.example/", "/organizador/"),
        ("//evil.example/", "/organizador/"),
        ("/\\evil.example", "/organizador/"),
    ],
)
def test_entrar_respeita_next_interno_e_ignora_externo(organizador, valor, destino):
    resposta = Client().post(ENTRAR, {"email": organizador.email, "senha": SENHA, "next": valor})

    assert resposta.status_code == 302
    assert resposta["Location"] == destino


# --- sair -----------------------------------------------------------------------------


def test_sair_exige_post_e_csrf_e_encerra_sessao(organizador):
    cliente = Client(enforce_csrf_checks=True)
    pagina = cliente.get(ENTRAR)
    token = pagina.cookies["csrftoken"].value
    resposta = cliente.post(
        ENTRAR, {"email": organizador.email, "senha": SENHA, "csrfmiddlewaretoken": token}
    )
    assert resposta.status_code == 302
    sessao_antiga = cliente.cookies["sessionid"].value

    assert cliente.get(SAIR).status_code == 405
    assert cliente.get("/organizador/").status_code == 200

    assert cliente.post(SAIR).status_code == 403
    assert cliente.get("/organizador/").status_code == 200

    token = cliente.cookies["csrftoken"].value
    resposta = cliente.post(SAIR, {"csrfmiddlewaretoken": token})
    assert resposta.status_code == 302
    assert resposta["Location"] == "/"

    depois = cliente.get("/organizador/")
    assert depois.status_code == 302
    assert depois["Location"] == "/contas/entrar/?next=/organizador/"

    com_cookie_antigo = Client()
    com_cookie_antigo.cookies["sessionid"] = sessao_antiga
    reenvio = com_cookie_antigo.get("/organizador/")
    assert reenvio.status_code == 302
    assert reenvio["Location"] == "/contas/entrar/?next=/organizador/"


@pytest.mark.parametrize("caminho", [ENTRAR, CADASTRO])
def test_autenticado_em_entrar_ou_cadastro_vai_ao_destino_padrao(client_participante, caminho):
    antes = Usuario.objects.count()

    assert client_participante.get(caminho)["Location"] == "/"
    resposta = client_participante.post(
        caminho, {"nome": "Outra", "email": "outra@example.com", "senha": SENHA}
    )
    assert resposta.status_code == 302
    assert resposta["Location"] == "/"
    assert Usuario.objects.count() == antes


def test_autenticado_organizador_em_entrar_vai_para_a_area(client_organizador):
    assert client_organizador.get(ENTRAR)["Location"] == "/organizador/"
