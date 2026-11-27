from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from dominio.models import CobrancaGateway, Evento, Ingresso, Usuario
from dominio.servicos import compras, eventos
from dominio.servicos.gateway import aplicar_resposta_gateway
from web.tests.conftest import SENHA

pytestmark = pytest.mark.django_db

CARTAO = "4000000000000001"


def _futuro(dias=30):
    dia = timezone.localtime(timezone.now() + timedelta(days=dias)).date()
    return f"{dia.isoformat()}T21:00"


def _dados(**extra):
    dados = {
        "nome": "Show",
        "inicio": _futuro(),
        "local": "Bar",
        "lotacao": "2",
        "preco": "100,00",
    }
    dados.update(extra)
    return dados


@pytest.fixture
def evento(organizador):
    criado = eventos.criar_evento(organizador, _dados())
    return eventos.publicar_evento(organizador, criado.id_publico)


def _comprar_url(evento):
    return f"/eventos/{evento.id_publico}/comprar/"


def _compra_direta(evento, cartao=CARTAO, comprador=None):
    return compras.comprar_ingresso(
        evento.id_publico,
        cartao=cartao,
        email_comprador="x@example.com",
        canal="api",
        comprador=comprador,
    )


def _bloco(html):
    return html.split('id="compra"', 1)[1].split("</section>", 1)[0]


def test_bloco_compra_com_vaga_mostra_formulario(client_participante, evento):
    bloco = _bloco(client_participante.get(f"/eventos/{evento.id_publico}/").content.decode())
    assert 'id="form-compra"' in bloco and 'name="cartao"' in bloco
    assert 'data-campo="vagas-disponiveis">2<' in bloco
    assert "Ingressos esgotados" not in bloco


def test_bloco_compra_sem_vaga_mostra_esgotados(client_participante, evento):
    _compra_direta(evento)
    _compra_direta(evento, "4000000000000003")
    bloco = _bloco(client_participante.get(f"/eventos/{evento.id_publico}/").content.decode())
    assert 'id="esgotado"' in bloco and "Ingressos esgotados" in bloco
    assert 'id="form-compra"' not in bloco
    assert 'data-campo="vagas-disponiveis">0<' in bloco


def test_visitante_ve_link_para_entrar(evento):
    bloco = _bloco(Client().get(f"/eventos/{evento.id_publico}/").content.decode())
    assert f'href="/contas/entrar/?next=/eventos/{evento.id_publico}/"' in bloco
    assert 'id="form-compra"' not in bloco


def test_compra_pela_vitrine_vai_para_meus_ingressos_pendente(
    client_participante, participante, evento
):
    resposta = client_participante.post(_comprar_url(evento), {"cartao": CARTAO})
    assert (resposta.status_code, resposta["Location"]) == (302, "/meus-ingressos/")
    ingresso = Ingresso.objects.get()
    assert (ingresso.comprador, ingresso.canal, ingresso.status) == (
        participante,
        "vitrine",
        "pending",
    )
    assert ingresso.email_comprador == participante.email
    html = client_participante.get("/meus-ingressos/").content.decode()
    linha = next(li for li in html.splitlines() if f'data-ingresso="{ingresso.id_publico}"' in li)
    assert 'data-campo="evento">Show<' in linha
    assert 'data-campo="status">pendente<' in linha
    assert f'data-campo="codigo">{ingresso.codigo}<' in linha
    assert "Compra registrada. O pagamento está sendo processado." in html

    aplicar_resposta_gateway(ingresso.pk, aprovado=True)
    html = client_participante.get("/meus-ingressos/").content.decode()
    assert 'data-campo="status">confirmado<' in html


@pytest.mark.parametrize("cartao", ["123", "40000000000000011", "400000000000000A", ""])
def test_compra_com_cartao_invalido_reexibe_sem_criar(client_participante, evento, cartao):
    resposta = client_participante.post(_comprar_url(evento), {"cartao": cartao})
    assert resposta.status_code == 200
    assert "O número do cartão precisa ter 16 dígitos." in resposta.content.decode()
    assert (Ingresso.objects.count(), CobrancaGateway.objects.count()) == (0, 0)


def test_compra_esgotada_mostra_mensagem_sem_criar(client_participante, evento):
    _compra_direta(evento)
    _compra_direta(evento)
    resposta = client_participante.post(_comprar_url(evento), {"cartao": CARTAO})
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert 'id="erro-compra">Ingressos esgotados<' in html
    assert Ingresso.objects.count() == 2


def test_compra_de_rascunho_ou_inexistente_responde_404(client_participante, organizador):
    rascunho = eventos.criar_evento(organizador, _dados())
    assert client_participante.post(_comprar_url(rascunho), {"cartao": CARTAO}).status_code == 404
    resposta = client_participante.post("/eventos/evt_zzzzzzzz/comprar/", {"cartao": CARTAO})
    assert resposta.status_code == 404
    Evento.objects.filter(pk=rascunho.pk).update(status="cancelado")
    assert client_participante.post(_comprar_url(rascunho), {"cartao": CARTAO}).status_code == 404
    assert Ingresso.objects.count() == 0


def test_visitante_e_organizador_nao_compram(client, organizador, evento):
    resposta = client.post(_comprar_url(evento), {"cartao": CARTAO})
    assert (resposta.status_code, resposta["Location"]) == (302, "/contas/entrar/")
    org = Client()
    org.force_login(organizador)
    assert org.post(_comprar_url(evento), {"cartao": CARTAO}).status_code == 403
    assert (
        "Compras são feitas com uma conta de participante."
        in org.get(f"/eventos/{evento.id_publico}/").content.decode()
    )
    assert Ingresso.objects.count() == 0


def test_meus_ingressos_so_os_proprios(participante, evento):
    outro = Usuario.objects.create_user("outra@example.com", SENHA, nome="Outra")
    meu = _compra_direta(evento, comprador=participante)
    dela = _compra_direta(evento, comprador=outro)
    cliente = Client()
    cliente.force_login(participante)
    html = cliente.get("/meus-ingressos/").content.decode()
    assert meu.codigo in html and dela.codigo not in html
    vazio = Client()
    vazio.force_login(Usuario.objects.create_user("nova@example.com", SENHA, nome="Nova"))
    assert "Você ainda não tem ingressos." in vazio.get("/meus-ingressos/").content.decode()
    resposta = Client().get("/meus-ingressos/")
    assert resposta["Location"] == "/contas/entrar/?next=/meus-ingressos/"


def test_editar_lotacao_abaixo_das_ocupadas_pela_tela(client_organizador, evento):
    _compra_direta(evento)
    _compra_direta(evento, "4000000000000003")
    editar = f"/organizador/eventos/{evento.id_publico}/editar/"
    resposta = client_organizador.post(editar, _dados(lotacao="1"))
    assert resposta.status_code == 200
    assert "A lotação não pode ser menor que as vagas ocupadas (2)." in resposta.content.decode()
    evento.refresh_from_db()
    assert evento.lotacao == 2
    resposta = client_organizador.post(editar, _dados(lotacao="3", preco="150,00"))
    assert resposta.status_code == 302
    novo = _compra_direta(evento)
    assert novo.valor_centavos == 15000
