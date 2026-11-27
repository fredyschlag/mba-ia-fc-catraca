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
