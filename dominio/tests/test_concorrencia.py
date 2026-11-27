"""R07 sob concorrência real: threads com conexões próprias disputando as vagas no Postgres."""

import threading

import pytest
from django.db import connection

from dominio.excecoes import IngressosEsgotados
from dominio.models import Ingresso, Usuario
from dominio.servicos import compras, eventos
from dominio.tests.conftest import dados_evento

COMPRAS_SIMULTANEAS = 30
LOTACAO = 5
RODADAS = 10


def _disputar(evento_id):
    barreira = threading.Barrier(COMPRAS_SIMULTANEAS)
    resultados = []
    trava = threading.Lock()

    def comprar(indice):
        try:
            barreira.wait()
            compras.comprar_ingresso(
                evento_id,
                cartao="4000000000000001",
                email_comprador=f"carga{indice}@example.com",
                canal="api",
            )
            resultado = "ok"
        except IngressosEsgotados:
            resultado = "esgotado"
        except Exception as erro:  # noqa: BLE001 — qualquer outro erro reprova o teste
            resultado = f"erro: {erro!r}"
        finally:
            connection.close()
        with trava:
            resultados.append(resultado)

    threads = [threading.Thread(target=comprar, args=(i,)) for i in range(COMPRAS_SIMULTANEAS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return resultados


@pytest.mark.django_db(transaction=True)
def test_compras_simultaneas_nunca_passam_da_lotacao():
    organizador = Usuario.objects.create_user(
        "org.concorrencia@example.com", "x" * 10, nome="Org", papel=Usuario.Papel.ORGANIZADOR
    )
    for rodada in range(RODADAS):
        evento = eventos.criar_evento(
            organizador, dados_evento(nome=f"Rajada {rodada}", lotacao=str(LOTACAO))
        )
        eventos.publicar_evento(organizador, evento.id_publico)

        resultados = _disputar(evento.id_publico)

        assert len(resultados) == COMPRAS_SIMULTANEAS, f"rodada {rodada}: thread presa"
        assert resultados.count("ok") == LOTACAO, f"rodada {rodada}: {resultados}"
        assert resultados.count("esgotado") == COMPRAS_SIMULTANEAS - LOTACAO
        assert Ingresso.objects.filter(evento=evento).count() == LOTACAO
        assert compras.vagas_ocupadas(evento) == LOTACAO


@pytest.mark.django_db(transaction=True)
def test_editar_lotacao_concorrente_com_compras():
    """Edição de lotação para baixo disputando com compras: nunca ocupadas > lotação (R03, R07)."""
    from dominio.excecoes import ValidacaoError

    organizador = Usuario.objects.create_user(
        "org.edicao@example.com", "x" * 10, nome="Org", papel=Usuario.Papel.ORGANIZADOR
    )
    for rodada in range(5):
        evento = eventos.criar_evento(
            organizador, dados_evento(nome=f"Edição {rodada}", lotacao="10")
        )
        eventos.publicar_evento(organizador, evento.id_publico)
        barreira = threading.Barrier(16)

        def comprar(indice, evento_id=evento.id_publico, barreira=barreira):
            try:
                barreira.wait()
                compras.comprar_ingresso(
                    evento_id,
                    cartao="4000000000000001",
                    email_comprador=f"e{indice}@example.com",
                    canal="api",
                )
            except IngressosEsgotados:
                pass
            finally:
                connection.close()

        def reduzir(evento_id=evento.id_publico, barreira=barreira):
            try:
                barreira.wait()
                eventos.editar_evento(organizador, evento_id, dados_evento(lotacao="4"))
            except ValidacaoError:
                pass
            finally:
                connection.close()

        threads = [threading.Thread(target=comprar, args=(i,)) for i in range(15)]
        threads.append(threading.Thread(target=reduzir))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        evento.refresh_from_db()
        ocupadas = compras.vagas_ocupadas(evento)
        assert ocupadas <= evento.lotacao, f"rodada {rodada}: {ocupadas} > {evento.lotacao}"
        assert evento.lotacao in (4, 10)
        assert ocupadas == evento.lotacao  # 15 compras sempre esgotam o que a lotação permite
