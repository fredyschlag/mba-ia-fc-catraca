import re

import pytest
from django.db import DataError, IntegrityError, transaction

from dominio.excecoes import (
    MSG_CARTAO_INVALIDO,
    CartaoInvalido,
    EventoIndisponivel,
    IngressoNaoEncontrado,
    IngressosEsgotados,
    ValidacaoError,
)
from dominio.models import CobrancaGateway, Evento, Ingresso
from dominio.servicos import compras, eventos
from dominio.servicos.gateway import aplicar_resposta_gateway
from dominio.tests.conftest import dados_evento

pytestmark = pytest.mark.django_db

CARTAO = "4000000000000001"


def publicado(organizador, **dados):
    evento = eventos.criar_evento(organizador, dados_evento(**dados))
    return eventos.publicar_evento(organizador, evento.id_publico)


def comprar(evento, cartao=CARTAO, email="ana@example.com", canal="vitrine", comprador=None):
    return compras.comprar_ingresso(
        evento.id_publico,
        cartao=cartao,
        email_comprador=email,
        canal=canal,
        comprador=comprador,
    )


def test_restricoes_do_ingresso_no_banco(organizador):
    evento = publicado(organizador)
    base = {
        "evento": evento,
        "email_comprador": "a@example.com",
        "canal": "vitrine",
        "valor_centavos": 100,
        "cartao_final": "0001",
    }
    invalidos = [
        {"codigo": "abcdefgh"},
        {"codigo": "ABC"},
        {"cartao_final": "4000000000000001"},
        {"status": "outro"},
        {"canal": "loja"},
        {"valor_centavos": 0},
    ]
    for extra in invalidos:
        with pytest.raises((IntegrityError, DataError)), transaction.atomic():
            Ingresso.objects.create(**{**base, **extra})
    Ingresso.objects.create(**{**base, "codigo": "ABCDEFGH"})
    with pytest.raises(IntegrityError), transaction.atomic():
        Ingresso.objects.create(**{**base, "codigo": "ABCDEFGH"})


def test_comprar_cria_pendente_com_preco_e_final_do_cartao(organizador, participante):
    evento = publicado(organizador, preco="100,00")
    ingresso = comprar(evento, email=" Ana@Example.COM ", comprador=participante)
    ingresso.refresh_from_db()
    assert ingresso.status == Ingresso.Status.PENDENTE
    assert ingresso.get_status_display() == "pendente"
    assert (ingresso.valor_centavos, ingresso.cartao_final, ingresso.canal) == (
        10000,
        "0001",
        "vitrine",
    )
    assert ingresso.email_comprador == "ana@example.com"
    assert ingresso.comprador == participante
    assert ingresso.check_in_em is None
    assert re.fullmatch(r"tkt_[a-z0-9]{8}", ingresso.id_publico)
    cobranca = ingresso.cobranca
    assert cobranca.resultado == CobrancaGateway.Resultado.APROVADO
    assert cobranca.processada_em is None
    atraso = (cobranca.responder_em - ingresso.criado_em).total_seconds()
    assert 2 <= atraso <= 4


@pytest.mark.parametrize(
    "cartao",
    [
        "123",
        "400000000000000",
        "40000000000000011",
        "400000000000000A",
        "",
        None,
        "4000 0000 0000 0001",
    ],
)
def test_cartao_invalido_nao_cria_nada(organizador, cartao):
    evento = publicado(organizador)
    with pytest.raises(CartaoInvalido) as erro:
        comprar(evento, cartao=cartao)
    assert erro.value.erros == {"cartao": [MSG_CARTAO_INVALIDO]}
    assert (Ingresso.objects.count(), CobrancaGateway.objects.count()) == (0, 0)


def test_cartao_invalido_antes_de_evento_indisponivel(organizador):
    with pytest.raises(CartaoInvalido):
        compras.comprar_ingresso(
            "evt_naoexis", cartao="123", email_comprador="a@example.com", canal="api"
        )


@pytest.mark.parametrize("email", ["", "ana@", "ana", "a" * 250 + "@x.com", None])
def test_email_invalido_nao_cria_nada(organizador, email):
    evento = publicado(organizador)
    with pytest.raises(ValidacaoError) as erro:
        comprar(evento, email=email)
    assert erro.value.erros == {"email_comprador": [compras.MSG_EMAIL_COMPRADOR_INVALIDO]}
    assert Ingresso.objects.count() == 0


def test_evento_indisponivel_nao_vende(organizador):
    rascunho = eventos.criar_evento(organizador, dados_evento())
    cancelado = publicado(organizador)
    Evento.objects.filter(pk=cancelado.pk).update(status=Evento.Status.CANCELADO)
    for evento_id in (rascunho.id_publico, cancelado.id_publico, "evt_zzzzzzzz"):
        with pytest.raises(EventoIndisponivel):
            compras.comprar_ingresso(
                evento_id, cartao=CARTAO, email_comprador="a@example.com", canal="vitrine"
            )
    assert Ingresso.objects.count() == 0


def test_sem_vaga_lanca_esgotados(organizador):
    evento = publicado(organizador, lotacao="2")
    comprar(evento)
    comprar(evento)
    with pytest.raises(IngressosEsgotados) as erro:
        comprar(evento)
    assert str(erro.value) == "Ingressos esgotados"
    assert Ingresso.objects.filter(evento=evento).count() == 2
    assert CobrancaGateway.objects.count() == 2


def test_pendente_ocupa_e_recusado_libera_vaga(organizador):
    evento = publicado(organizador, lotacao="1")
    assert compras.vagas_disponiveis(evento) == 1
    ingresso = comprar(evento, cartao="4000000000000003")
    assert (compras.vagas_ocupadas(evento), compras.vagas_disponiveis(evento)) == (1, 0)
    with pytest.raises(IngressosEsgotados):
        comprar(evento)
    assert aplicar_resposta_gateway(ingresso.pk, aprovado=False) is True
    assert (compras.vagas_ocupadas(evento), compras.vagas_disponiveis(evento)) == (0, 1)
    confirmado = comprar(evento)
    aplicar_resposta_gateway(confirmado.pk, aprovado=True)
    assert compras.vagas_disponiveis(evento) == 0


def test_vagas_disponiveis_de_cancelado_e_zero(organizador):
    evento = publicado(organizador, lotacao="5")
    for status in ("declined", "cancelled", "refunded"):
        ingresso = comprar(evento)
        Ingresso.objects.filter(pk=ingresso.pk).update(status=status)
    assert (compras.vagas_ocupadas(evento), compras.vagas_disponiveis(evento)) == (0, 5)
    evento.status = Evento.Status.CANCELADO
    assert compras.vagas_disponiveis(evento) == 0


def test_preco_gravado_nao_muda_com_preco_novo(organizador):
    evento = publicado(organizador, preco="100,00", lotacao="3")
    antigo = comprar(evento)
    eventos.editar_evento(organizador, evento.id_publico, dados_evento(preco="150,00", lotacao="3"))
    novo = comprar(evento)
    antigo.refresh_from_db()
    assert (antigo.valor_centavos, novo.valor_centavos) == (10000, 15000)


def test_lotacao_nao_fica_abaixo_das_ocupadas(organizador):
    evento = publicado(organizador, lotacao="3")
    comprar(evento)
    comprar(evento, cartao="4000000000000003")
    recusado = comprar(evento, cartao="4000000000000002")
    aplicar_resposta_gateway(recusado.pk, aprovado=False)
    with pytest.raises(ValidacaoError) as erro:
        eventos.editar_evento(organizador, evento.id_publico, dados_evento(lotacao="1"))
    assert erro.value.erros == {
        "lotacao": ["A lotação não pode ser menor que as vagas ocupadas (2)."]
    }
    evento.refresh_from_db()
    assert evento.lotacao == 3
    for lotacao in ("2", "3", "10"):
        editado = eventos.editar_evento(
            organizador, evento.id_publico, dados_evento(lotacao=lotacao)
        )
        assert editado.lotacao == int(lotacao)


def test_codigo_unico_maiusculo_de_8(organizador):
    evento = publicado(organizador, lotacao="50")
    codigos = {comprar(evento).codigo for _ in range(30)}
    assert len(codigos) == 30
    assert all(re.fullmatch(r"[A-Z0-9]{8}", c) for c in codigos)


def test_codigo_colidido_gera_outro(organizador, monkeypatch):
    evento = publicado(organizador)
    primeiro = comprar(evento)
    sequencia = iter([primeiro.codigo, "ZZZZ2222"])
    monkeypatch.setattr(compras, "gerar_codigo_ingresso", lambda: next(sequencia))
    assert comprar(evento).codigo == "ZZZZ2222"


def test_consultar_ingresso(organizador):
    ingresso = comprar(publicado(organizador), canal="api")
    assert compras.consultar_ingresso(ingresso.id_publico) == ingresso
    with pytest.raises(IngressoNaoEncontrado):
        compras.consultar_ingresso("tkt_naoexist")


def test_ingressos_do_participante_so_os_proprios(organizador, participante):
    from dominio.models import Usuario

    outro = Usuario.objects.create_user("outro@example.com", "x" * 10, nome="Outro")
    evento = publicado(organizador, lotacao="5")
    meus = [comprar(evento, comprador=participante) for _ in range(2)]
    comprar(evento, comprador=outro)
    comprar(evento, canal="api")
    assert list(compras.ingressos_do_participante(participante)) == meus[::-1]
