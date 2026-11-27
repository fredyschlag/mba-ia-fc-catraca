import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from dominio.models import Evento, Ingresso
from dominio.servicos import compras, eventos
from dominio.servicos.painel import Painel, painel_do_evento
from dominio.tests.conftest import dados_evento

pytestmark = pytest.mark.django_db


def publicado(organizador, **dados):
    evento = eventos.criar_evento(organizador, dados_evento(**dados))
    return eventos.publicar_evento(organizador, evento.id_publico)


def ingresso(evento, status="pending", canal="api", check_in=False, cartao="4000000000000001"):
    criado = compras.comprar_ingresso(
        evento.id_publico, cartao=cartao, email_comprador="a@example.com", canal=canal
    )
    campos = {"status": status}
    if check_in:
        campos["check_in_em"] = timezone.now()
    Ingresso.objects.filter(pk=criado.pk).update(**campos)
    return criado


def test_painel_de_evento_sem_ingressos(organizador):
    evento = publicado(organizador, lotacao="4")
    assert painel_do_evento(evento) == Painel(0, 0, 0, 4, 0, 0)


def test_painel_conta_cada_status_pela_definicao(organizador):
    evento = publicado(organizador, lotacao="20", preco="10,00")
    for status, quantos in (
        ("pending", 2),
        ("confirmed", 3),
        ("declined", 4),
        ("cancelled", 1),
        ("refunded", 2),
    ):
        for _ in range(quantos):
            ingresso(evento, status)
    ingresso(evento, "confirmed", check_in=True)
    assert painel_do_evento(evento) == Painel(
        confirmados=4,
        pendentes=2,
        check_ins=1,
        vagas_disponiveis=20 - 2 - 4,
        receita_centavos=4 * 1000,
        estornados=2,
    )


def test_check_ins_so_de_confirmados(organizador):
    evento = publicado(organizador, lotacao="10")
    ingresso(evento, "confirmed", check_in=True)
    ingresso(evento, "confirmed")
    ingresso(evento, "refunded", check_in=True)
    ingresso(evento, "cancelled", check_in=True)
    painel = painel_do_evento(evento)
    assert (painel.confirmados, painel.check_ins, painel.estornados) == (2, 1, 1)


def test_receita_soma_o_preco_gravado_de_cada_confirmado(organizador):
    evento = publicado(organizador, lotacao="3", preco="100,00")
    ingresso(evento, "confirmed")
    ingresso(evento, "confirmed", canal="vitrine")
    eventos.editar_evento(organizador, evento.id_publico, dados_evento(lotacao="3", preco="150,00"))
    ingresso(evento, "confirmed")
    eventos.editar_evento(organizador, evento.id_publico, dados_evento(lotacao="3", preco="999,00"))
    painel = painel_do_evento(evento)
    assert painel.receita_centavos == 35000
    assert (painel.confirmados, painel.vagas_disponiveis) == (3, 0)


def test_receita_ignora_pendentes_recusados_cancelados_e_estornados(organizador):
    evento = publicado(organizador, lotacao="10", preco="50,00")
    for status in ("pending", "declined", "cancelled", "refunded"):
        ingresso(evento, status)
    assert painel_do_evento(evento).receita_centavos == 0
    ingresso(evento, "confirmed")
    assert painel_do_evento(evento).receita_centavos == 5000


def test_vitrine_e_api_contam_igual(organizador, participante):
    evento = publicado(organizador, lotacao="4", preco="20,00")
    ingresso(evento, "confirmed", canal="api", check_in=True)
    vitrine = compras.comprar_ingresso(
        evento.id_publico,
        cartao="4000000000000001",
        email_comprador=participante.email,
        canal="vitrine",
        comprador=participante,
    )
    Ingresso.objects.filter(pk=vitrine.pk).update(status="confirmed", check_in_em=timezone.now())
    ingresso(evento, "pending", canal="vitrine")
    assert painel_do_evento(evento) == Painel(2, 1, 2, 1, 4000, 0)


def test_vagas_disponiveis_segue_r05_e_zera_em_cancelado(organizador):
    evento = publicado(organizador, lotacao="5")
    ingresso(evento, "pending")
    ingresso(evento, "confirmed")
    ingresso(evento, "declined")
    assert painel_do_evento(evento).vagas_disponiveis == 3
    Evento.objects.filter(pk=evento.pk).update(status=Evento.Status.CANCELADO)
    evento.refresh_from_db()
    assert painel_do_evento(evento).vagas_disponiveis == 0


def test_painel_usa_uma_consulta_agregada(organizador):
    evento = publicado(organizador, lotacao="5")
    ingresso(evento, "confirmed")
    with CaptureQueriesContext(connection) as consultas:
        painel_do_evento(evento)
    agregadas = [q["sql"] for q in consultas.captured_queries if "COUNT" in q["sql"].upper()]
    assert len(consultas.captured_queries) == 2  # agregados + vagas_ocupadas (R05)
    assert any("SUM" in sql.upper() for sql in agregadas)
