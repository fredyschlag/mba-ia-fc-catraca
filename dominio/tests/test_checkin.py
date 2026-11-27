"""R10: as cinco mensagens do check-in, na ordem; R13: só o dono do evento faz check-in."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from dominio.excecoes import EventoNaoEncontrado
from dominio.models import Evento, Ingresso
from dominio.servicos import compras, eventos
from dominio.servicos.checkin import ResultadoCheckIn, fazer_check_in, normalizar_codigo
from dominio.tests.conftest import dados_evento

pytestmark = pytest.mark.django_db

R = ResultadoCheckIn
NAO_CONFIRMADOS = ["pending", "declined", "cancelled", "refunded"]
TODOS_OS_STATUS = ["pending", "confirmed", "declined", "cancelled", "refunded"]


def _evento(organizador, nome="Show", publicar=True):
    evento = eventos.criar_evento(organizador, dados_evento(nome=nome, lotacao="10"))
    if publicar:
        evento = eventos.publicar_evento(organizador, evento.id_publico)
    return evento


def _ingresso(evento, status="confirmed", check_in=False):
    """Ingresso comprado pelo domínio e levado direto ao estado pedido (preparação de teste)."""
    ingresso = compras.comprar_ingresso(
        evento.id_publico, cartao="4000000000000001", email_comprador="x@example.com", canal="api"
    )
    Ingresso.objects.filter(pk=ingresso.pk).update(
        status=status, check_in_em=timezone.now() if check_in else None
    )
    ingresso.refresh_from_db()
    return ingresso


def _cancelar(evento):
    Evento.objects.filter(pk=evento.pk).update(status=Evento.Status.CANCELADO)


def _retrato():
    return list(Ingresso.objects.order_by("id").values_list("id", "status", "check_in_em"))


def test_resultado_check_in_tem_as_cinco_mensagens_exatas_na_ordem():
    assert [r.value for r in ResultadoCheckIn] == [
        "Ingresso inválido para este evento",
        "Evento cancelado",
        "Ingresso não confirmado",
        "Ingresso já utilizado",
        "Entrada liberada",
    ]
    assert str(R.ENTRADA_LIBERADA) == "Entrada liberada"


def test_codigo_inexistente_e_invalido(organizador):
    evento = _evento(organizador)
    _ingresso(evento)

    assert fazer_check_in(organizador, evento.id_publico, "ZZZZZZZZ") is R.INVALIDO


@pytest.mark.parametrize("de_quem", ["mesmo_organizador", "outro_organizador"])
def test_codigo_de_outro_evento_e_invalido(organizador, organizador_b, de_quem):
    evento = _evento(organizador)
    dono_do_outro = organizador if de_quem == "mesmo_organizador" else organizador_b
    de_outro = _ingresso(_evento(dono_do_outro, nome="Outro"))

    assert fazer_check_in(organizador, evento.id_publico, de_outro.codigo) is R.INVALIDO
    de_outro.refresh_from_db()
    assert de_outro.check_in_em is None


@pytest.mark.parametrize("check_in", [False, True])
def test_codigo_de_outro_evento_em_evento_cancelado_e_invalido(
    organizador, organizador_b, check_in
):
    evento = _evento(organizador)
    _ingresso(evento)
    _cancelar(evento)
    do_mesmo = _ingresso(_evento(organizador, nome="Outro de A"), check_in=check_in)
    de_b = _ingresso(_evento(organizador_b, nome="De B"), check_in=check_in)

    assert fazer_check_in(organizador, evento.id_publico, do_mesmo.codigo) is R.INVALIDO
    assert fazer_check_in(organizador, evento.id_publico, de_b.codigo) is R.INVALIDO


@pytest.mark.parametrize("check_in", [False, True])
@pytest.mark.parametrize("status", TODOS_OS_STATUS)
def test_evento_cancelado_vem_antes_do_status_e_do_check_in(organizador, status, check_in):
    evento = _evento(organizador)
    ingresso = _ingresso(evento, status=status, check_in=check_in)
    _cancelar(evento)
    antes = _retrato()

    assert fazer_check_in(organizador, evento.id_publico, ingresso.codigo) is R.EVENTO_CANCELADO
    assert _retrato() == antes


@pytest.mark.parametrize("check_in", [False, True])
@pytest.mark.parametrize("status", NAO_CONFIRMADOS)
def test_ingresso_nao_confirmado(organizador, status, check_in):
    evento = _evento(organizador)
    ingresso = _ingresso(evento, status=status, check_in=check_in)
    antes = _retrato()

    assert fazer_check_in(organizador, evento.id_publico, ingresso.codigo) is R.NAO_CONFIRMADO
    assert _retrato() == antes


def test_ingresso_ja_utilizado(organizador):
    evento = _evento(organizador)
    ingresso = _ingresso(evento, check_in=True)
    quando = ingresso.check_in_em

    assert fazer_check_in(organizador, evento.id_publico, ingresso.codigo) is R.JA_UTILIZADO
    ingresso.refresh_from_db()
    assert ingresso.check_in_em == quando


def test_entrada_liberada_grava_check_in_e_mantem_confirmado(organizador):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)
    outro = _ingresso(evento)
    antes = timezone.now()

    assert fazer_check_in(organizador, evento.id_publico, ingresso.codigo) is R.ENTRADA_LIBERADA

    ingresso.refresh_from_db()
    assert ingresso.status == "confirmed"
    assert ingresso.check_in_em is not None and ingresso.check_in_em >= antes
    outro.refresh_from_db()
    assert outro.check_in_em is None
    assert fazer_check_in(organizador, evento.id_publico, ingresso.codigo) is R.JA_UTILIZADO


def test_codigo_normalizado(organizador):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)

    assert normalizar_codigo(f"  {ingresso.codigo.lower()}\t ") == ingresso.codigo
    assert normalizar_codigo(None) == ""
    digitado = f"  {ingresso.codigo.lower()}  "
    assert fazer_check_in(organizador, evento.id_publico, digitado) is R.ENTRADA_LIBERADA
    assert fazer_check_in(organizador, evento.id_publico, ingresso.codigo) is R.JA_UTILIZADO


@pytest.mark.parametrize("modo", ["vazio", "none", "longo", "espaco_no_meio", "nul"])
def test_codigo_mal_formado_e_invalido(organizador, modo):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)
    codigo = {
        "vazio": "",
        "none": None,
        "longo": ingresso.codigo + "A",
        "espaco_no_meio": f"{ingresso.codigo[:4]} {ingresso.codigo[4:]}",
        "nul": ingresso.codigo[:7] + "\x00",
    }[modo]

    assert fazer_check_in(organizador, evento.id_publico, codigo) is R.INVALIDO
    ingresso.refresh_from_db()
    assert ingresso.check_in_em is None


def test_evento_em_rascunho_so_tem_codigos_invalidos(organizador):
    rascunho = _evento(organizador, nome="Rascunho", publicar=False)
    de_outro = _ingresso(_evento(organizador, nome="Publicado"))

    assert rascunho.status == "rascunho"
    assert fazer_check_in(organizador, rascunho.id_publico, "ZZZZZZZZ") is R.INVALIDO
    assert fazer_check_in(organizador, rascunho.id_publico, de_outro.codigo) is R.INVALIDO


def test_evento_de_outro_organizador_ou_inexistente_lanca_sem_efeito(organizador, organizador_b):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)
    antes = _retrato()

    with pytest.raises(EventoNaoEncontrado):
        fazer_check_in(organizador_b, evento.id_publico, ingresso.codigo)
    with pytest.raises(EventoNaoEncontrado):
        fazer_check_in(organizador, "evt_zzzzzzzz", ingresso.codigo)
    assert _retrato() == antes


def test_check_in_trava_evento_e_depois_ingresso(organizador):
    evento = _evento(organizador)
    ingresso = _ingresso(evento)

    with CaptureQueriesContext(connection) as consultas:
        fazer_check_in(organizador, evento.id_publico, ingresso.codigo)

    travas = [q["sql"] for q in consultas.captured_queries if "FOR UPDATE" in q["sql"]]
    assert len(travas) == 2
    assert '"dominio_evento"' in travas[0].split("WHERE")[0]
    assert '"dominio_ingresso"' in travas[1].split("WHERE")[0]
    escritas = [q["sql"] for q in consultas.captured_queries if q["sql"].startswith("UPDATE")]
    assert len(escritas) == 1 and "check_in_em" in escritas[0]


def test_resultados_rejeitados_nao_escrevem(organizador, organizador_b):
    evento = _evento(organizador)
    pendente = _ingresso(evento, status="pending")
    usado = _ingresso(evento, check_in=True)
    de_b = _ingresso(_evento(organizador_b, nome="De B"))
    cancelado = _evento(organizador, nome="Cancelado")
    do_cancelado = _ingresso(cancelado)
    _cancelar(cancelado)

    casos = [
        (evento, "ZZZZZZZZ", R.INVALIDO),
        (evento, de_b.codigo, R.INVALIDO),
        (cancelado, do_cancelado.codigo, R.EVENTO_CANCELADO),
        (evento, pendente.codigo, R.NAO_CONFIRMADO),
        (evento, usado.codigo, R.JA_UTILIZADO),
    ]
    for alvo, codigo, esperado in casos:
        with CaptureQueriesContext(connection) as consultas:
            assert fazer_check_in(organizador, alvo.id_publico, codigo) is esperado
        sqls = [q["sql"] for q in consultas.captured_queries]
        assert not [s for s in sqls if s.startswith(("UPDATE", "INSERT", "DELETE"))], esperado
