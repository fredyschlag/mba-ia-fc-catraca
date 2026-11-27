import time

import pytest
from django.utils import timezone

from dominio.excecoes import (
    CancelamentoNaoPermitido,
    EventoCancelado,
    EventoIndisponivel,
    EventoNaoEncontrado,
)
from dominio.models import CobrancaGateway, Evento, Ingresso
from dominio.servicos import compras, eventos
from dominio.servicos.cancelamento import cancelar_evento
from dominio.servicos.gateway import processar_cobrancas_vencidas
from dominio.tests.conftest import dados_evento

pytestmark = pytest.mark.django_db


def publicado(organizador, **dados):
    evento = eventos.criar_evento(organizador, dados_evento(lotacao="10", **dados))
    return eventos.publicar_evento(organizador, evento.id_publico)


def ingresso(evento, status=None, cartao="4000000000000001", check_in=False):
    criado = compras.comprar_ingresso(
        evento.id_publico, cartao=cartao, email_comprador="a@example.com", canal="api"
    )
    campos = {}
    if status:
        campos["status"] = status
    if check_in:
        campos["check_in_em"] = timezone.now()
    if campos:
        Ingresso.objects.filter(pk=criado.pk).update(**campos)
    criado.refresh_from_db()
    return criado


def status(*ingressos):
    return [Ingresso.objects.get(pk=i.pk).status for i in ingressos]


def test_cancelar_publicado_estorna_confirmados_e_cancela_pendentes(organizador):
    evento = publicado(organizador)
    confirmado = ingresso(evento, "confirmed")
    pendente = ingresso(evento)
    cancelado = cancelar_evento(organizador, evento.id_publico)
    assert cancelado.status == Evento.Status.CANCELADO
    evento.refresh_from_db()
    assert evento.status == Evento.Status.CANCELADO
    assert status(confirmado, pendente) == ["refunded", "cancelled"]


def test_cancelar_mantem_check_in_e_recusados(organizador):
    evento = publicado(organizador)
    com_check_in = ingresso(evento, "confirmed", check_in=True)
    recusado = ingresso(evento, "declined")
    cancelar_evento(organizador, evento.id_publico)
    com_check_in.refresh_from_db()
    assert (com_check_in.status, com_check_in.check_in_em is not None) == ("refunded", True)
    assert status(recusado) == ["declined"]


def test_cancelar_de_novo_nao_muda_nada(organizador):
    evento = publicado(organizador)
    estornado = ingresso(evento, "confirmed")
    cancelar_evento(organizador, evento.id_publico)
    assert cancelar_evento(organizador, evento.id_publico).status == Evento.Status.CANCELADO
    assert status(estornado) == ["refunded"]


def test_cancelar_rascunho_e_rejeitado(organizador):
    rascunho = eventos.criar_evento(organizador, dados_evento())
    with pytest.raises(CancelamentoNaoPermitido) as erro:
        cancelar_evento(organizador, rascunho.id_publico)
    assert str(erro.value) == "Só evento publicado pode ser cancelado."
    rascunho.refresh_from_db()
    assert rascunho.status == Evento.Status.RASCUNHO


def test_cancelar_evento_de_outro_organizador(organizador, organizador_b):
    evento = publicado(organizador)
    for evento_id in (evento.id_publico, "evt_zzzzzzzz"):
        with pytest.raises(EventoNaoEncontrado):
            cancelar_evento(organizador_b, evento_id)
    evento.refresh_from_db()
    assert evento.status == Evento.Status.PUBLICADO


def test_evento_cancelado_nao_edita_nem_publica(organizador):
    evento = publicado(organizador)
    cancelar_evento(organizador, evento.id_publico)
    with pytest.raises(EventoCancelado) as erro:
        eventos.editar_evento(organizador, evento.id_publico, dados_evento(nome="Novo"))
    assert str(erro.value) == "Evento cancelado não pode ser alterado."
    with pytest.raises(EventoCancelado):
        eventos.editar_evento(organizador, evento.id_publico, {"nome": ""})
    with pytest.raises(EventoCancelado):
        eventos.publicar_evento(organizador, evento.id_publico)
    with pytest.raises(EventoCancelado):
        eventos.garantir_editavel(organizador, evento.id_publico)
    evento.refresh_from_db()
    assert (evento.nome, evento.status) == ("Jazz no Porão", Evento.Status.CANCELADO)


def test_evento_cancelado_sai_da_venda(organizador):
    evento = publicado(organizador)
    cancelar_evento(organizador, evento.id_publico)
    assert evento not in eventos.eventos_a_venda()
    with pytest.raises(EventoIndisponivel):
        eventos.evento_a_venda(evento.id_publico)
    with pytest.raises(EventoIndisponivel):
        ingresso(evento)


def test_vagas_de_evento_cancelado_sao_zero(organizador):
    evento = publicado(organizador)
    ingresso(evento, "declined")
    cancelar_evento(organizador, evento.id_publico)
    evento.refresh_from_db()
    assert (compras.vagas_ocupadas(evento), compras.vagas_disponiveis(evento)) == (0, 0)


@pytest.mark.parametrize("cartao", ["4000000000000003", "4000000000000004"])
def test_resposta_tardia_nao_muda_cancelado_nem_estornado(organizador, settings, cartao):
    """Fator de atraso curto: o lento responde em ~0,35 s, depois do cancelamento."""
    settings.GATEWAY_FATOR_ATRASO = 0.01
    evento = publicado(organizador)
    pendente = ingresso(evento, cartao=cartao)
    confirmado = ingresso(evento, "confirmed")
    cancelar_evento(organizador, evento.id_publico)
    time.sleep(0.5)
    assert processar_cobrancas_vencidas() >= 1
    assert status(pendente, confirmado) == ["cancelled", "refunded"]
    assert CobrancaGateway.objects.get(ingresso=pendente).processada_em is not None


def test_propriedades_de_estado_do_evento(organizador):
    rascunho = eventos.criar_evento(organizador, dados_evento())
    assert (
        rascunho.pode_ser_editado,
        rascunho.pode_ser_publicado,
        rascunho.pode_ser_cancelado,
    ) == (
        True,
        True,
        False,
    )
    evento = publicado(organizador)
    assert (evento.pode_ser_editado, evento.pode_ser_publicado, evento.pode_ser_cancelado) == (
        True,
        False,
        True,
    )
    evento = cancelar_evento(organizador, evento.id_publico)
    assert (evento.pode_ser_editado, evento.pode_ser_publicado, evento.pode_ser_cancelado) == (
        False,
        False,
        False,
    )
