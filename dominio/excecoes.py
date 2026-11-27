"""Exceções do domínio.

Os serviços de `dominio.servicos` lançam estas exceções; `web` e `api_parceiros` só as
traduzem para a resposta de cada camada. As features seguintes acrescentam as suas aqui
(EventoNaoEncontrado, IngressosEsgotados etc., conforme docs/prd.md).
"""


class ErroDeDominio(Exception):
    """Base de todas as exceções de regra de negócio."""


class ValidacaoError(ErroDeDominio):
    """Dados de entrada inválidos.

    `erros` mapeia o nome do campo para a lista de mensagens daquele campo.
    """

    def __init__(self, erros: dict[str, list[str]]):
        self.erros = {campo: list(mensagens) for campo, mensagens in erros.items()}
        super().__init__(self.erros)


class EmailJaCadastrado(ValidacaoError):
    """O e-mail informado já pertence a outra conta."""


class EventoNaoEncontrado(ErroDeDominio):
    """O evento não existe ou é de outro organizador (as views respondem 404)."""


class EventoIndisponivel(ErroDeDominio):
    """O evento não existe ou não está à venda: rascunho ou cancelado (R02)."""


MSG_CARTAO_INVALIDO = "O número do cartão precisa ter 16 dígitos."
MSG_INGRESSOS_ESGOTADOS = "Ingressos esgotados"


class CartaoInvalido(ValidacaoError):
    """Número de cartão fora de 16 dígitos; a compra é rejeitada antes de criar o ingresso."""

    def __init__(self):
        super().__init__({"cartao": [MSG_CARTAO_INVALIDO]})


class IngressosEsgotados(ErroDeDominio):
    """Sem vaga disponível no evento (R07)."""

    def __init__(self):
        super().__init__(MSG_INGRESSOS_ESGOTADOS)


class IngressoNaoEncontrado(ErroDeDominio):
    """Nenhum ingresso com esse id público."""


MSG_EVENTO_CANCELADO = "Evento cancelado não pode ser alterado."
MSG_CANCELAMENTO_NAO_PERMITIDO = "Só evento publicado pode ser cancelado."


class EventoCancelado(ErroDeDominio):
    """Evento cancelado não pode ser editado nem publicado (R11)."""

    def __init__(self):
        super().__init__(MSG_EVENTO_CANCELADO)


class CancelamentoNaoPermitido(ErroDeDominio):
    """Só evento publicado pode ser cancelado (rascunho não)."""

    def __init__(self):
        super().__init__(MSG_CANCELAMENTO_NAO_PERMITIDO)
