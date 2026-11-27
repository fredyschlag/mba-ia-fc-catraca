import re
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from dominio.models import Evento, Usuario
from dominio.servicos import eventos as srv
from web.templatetags.catraca import reais
from web.tests.conftest import SENHA

pytestmark = pytest.mark.django_db

NOVO = "/organizador/eventos/novo/"


def _futuro(dias=30, hora="21:00"):
    dia = timezone.localtime(timezone.now() + timedelta(days=dias)).date()
    return f"{dia.isoformat()}T{hora}"


def _dados(**extra):
    dados = {
        "nome": "Jazz no Porão",
        "inicio": _futuro(),
        "local": "Bar do Porão",
        "lotacao": "2",
        "preco": "100,00",
    }
    dados.update(extra)
    return dados


def _gestao(evento):
    return f"/organizador/eventos/{evento.id_publico}/"


@pytest.fixture
def organizador_b(db):
    return Usuario.objects.create_user(
        "organizador.b@example.com", SENHA, nome="Bia B", papel=Usuario.Papel.ORGANIZADOR
    )


@pytest.fixture
def evento(organizador):
    return srv.criar_evento(organizador, _dados())


def _cliente(usuario=None):
    cliente = Client()
    if usuario is not None:
        cliente.force_login(usuario)
    return cliente


# --- formatação e vitrine ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("centavos", "texto"),
    [
        (10000, "R$ 100,00"),
        (35000, "R$ 350,00"),
        (12050, "R$ 120,50"),
        (0, "R$ 0,00"),
        (123456, "R$ 1.234,56"),
        (1, "R$ 0,01"),
    ],
)
def test_filtro_reais(centavos, texto):
    assert reais(centavos) == texto


def test_vitrine_lista_publicados_com_dados_e_link(organizador, evento):
    srv.publicar_evento(organizador, evento.id_publico)
    srv.criar_evento(organizador, _dados(nome="Rascunho escondido"))
    cedo = srv.criar_evento(organizador, _dados(nome="Antes", inicio=_futuro(5, "19:00")))
    srv.publicar_evento(organizador, cedo.id_publico)

    html = Client().get("/").content.decode()
    assert 'id="vitrine"' in html
    link = f'href="/eventos/{evento.id_publico}/"'
    for texto in ("Jazz no Porão", "Bar do Porão", "R$ 100,00", link):
        assert texto in html
    inicio = timezone.localtime(evento.inicio).strftime("%d/%m/%Y %H:%M")
    assert inicio in html
    assert "Rascunho escondido" not in html
    links = re.findall(r'href="/eventos/(evt_[a-z0-9]{8})/"', html)
    assert links == [cedo.id_publico, evento.id_publico]


def test_vitrine_vazia():
    html = Client().get("/").content.decode()
    assert "Nenhum evento à venda no momento." in html


def test_detalhe_de_publicado_tem_dados_e_slot_de_compra(organizador, evento):
    srv.publicar_evento(organizador, evento.id_publico)
    resposta = Client().get(f"/eventos/{evento.id_publico}/")
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Jazz no Porão" in html and "R$ 100,00" in html
    assert html.count('id="compra"') == 1


def test_detalhe_de_rascunho_ou_inexistente_responde_404(evento, participante):
    for cliente in (_cliente(), _cliente(participante)):
        resposta = cliente.get(f"/eventos/{evento.id_publico}/")
        assert resposta.status_code == 404
        assert "Jazz no Porão" not in resposta.content.decode()
    assert Client().get("/eventos/evt_naoexis/").status_code == 404
    Evento.objects.filter(pk=evento.pk).update(status=Evento.Status.CANCELADO)
    assert Client().get(f"/eventos/{evento.id_publico}/").status_code == 404


# --- área do organizador -----------------------------------------------------------------


def test_criar_evento_pela_tela_vai_para_gestao(client_organizador, organizador):
    form = client_organizador.get(NOVO).content.decode()
    for campo in ("nome", "inicio", "local", "lotacao", "preco"):
        assert f'name="{campo}"' in form
    assert 'type="datetime-local"' in form

    resposta = client_organizador.post(NOVO, _dados())
    evento = Evento.objects.get()
    assert resposta.status_code == 302
    assert resposta["Location"] == _gestao(evento)
    assert (evento.organizador, evento.status, evento.preco_centavos) == (
        organizador,
        Evento.Status.RASCUNHO,
        10000,
    )
    assert "Evento criado." in client_organizador.get(_gestao(evento)).content.decode()


@pytest.mark.parametrize(
    ("campo", "valor", "mensagem"),
    [
        ("inicio", "2026-01-10T20:00", "A data de início precisa estar no futuro."),
        ("lotacao", "0", "A lotação precisa ser um número inteiro maior ou igual a 1."),
        ("lotacao", "2.5", "A lotação precisa ser um número inteiro maior ou igual a 1."),
        ("preco", "abc", "Informe o preço em reais, por exemplo 100,00."),
        ("preco", "-10", "O preço precisa ser maior que zero."),
        ("nome", "", "Informe o nome do evento."),
    ],
)
def test_criar_evento_invalido_reexibe_formulario_sem_gravar(
    client_organizador, campo, valor, mensagem
):
    resposta = client_organizador.post(NOVO, _dados(**{campo: valor}))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert mensagem in html
    assert 'value="Bar do Porão"' in html
    assert Evento.objects.count() == 0


def test_gestao_mostra_dados_acoes_e_slots(client_organizador, organizador, evento):
    html = client_organizador.get(_gestao(evento)).content.decode()
    for secao in ("evento-dados", "evento-acoes", "evento-cancelar", "check-in", "painel"):
        assert html.count(f'id="{secao}"') == 1
    inicio = timezone.localtime(evento.inicio).strftime("%d/%m/%Y %H:%M")
    for trecho in (
        'data-campo="nome">Jazz no Porão<',
        f'data-campo="inicio">{inicio}<',
        'data-campo="local">Bar do Porão<',
        'data-campo="lotacao">2<',
        'data-campo="preco">R$ 100,00<',
        'data-campo="status">Rascunho<',
        f'href="/organizador/eventos/{evento.id_publico}/editar/"',
        f'action="/organizador/eventos/{evento.id_publico}/publicar/"',
    ):
        assert trecho in html

    srv.publicar_evento(organizador, evento.id_publico)
    html = client_organizador.get(_gestao(evento)).content.decode()
    assert 'data-campo="status">Publicado<' in html
    assert "/publicar/" not in html


def test_editar_evento_pela_tela(client_organizador, organizador, evento):
    srv.publicar_evento(organizador, evento.id_publico)
    editar = f"{_gestao(evento)}editar/"
    form = client_organizador.get(editar).content.decode()
    inicio = timezone.localtime(evento.inicio).strftime("%Y-%m-%dT%H:%M")
    assert f'value="{inicio}"' in form and 'value="100,00"' in form

    novo = _dados(nome="Jazz (edição)", local="Porão Novo", lotacao="4", preco="120,50")
    resposta = client_organizador.post(editar, novo)
    assert (resposta.status_code, resposta["Location"]) == (302, _gestao(evento))
    evento.refresh_from_db()
    assert (evento.nome, evento.local, evento.lotacao, evento.preco_centavos) == (
        "Jazz (edição)",
        "Porão Novo",
        4,
        12050,
    )
    assert "R$ 120,50" in Client().get("/").content.decode()

    resposta = client_organizador.post(editar, _dados(inicio="2026-01-10T20:00"))
    assert resposta.status_code == 200
    assert "A data de início precisa estar no futuro." in resposta.content.decode()
    evento.refresh_from_db()
    assert evento.nome == "Jazz (edição)"


def test_publicar_evento_pela_tela(client_organizador, evento):
    publicar = f"{_gestao(evento)}publicar/"
    assert client_organizador.get(publicar).status_code == 405
    for _ in range(2):
        resposta = client_organizador.post(publicar)
        assert (resposta.status_code, resposta["Location"]) == (302, _gestao(evento))
        evento.refresh_from_db()
        assert evento.status == Evento.Status.PUBLICADO
    assert Evento.objects.count() == 1


def test_lista_do_organizador_so_mostra_os_proprios(organizador, organizador_b, evento):
    srv.criar_evento(organizador_b, _dados(nome="Evento do B"))
    html_a = _cliente(organizador).get("/organizador/").content.decode()
    html_b = _cliente(organizador_b).get("/organizador/").content.decode()
    assert "Jazz no Porão" in html_a and "Rascunho" in html_a
    assert "Evento do B" not in html_a
    assert "Evento do B" in html_b and "Jazz no Porão" not in html_b


def test_lista_vazia_do_organizador(client_organizador):
    html = client_organizador.get("/organizador/").content.decode()
    assert "Você ainda não tem eventos." in html
    assert 'href="/organizador/eventos/novo/"' in html


def test_outro_organizador_recebe_404_sem_dados(organizador_b, evento):
    cliente = _cliente(organizador_b)
    base = _gestao(evento)
    respostas = [
        cliente.get(base),
        cliente.get(f"{base}editar/"),
        cliente.post(f"{base}editar/", _dados(nome="Hackeado")),
        cliente.post(f"{base}publicar/"),
    ]
    for resposta in respostas:
        assert resposta.status_code == 404
        html = resposta.content.decode()
        for proibido in ("Jazz no Porão", "Bar do Porão", "100,00", "data-campo"):
            assert proibido not in html
    evento.refresh_from_db()
    assert (evento.nome, evento.status) == ("Jazz no Porão", Evento.Status.RASCUNHO)


def test_participante_nao_cria_evento(client_participante):
    assert client_participante.get(NOVO).status_code == 403
    assert client_participante.post(NOVO, _dados()).status_code == 403
    assert Evento.objects.count() == 0


def test_visitante_na_gestao_vai_para_o_login_sem_dados(evento):
    resposta = Client().get(_gestao(evento))
    assert resposta.status_code == 302
    assert resposta["Location"] == f"/contas/entrar/?next={_gestao(evento)}"
    assert "Jazz no Porão" not in resposta.content.decode()
    resposta = Client().post(f"{_gestao(evento)}publicar/")
    assert (resposta.status_code, resposta["Location"]) == (302, "/contas/entrar/")
    evento.refresh_from_db()
    assert evento.status == Evento.Status.RASCUNHO
