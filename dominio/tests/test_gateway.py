import random
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from dominio.models import CobrancaGateway, Ingresso
from dominio.servicos import compras, eventos
from dominio.servicos.gateway import (
    GatewaySimulado,
    aplicar_resposta_gateway,
    processar_cobrancas_vencidas,
)
from dominio.tests.conftest import dados_evento

pytestmark = pytest.mark.django_db


def _ingresso(organizador, cartao="4000000000000001"):
    evento = eventos.criar_evento(organizador, dados_evento(lotacao="50"))
    eventos.publicar_evento(organizador, evento.id_publico)
    return compras.comprar_ingresso(
        evento.id_publico, cartao=cartao, email_comprador="a@example.com", canal="api"
    )


@pytest.mark.parametrize(
    ("final", "aprovado"),
    [
        ("0001", True),
        ("0002", False),
        ("0003", True),
        ("0004", False),
        ("0009", False),
        ("1234", False),
    ],
)
def test_resultado_por_final_do_cartao(final, aprovado):
    assert GatewaySimulado.resultado_para("400000000000" + final) is aprovado


@pytest.mark.parametrize(
    ("final", "faixa"),
    [("0001", (2, 4)), ("0002", (2, 4)), ("0009", (2, 4)), ("0003", (32, 38)), ("0004", (32, 38))],
)
def test_atrasos_ficam_nas_faixas_com_semente(final, faixa):
    aleatorio = random.Random(20261127)
    atrasos = [
        GatewaySimulado.atraso_para("400000000000" + final, aleatorio).total_seconds()
        for _ in range(1000)
    ]
    assert all(faixa[0] <= a <= faixa[1] for a in atrasos)
    assert max(atrasos) - min(atrasos) > (faixa[1] - faixa[0]) * 0.9  # cobre a faixa


def test_fator_de_atraso_multiplica(settings):
    assert settings.GATEWAY_FATOR_ATRASO == 1.0
    settings.GATEWAY_FATOR_ATRASO = 0.01
    lento = GatewaySimulado.atraso_para("4000000000000003", random.Random(1))
    assert timedelta(seconds=0.32) <= lento <= timedelta(seconds=0.38)


def test_compose_nao_define_fator_de_atraso():
    compose = (Path(settings.BASE_DIR) / "compose.yaml").read_text()
    assert "GATEWAY_FATOR_ATRASO" not in compose


@pytest.mark.parametrize("status", ["confirmed", "declined", "cancelled", "refunded"])
def test_aplicar_resposta_so_muda_pendente(organizador, status):
    ingresso = _ingresso(organizador)
    Ingresso.objects.filter(pk=ingresso.pk).update(status=status)
    for aprovado in (True, False):
        assert aplicar_resposta_gateway(ingresso.pk, aprovado) is False
        ingresso.refresh_from_db()
        assert ingresso.status == status


def test_aplicar_resposta_em_pendente(organizador):
    aprovado = _ingresso(organizador)
    recusado = _ingresso(organizador)
    assert aplicar_resposta_gateway(aprovado.pk, True) is True
    assert aplicar_resposta_gateway(recusado.pk, False) is True
    aprovado.refresh_from_db()
    recusado.refresh_from_db()
    assert (aprovado.status, recusado.status) == ("confirmed", "declined")
    assert aplicar_resposta_gateway(aprovado.pk, False) is False


def test_processar_cobrancas_vencidas_marca_processada_mesmo_sem_mudanca(organizador):
    vencida = _ingresso(organizador, "4000000000000001")
    cancelada = _ingresso(organizador, "4000000000000003")
    Ingresso.objects.filter(pk=cancelada.pk).update(status="cancelled")
    depois = timezone.now() + timedelta(seconds=60)
    assert processar_cobrancas_vencidas(agora=depois) == 2
    vencida.refresh_from_db()
    cancelada.refresh_from_db()
    assert (vencida.status, cancelada.status) == ("confirmed", "cancelled")
    assert CobrancaGateway.objects.filter(processada_em__isnull=True).count() == 0
    assert processar_cobrancas_vencidas(agora=depois) == 0


def test_processar_ignora_cobrancas_nao_vencidas(organizador):
    rapido = _ingresso(organizador, "4000000000000002")
    lento = _ingresso(organizador, "4000000000000003")
    assert processar_cobrancas_vencidas(agora=timezone.now() + timedelta(seconds=10)) == 1
    rapido.refresh_from_db()
    lento.refresh_from_db()
    assert (rapido.status, lento.status) == ("declined", "pending")
    assert lento.cobranca.processada_em is None


def test_worker_processa_cobrancas_vencidas(organizador):
    ingresso = _ingresso(organizador)
    CobrancaGateway.objects.filter(ingresso=ingresso).update(
        responder_em=timezone.now() - timedelta(seconds=1)
    )
    call_command("gateway_worker", voltas=1)
    ingresso.refresh_from_db()
    assert ingresso.status == "confirmed"


def test_worker_sobrevive_a_erro(monkeypatch):
    from dominio.management.commands import gateway_worker

    def falha():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(gateway_worker, "processar_cobrancas_vencidas", falha)
    call_command("gateway_worker", voltas=2)  # não levanta


@pytest.mark.django_db(transaction=True)
def test_respostas_simultaneas_so_uma_aplica():
    import threading

    from django.db import connection

    from dominio.models import Usuario

    organizador = Usuario.objects.create_user(
        "org.gateway@example.com", "x" * 10, nome="Org", papel=Usuario.Papel.ORGANIZADOR
    )
    for _ in range(20):
        ingresso = _ingresso(organizador, "4000000000000003")
        barreira = threading.Barrier(2)
        resultados = []

        def responder(aprovado, ingresso_id=ingresso.pk, barreira=barreira, saida=resultados):
            try:
                barreira.wait()
                saida.append((aprovado, aplicar_resposta_gateway(ingresso_id, aprovado)))
            finally:
                connection.close()

        threads = [threading.Thread(target=responder, args=(a,)) for a in (True, False)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert [r for _, r in resultados].count(True) == 1
        vencedor = next(a for a, r in resultados if r)
        ingresso.refresh_from_db()
        assert ingresso.status == ("confirmed" if vencedor else "declined")
