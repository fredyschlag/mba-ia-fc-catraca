import re
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from dominio.excecoes import (
    EventoCancelado,
    EventoIndisponivel,
    EventoNaoEncontrado,
    ValidacaoError,
)
from dominio.models import Evento
from dominio.servicos import eventos as srv
from dominio.tests.conftest import dados_evento, futuro

pytestmark = pytest.mark.django_db


def test_restricoes_do_evento_no_banco(organizador):
    base = {
        "organizador": organizador,
        "nome": "X",
        "inicio": timezone.now() + timedelta(days=1),
        "local": "Y",
        "lotacao": 1,
        "preco_centavos": 1,
    }
    for campo in ("lotacao", "preco_centavos"):
        with pytest.raises(IntegrityError), transaction.atomic():
            Evento.objects.create(**{**base, campo: 0})
    with pytest.raises(IntegrityError), transaction.atomic():
        Evento.objects.create(**{**base, "status": "outro"})


@pytest.mark.parametrize("preco", ["100", "100,00", "100.00", " 100,00 "])
def test_criar_evento_nasce_rascunho_com_preco_em_centavos(organizador, preco):
    evento = srv.criar_evento(organizador, dados_evento(preco=preco))
    evento.refresh_from_db()
    assert evento.status == Evento.Status.RASCUNHO
    assert evento.preco_centavos == 10000
    assert evento.organizador == organizador
    assert evento.lotacao == 2
    assert evento.nome == "Jazz no Porão"


def test_criar_evento_aceita_centavos_e_valores_tipados(organizador):
    assert srv.criar_evento(organizador, dados_evento(preco="120,5")).preco_centavos == 12050
    assert srv.criar_evento(organizador, dados_evento(preco="0,01")).preco_centavos == 1
    tipado = dados_evento(
        preco=150, lotacao=3, inicio=timezone.now() + timedelta(days=2), nome="  Com espaços  "
    )
    evento = srv.criar_evento(organizador, tipado)
    assert (evento.preco_centavos, evento.lotacao, evento.nome) == (15000, 3, "Com espaços")


def test_inicio_sem_fuso_vale_sao_paulo(organizador):
    evento = srv.criar_evento(organizador, dados_evento(inicio="2099-06-15T21:00"))
    local = timezone.localtime(evento.inicio)
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2099, 6, 15, 21, 0)
    assert local.utcoffset() == timedelta(hours=-3)
    for formato in ("2099-06-15 21:00", "2099-06-15T21:00:00", "2099-06-15 21:00:30"):
        assert srv.criar_evento(organizador, dados_evento(inicio=formato)).inicio.year == 2099


@pytest.mark.parametrize(
    ("campo", "valor", "mensagem"),
    [
        ("nome", "   ", srv.MSG_NOME_VAZIO),
        ("nome", "x" * 151, srv.MSG_NOME_LONGO),
        ("inicio", "", srv.MSG_INICIO_VAZIO),
        ("inicio", "15/06/2099 21:00", srv.MSG_INICIO_INVALIDO),
        ("inicio", "2026-01-10T20:00", srv.MSG_INICIO_PASSADO),
        ("local", "", srv.MSG_LOCAL_VAZIO),
        ("local", "x" * 201, srv.MSG_LOCAL_LONGO),
        ("lotacao", "", srv.MSG_LOTACAO_VAZIA),
        ("lotacao", "0", srv.MSG_LOTACAO_INVALIDA),
        ("lotacao", "-1", srv.MSG_LOTACAO_INVALIDA),
        ("lotacao", "2.5", srv.MSG_LOTACAO_INVALIDA),
        ("lotacao", "abc", srv.MSG_LOTACAO_INVALIDA),
        ("lotacao", "100001", srv.MSG_LOTACAO_MAXIMA),
        ("preco", "", srv.MSG_PRECO_VAZIO),
        ("preco", "abc", srv.MSG_PRECO_INVALIDO),
        ("preco", "1.000,00", srv.MSG_PRECO_INVALIDO),
        ("preco", "10,123", srv.MSG_PRECO_INVALIDO),
        ("preco", "0", srv.MSG_PRECO_NAO_POSITIVO),
        ("preco", "0,00", srv.MSG_PRECO_NAO_POSITIVO),
        ("preco", "-10", srv.MSG_PRECO_NAO_POSITIVO),
        ("preco", "1000000,01", srv.MSG_PRECO_MAXIMO),
    ],
)
def test_criar_evento_valida_campos(organizador, campo, valor, mensagem):
    with pytest.raises(ValidacaoError) as erro:
        srv.criar_evento(organizador, dados_evento(**{campo: valor}))
    assert erro.value.erros == {campo: [mensagem]}
    assert Evento.objects.count() == 0


def test_criar_evento_junta_todos_os_erros(organizador):
    with pytest.raises(ValidacaoError) as erro:
        srv.criar_evento(organizador, {"nome": "", "inicio": "", "local": "", "lotacao": ""})
    assert erro.value.erros == {
        "nome": [srv.MSG_NOME_VAZIO],
        "inicio": [srv.MSG_INICIO_VAZIO],
        "local": [srv.MSG_LOCAL_VAZIO],
        "lotacao": [srv.MSG_LOTACAO_VAZIA],
        "preco": [srv.MSG_PRECO_VAZIO],
    }


def test_criar_e_editar_rejeitam_inicio_no_passado(organizador):
    ontem = timezone.localtime(timezone.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    with pytest.raises(ValidacaoError) as erro:
        srv.criar_evento(organizador, dados_evento(inicio=ontem))
    assert erro.value.erros == {"inicio": [srv.MSG_INICIO_PASSADO]}

    evento = srv.criar_evento(organizador, dados_evento())
    with pytest.raises(ValidacaoError) as erro:
        srv.editar_evento(organizador, evento.id_publico, dados_evento(inicio=ontem, nome="Novo"))
    assert erro.value.erros == {"inicio": [srv.MSG_INICIO_PASSADO]}
    evento.refresh_from_db()
    assert evento.nome == "Jazz no Porão"


def test_editar_evento_grava_novos_valores(organizador):
    evento = srv.criar_evento(organizador, dados_evento())
    srv.publicar_evento(organizador, evento.id_publico)
    novo = dados_evento(
        nome="Jazz (edição)", inicio=futuro(40, "22:30"), local="Novo", lotacao="4", preco="120,50"
    )
    editado = srv.editar_evento(organizador, evento.id_publico, novo)
    evento.refresh_from_db()
    assert editado.pk == evento.pk
    assert (evento.nome, evento.local, evento.lotacao, evento.preco_centavos) == (
        "Jazz (edição)",
        "Novo",
        4,
        12050,
    )
    assert timezone.localtime(evento.inicio).strftime("%H:%M") == "22:30"
    assert evento.status == Evento.Status.PUBLICADO


def test_editar_evento_invalido_nao_grava(organizador):
    evento = srv.criar_evento(organizador, dados_evento())
    with pytest.raises(ValidacaoError) as erro:
        srv.editar_evento(organizador, evento.id_publico, dados_evento(nome="Y", lotacao="0"))
    assert erro.value.erros == {"lotacao": [srv.MSG_LOTACAO_INVALIDA]}
    evento.refresh_from_db()
    assert (evento.nome, evento.lotacao) == ("Jazz no Porão", 2)


def test_editar_evento_de_outro_organizador_lanca_nao_encontrado(organizador, organizador_b):
    evento = srv.criar_evento(organizador, dados_evento())
    with pytest.raises(EventoNaoEncontrado):
        srv.editar_evento(organizador_b, evento.id_publico, dados_evento(nome="Hackeado"))
    with pytest.raises(EventoNaoEncontrado):
        srv.publicar_evento(organizador_b, evento.id_publico)
    with pytest.raises(EventoNaoEncontrado):
        srv.editar_evento(organizador, "evt_naoexis", dados_evento())
    evento.refresh_from_db()
    assert (evento.nome, evento.status) == ("Jazz no Porão", Evento.Status.RASCUNHO)


def test_publicar_evento_so_a_partir_de_rascunho_e_idempotente(organizador):
    evento = srv.criar_evento(organizador, dados_evento())
    assert srv.publicar_evento(organizador, evento.id_publico).status == Evento.Status.PUBLICADO
    assert srv.publicar_evento(organizador, evento.id_publico).status == Evento.Status.PUBLICADO
    Evento.objects.filter(pk=evento.pk).update(status=Evento.Status.CANCELADO)
    with pytest.raises(EventoCancelado):
        srv.publicar_evento(organizador, evento.id_publico)
    assert Evento.objects.count() == 1


def test_eventos_do_organizador_so_os_proprios(organizador, organizador_b):
    a1 = srv.criar_evento(organizador, dados_evento(nome="A1", inicio=futuro(20)))
    a2 = srv.criar_evento(organizador, dados_evento(nome="A2", inicio=futuro(10)))
    b1 = srv.criar_evento(organizador_b, dados_evento(nome="B1"))
    assert list(srv.eventos_do_organizador(organizador)) == [a2, a1]
    assert list(srv.eventos_do_organizador(organizador_b)) == [b1]
    assert srv.evento_do_organizador(organizador, a1.id_publico) == a1
    with pytest.raises(EventoNaoEncontrado):
        srv.evento_do_organizador(organizador_b, a1.id_publico)
    with pytest.raises(EventoNaoEncontrado):
        srv.evento_do_organizador(organizador, "evt_naoexis")


def test_eventos_a_venda_so_publicados_ordenados_por_inicio(organizador, organizador_b):
    tarde = srv.criar_evento(organizador, dados_evento(nome="Tarde", inicio=futuro(30)))
    cedo = srv.criar_evento(organizador_b, dados_evento(nome="Cedo", inicio=futuro(5)))
    srv.criar_evento(organizador, dados_evento(nome="Rascunho"))
    cancelado = srv.criar_evento(organizador, dados_evento(nome="Cancelado"))
    for evento in (tarde, cedo, cancelado):
        srv.publicar_evento(evento.organizador, evento.id_publico)
    Evento.objects.filter(pk=cancelado.pk).update(status=Evento.Status.CANCELADO)
    assert list(srv.eventos_a_venda()) == [cedo, tarde]


def test_evento_a_venda_lanca_indisponivel(organizador):
    rascunho = srv.criar_evento(organizador, dados_evento())
    with pytest.raises(EventoIndisponivel):
        srv.evento_a_venda(rascunho.id_publico)
    with pytest.raises(EventoIndisponivel):
        srv.evento_a_venda("evt_naoexis")
    srv.publicar_evento(organizador, rascunho.id_publico)
    assert srv.evento_a_venda(rascunho.id_publico) == rascunho
    Evento.objects.filter(pk=rascunho.pk).update(status=Evento.Status.CANCELADO)
    with pytest.raises(EventoIndisponivel):
        srv.evento_a_venda(rascunho.id_publico)


def test_id_publico_no_formato_evt(organizador):
    ids = {srv.criar_evento(organizador, dados_evento()).id_publico for _ in range(20)}
    assert len(ids) == 20
    assert all(re.fullmatch(r"evt_[a-z0-9]{8}", i) for i in ids)


def test_criar_evento_tenta_outro_id_quando_colide(organizador, monkeypatch):
    existente = srv.criar_evento(organizador, dados_evento())
    sequencia = iter([existente.id_publico, "evt_novo0001"])
    monkeypatch.setattr(srv, "gerar_id_evento", lambda: next(sequencia))
    assert srv.criar_evento(organizador, dados_evento()).id_publico == "evt_novo0001"
