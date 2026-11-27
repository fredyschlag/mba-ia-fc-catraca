"""R10 sob concorrência real: threads com conexões próprias fazendo o check-in do mesmo código."""

import threading

import pytest
from django.db import connection

from dominio.models import Ingresso, Usuario
from dominio.servicos import compras, eventos
from dominio.servicos.checkin import ResultadoCheckIn, fazer_check_in
from dominio.servicos.gateway import aplicar_resposta_gateway
from dominio.tests.conftest import dados_evento

CHECK_INS_SIMULTANEOS = 10
RODADAS = 10


def _disputar(organizador, evento_id, codigo):
    barreira = threading.Barrier(CHECK_INS_SIMULTANEOS)
    resultados = []
    trava = threading.Lock()

    def check_in():
        try:
            barreira.wait()
            resultado = fazer_check_in(organizador, evento_id, codigo)
        except Exception as erro:  # noqa: BLE001 — qualquer erro reprova o teste
            resultado = f"erro: {erro!r}"
        finally:
            connection.close()
        with trava:
            resultados.append(resultado)

    threads = [threading.Thread(target=check_in) for _ in range(CHECK_INS_SIMULTANEOS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return resultados


@pytest.mark.django_db(transaction=True)
def test_check_ins_simultaneos_liberam_uma_unica_vez():
    organizador = Usuario.objects.create_user(
        "org.checkin@example.com", "x" * 10, nome="Org", papel=Usuario.Papel.ORGANIZADOR
    )
    evento = eventos.criar_evento(
        organizador, dados_evento(nome="Porta cheia", lotacao=str(RODADAS))
    )
    eventos.publicar_evento(organizador, evento.id_publico)

    for rodada in range(RODADAS):
        ingresso = compras.comprar_ingresso(
            evento.id_publico,
            cartao="4000000000000001",
            email_comprador=f"porta{rodada}@example.com",
            canal="vitrine",
        )
        assert aplicar_resposta_gateway(ingresso.pk, aprovado=True)

        resultados = _disputar(organizador, evento.id_publico, ingresso.codigo)

        assert len(resultados) == CHECK_INS_SIMULTANEOS, f"rodada {rodada}: thread presa"
        liberadas = resultados.count(ResultadoCheckIn.ENTRADA_LIBERADA)
        utilizados = resultados.count(ResultadoCheckIn.JA_UTILIZADO)
        assert liberadas == 1, f"rodada {rodada}: {resultados}"
        assert utilizados == CHECK_INS_SIMULTANEOS - 1, f"rodada {rodada}: {resultados}"
        ingresso.refresh_from_db()
        assert ingresso.status == Ingresso.Status.CONFIRMADO
        assert ingresso.check_in_em is not None

    assert Ingresso.objects.filter(evento=evento, check_in_em__isnull=False).count() == RODADAS
