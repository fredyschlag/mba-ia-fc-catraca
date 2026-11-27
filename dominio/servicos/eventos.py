"""Serviços de eventos (F02): criar, editar, publicar e consultar.

Regras: R01 (dados e início no futuro, ao criar e ao editar), R02 (só publicado está à venda),
R13 (cada organizador só enxerga os próprios eventos). `evento_id` é sempre o `id_publico`.

`editar_evento` trava a linha do evento e chama `_validar_edicao`, o ponto de extensão onde a
F03 acrescenta a regra lotação × vagas ocupadas (R03) e a F07 o bloqueio de evento cancelado.
"""

import re
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from dominio.excecoes import (
    EventoCancelado,
    EventoIndisponivel,
    EventoNaoEncontrado,
    ValidacaoError,
)
from dominio.models import Evento, gerar_id_evento
from dominio.servicos.compras import validar_lotacao_contra_ocupadas

NOME_TAMANHO_MAXIMO = 150
LOCAL_TAMANHO_MAXIMO = 200
LOTACAO_MAXIMA = 100_000
PRECO_MAXIMO_CENTAVOS = 100_000_000

MSG_NOME_VAZIO = "Informe o nome do evento."
MSG_NOME_LONGO = "O nome pode ter no máximo 150 caracteres."
MSG_INICIO_VAZIO = "Informe a data e a hora de início."
MSG_INICIO_INVALIDO = "Informe a data e a hora no formato AAAA-MM-DD HH:MM."
MSG_INICIO_PASSADO = "A data de início precisa estar no futuro."
MSG_LOCAL_VAZIO = "Informe o local."
MSG_LOCAL_LONGO = "O local pode ter no máximo 200 caracteres."
MSG_LOTACAO_VAZIA = "Informe a lotação."
MSG_LOTACAO_INVALIDA = "A lotação precisa ser um número inteiro maior ou igual a 1."
MSG_LOTACAO_MAXIMA = "A lotação pode ser no máximo 100000."
MSG_PRECO_VAZIO = "Informe o preço."
MSG_PRECO_INVALIDO = "Informe o preço em reais, por exemplo 100,00."
MSG_PRECO_NAO_POSITIVO = "O preço precisa ser maior que zero."
MSG_PRECO_MAXIMO = "O preço pode ser no máximo R$ 1.000.000,00."

_FORMATOS_INICIO = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
_RE_PRECO = re.compile(r"^-?(\d+)(?:[.,](\d{1,2}))?$")
_RE_INTEIRO = re.compile(r"^-?\d+$")
_TENTATIVAS_ID = 5


# --- validação ------------------------------------------------------------------------------


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


def _ler_inicio(valor, erros):
    if isinstance(valor, datetime):
        inicio = valor
    else:
        texto = _texto(valor).strip()
        if not texto:
            erros["inicio"] = [MSG_INICIO_VAZIO]
            return None
        inicio = None
        for formato in _FORMATOS_INICIO:
            try:
                inicio = datetime.strptime(texto, formato)
                break
            except ValueError:
                continue
        if inicio is None:
            erros["inicio"] = [MSG_INICIO_INVALIDO]
            return None
    if timezone.is_naive(inicio):
        inicio = timezone.make_aware(inicio, timezone.get_default_timezone())
    if inicio <= timezone.now():
        erros["inicio"] = [MSG_INICIO_PASSADO]
        return None
    return inicio


def _ler_lotacao(valor, erros):
    if isinstance(valor, bool):
        erros["lotacao"] = [MSG_LOTACAO_INVALIDA]
        return None
    if isinstance(valor, int):
        lotacao = valor
    else:
        texto = _texto(valor).strip()
        if not texto:
            erros["lotacao"] = [MSG_LOTACAO_VAZIA]
            return None
        if not _RE_INTEIRO.match(texto):
            erros["lotacao"] = [MSG_LOTACAO_INVALIDA]
            return None
        lotacao = int(texto)
    if lotacao < 1:
        erros["lotacao"] = [MSG_LOTACAO_INVALIDA]
        return None
    if lotacao > LOTACAO_MAXIMA:
        erros["lotacao"] = [MSG_LOTACAO_MAXIMA]
        return None
    return lotacao


def converter_preco(valor) -> int:
    """Reais (texto "100", "100,00", "100.00" ou int) → centavos. `ValueError` se mal formado."""
    if isinstance(valor, bool):
        raise ValueError(valor)
    if isinstance(valor, int):
        return valor * 100
    casamento = _RE_PRECO.match(_texto(valor).strip())
    if not casamento:
        raise ValueError(valor)
    reais, centavos = casamento.group(1), (casamento.group(2) or "0").ljust(2, "0")
    total = int(reais) * 100 + int(centavos)
    return -total if _texto(valor).strip().startswith("-") else total


def _ler_preco(valor, erros):
    if not isinstance(valor, int) and not _texto(valor).strip():
        erros["preco"] = [MSG_PRECO_VAZIO]
        return None
    try:
        centavos = converter_preco(valor)
    except ValueError:
        erros["preco"] = [MSG_PRECO_INVALIDO]
        return None
    if centavos <= 0:
        erros["preco"] = [MSG_PRECO_NAO_POSITIVO]
        return None
    if centavos > PRECO_MAXIMO_CENTAVOS:
        erros["preco"] = [MSG_PRECO_MAXIMO]
        return None
    return centavos


def _ler_texto(valor, campo, vazio, longo, maximo, erros):
    texto = _texto(valor).strip()
    if not texto:
        erros[campo] = [vazio]
        return None
    if len(texto) > maximo:
        erros[campo] = [longo]
        return None
    return texto


def validar_dados(dados) -> tuple[dict, dict[str, list[str]]]:
    """Lê e valida `dados` (tabela 2.3 da spec). Devolve (valores do modelo, erros)."""
    erros: dict[str, list[str]] = {}
    valores = {
        "nome": _ler_texto(
            dados.get("nome"), "nome", MSG_NOME_VAZIO, MSG_NOME_LONGO, NOME_TAMANHO_MAXIMO, erros
        ),
        "inicio": _ler_inicio(dados.get("inicio"), erros),
        "local": _ler_texto(
            dados.get("local"),
            "local",
            MSG_LOCAL_VAZIO,
            MSG_LOCAL_LONGO,
            LOCAL_TAMANHO_MAXIMO,
            erros,
        ),
        "lotacao": _ler_lotacao(dados.get("lotacao"), erros),
        "preco_centavos": _ler_preco(dados.get("preco"), erros),
    }
    return valores, erros


# --- comandos -------------------------------------------------------------------------------


def criar_evento(organizador, dados) -> Evento:
    """Cria um evento em rascunho do `organizador` (R01, R02). Lança `ValidacaoError`."""
    valores, erros = validar_dados(dados)
    if erros:
        raise ValidacaoError(erros)
    for tentativa in range(_TENTATIVAS_ID):
        try:
            with transaction.atomic():
                return Evento.objects.create(
                    organizador=organizador,
                    id_publico=gerar_id_evento(),
                    status=Evento.Status.RASCUNHO,
                    **valores,
                )
        except IntegrityError:
            if tentativa == _TENTATIVAS_ID - 1:
                raise
    raise AssertionError("inalcançável")


def _travar_evento_do_organizador(organizador, evento_id) -> Evento:
    """`SELECT … FOR UPDATE` na linha do evento do dono. Exige transação aberta."""
    try:
        return Evento.objects.select_for_update().get(id_publico=evento_id, organizador=organizador)
    except Evento.DoesNotExist as erro:
        raise EventoNaoEncontrado(evento_id) from erro


def _validar_edicao(evento: Evento, valores: dict, erros: dict[str, list[str]]) -> None:
    """Ponto de extensão das regras de edição que dependem do estado do evento.

    Chamado com a linha do evento travada. F03: lotação ≥ vagas ocupadas (R03).
    F07: evento cancelado não pode ser alterado (R11).
    """
    if evento.status == Evento.Status.CANCELADO:
        raise EventoCancelado()
    if "lotacao" not in erros:
        validar_lotacao_contra_ocupadas(evento, valores.get("lotacao"), erros)


def editar_evento(organizador, evento_id, dados) -> Evento:
    """Edita todos os campos do evento do `organizador` (R01). Lança `ValidacaoError`."""
    with transaction.atomic():
        evento = _travar_evento_do_organizador(organizador, evento_id)
        valores, erros = validar_dados(dados)
        _validar_edicao(evento, valores, erros)
        if erros:
            raise ValidacaoError(erros)
        for campo, valor in valores.items():
            setattr(evento, campo, valor)
        evento.save(update_fields=[*valores.keys()])
        return evento


def publicar_evento(organizador, evento_id) -> Evento:
    """Rascunho → publicado (R02). Já publicado: não muda nada. Cancelado: `EventoCancelado`."""
    with transaction.atomic():
        evento = _travar_evento_do_organizador(organizador, evento_id)
        if evento.status == Evento.Status.CANCELADO:
            raise EventoCancelado()
        if evento.status == Evento.Status.RASCUNHO:
            evento.status = Evento.Status.PUBLICADO
            evento.save(update_fields=["status"])
        return evento


# --- consultas ------------------------------------------------------------------------------


def eventos_do_organizador(organizador):
    """Só os eventos do `organizador`, ordenados pelo início (R13)."""
    return Evento.objects.filter(organizador=organizador).order_by("inicio", "id")


def evento_do_organizador(organizador, evento_id) -> Evento:
    """O evento, se for do `organizador`; senão `EventoNaoEncontrado` (R13)."""
    try:
        return Evento.objects.get(id_publico=evento_id, organizador=organizador)
    except Evento.DoesNotExist as erro:
        raise EventoNaoEncontrado(evento_id) from erro


def eventos_a_venda():
    """Eventos publicados (nem rascunho nem cancelado), ordenados pelo início (R02)."""
    return Evento.objects.filter(status=Evento.Status.PUBLICADO).order_by("inicio", "id")


def evento_a_venda(evento_id) -> Evento:
    """O evento publicado com esse id; senão `EventoIndisponivel` (R02)."""
    try:
        return eventos_a_venda().get(id_publico=evento_id)
    except Evento.DoesNotExist as erro:
        raise EventoIndisponivel(evento_id) from erro


def garantir_editavel(organizador, evento_id) -> Evento:
    """O evento do `organizador`, se puder ser editado; cancelado → `EventoCancelado` (R11)."""
    evento = evento_do_organizador(organizador, evento_id)
    if not evento.pode_ser_editado:
        raise EventoCancelado()
    return evento
