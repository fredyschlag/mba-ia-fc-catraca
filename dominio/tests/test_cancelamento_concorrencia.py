"""R11 sob concorrência: resposta do gateway e cancelamento disputando o mesmo ingresso.

Dois tipos de prova, contra o Postgres (READ COMMITTED, o padrão):
- a corrida solta (barreira de 2 threads, 50 repetições) exige o par coerente entre o retorno de
  `aplicar_resposta_gateway` e o status final: (True, "refunded") ou (False, "cancelled");
- dois testes determinísticos seguram uma das operações com a transação aberta e mostram que a
  outra espera a trava da linha e reavalia o WHERE sobre a versão gravada.
"""

import threading
import time

import pytest
from django.db import connection, transaction

from dominio.models import Evento, Ingresso, Usuario
from dominio.servicos import compras, eventos
from dominio.servicos.cancelamento import cancelar_evento
from dominio.servicos.gateway import aplicar_resposta_gateway
from dominio.tests.conftest import dados_evento

REPETICOES = 50


def _organizador(email):
    return Usuario.objects.create_user(email, "x" * 10, nome="Org", papel=Usuario.Papel.ORGANIZADOR)


def _evento_com_pendente(organizador, nome):
    evento = eventos.criar_evento(organizador, dados_evento(nome=nome))
    eventos.publicar_evento(organizador, evento.id_publico)
    ingresso = compras.comprar_ingresso(
        evento.id_publico, cartao="4000000000000003", email_comprador="a@example.com", canal="api"
    )
    return evento, ingresso


def _rodar(*alvos):
    threads = [threading.Thread(target=alvo) for alvo in alvos]
    for thread in threads:
        thread.start()
    return threads


@pytest.mark.django_db(transaction=True)
def test_corrida_aprovacao_e_cancelamento_nunca_deixa_confirmado():
    organizador = _organizador("org.corrida@example.com")
    pares = []
    for rodada in range(REPETICOES):
        evento, ingresso = _evento_com_pendente(organizador, f"Corrida {rodada}")
        barreira = threading.Barrier(2)
        saida = {}

        def aprovar(ingresso_id=ingresso.id, barreira=barreira, saida=saida):
            try:
                barreira.wait()
                saida["aplicou"] = aplicar_resposta_gateway(ingresso_id, True)
            except Exception as erro:  # noqa: BLE001
                saida["erro_aprovar"] = repr(erro)
            finally:
                connection.close()

        def cancelar(evento_id=evento.id_publico, barreira=barreira, saida=saida):
            try:
                barreira.wait()
                cancelar_evento(organizador, evento_id)
            except Exception as erro:  # noqa: BLE001
                saida["erro_cancelar"] = repr(erro)
            finally:
                connection.close()

        for thread in _rodar(aprovar, cancelar):
            thread.join(timeout=30)

        assert set(saida) == {"aplicou"}, f"rodada {rodada}: {saida}"
        assert Evento.objects.get(pk=evento.pk).status == Evento.Status.CANCELADO
        par = (saida["aplicou"], Ingresso.objects.get(pk=ingresso.pk).status)
        assert par in ((True, "refunded"), (False, "cancelled")), f"rodada {rodada}: {par}"
        pares.append(par)
    assert len(pares) == REPETICOES


@pytest.mark.django_db(transaction=True)
def test_aprovacao_que_espera_o_cancelamento_nao_muda_nada():
    organizador = _organizador("org.espera1@example.com")
    evento, ingresso = _evento_com_pendente(organizador, "Cancelamento primeiro")
    segurando, liberar, saida = threading.Event(), threading.Event(), {}

    def cancelar_e_segurar():
        try:
            with transaction.atomic():
                cancelar_evento(organizador, evento.id_publico)
                segurando.set()
                liberar.wait(10)
        finally:
            connection.close()

    def aprovar():
        try:
            segurando.wait(10)
            saida["aplicou"] = aplicar_resposta_gateway(ingresso.id, True)
        finally:
            connection.close()

    threads = _rodar(cancelar_e_segurar, aprovar)
    segurando.wait(10)
    time.sleep(0.3)
    assert "aplicou" not in saida  # a aprovação está esperando a trava da linha
    liberar.set()
    for thread in threads:
        thread.join(timeout=30)
    assert saida["aplicou"] is False
    assert Ingresso.objects.get(pk=ingresso.pk).status == "cancelled"


@pytest.mark.django_db(transaction=True)
def test_cancelamento_que_espera_a_aprovacao_estorna():
    organizador = _organizador("org.espera2@example.com")
    evento, ingresso = _evento_com_pendente(organizador, "Aprovação primeiro")
    segurando, liberar, saida = threading.Event(), threading.Event(), {}

    def aprovar_e_segurar():
        try:
            with transaction.atomic():
                saida["aplicou"] = aplicar_resposta_gateway(ingresso.id, True)
                segurando.set()
                liberar.wait(10)
        finally:
            connection.close()

    def cancelar():
        try:
            segurando.wait(10)
            cancelar_evento(organizador, evento.id_publico)
            saida["cancelou"] = True
        finally:
            connection.close()

    threads = _rodar(aprovar_e_segurar, cancelar)
    segurando.wait(10)
    time.sleep(0.3)
    assert "cancelou" not in saida  # o cancelamento está esperando a trava da linha do ingresso
    liberar.set()
    for thread in threads:
        thread.join(timeout=30)
    assert (saida["aplicou"], saida["cancelou"]) == (True, True)
    assert Ingresso.objects.get(pk=ingresso.pk).status == "refunded"
    assert Evento.objects.get(pk=evento.pk).status == Evento.Status.CANCELADO
