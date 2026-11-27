"""Serviços de contas (F01): cadastro de participante.

O papel do usuário cadastrado é fixo neste módulo: nenhum dado de entrada cria organizador
(R13). As contas de organizador vêm só da seed da W0.
"""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from dominio.excecoes import EmailJaCadastrado, ValidacaoError
from dominio.models import Usuario

NOME_TAMANHO_MAXIMO = 150
EMAIL_TAMANHO_MAXIMO = 254
SENHA_TAMANHO_MINIMO = 8
SENHA_TAMANHO_MAXIMO = 128

MSG_NOME_VAZIO = "Informe o seu nome."
MSG_NOME_LONGO = "O nome pode ter no máximo 150 caracteres."
MSG_EMAIL_VAZIO = "Informe o seu e-mail."
MSG_EMAIL_INVALIDO = "Informe um e-mail válido."
MSG_EMAIL_DUPLICADO = "Já existe uma conta com este e-mail."
MSG_SENHA_VAZIA = "Informe uma senha."
MSG_SENHA_CURTA = "A senha precisa ter pelo menos 8 caracteres."
MSG_SENHA_LONGA = "A senha pode ter no máximo 128 caracteres."


def _email_bem_formado(email: str) -> bool:
    if len(email) > EMAIL_TAMANHO_MAXIMO:
        return False
    try:
        validate_email(email)
    except ValidationError:
        return False
    return True


def cadastrar_participante(nome, email, senha) -> Usuario:
    """Cria uma conta de participante e a devolve.

    Lança `ValidacaoError` com todos os erros encontrados, ou `EmailJaCadastrado` quando o
    único problema é o e-mail já existir.
    """
    nome = (nome or "").strip()
    email = Usuario.normalizar_email(email)
    senha = senha or ""

    erros: dict[str, list[str]] = {}

    if not nome:
        erros["nome"] = [MSG_NOME_VAZIO]
    elif len(nome) > NOME_TAMANHO_MAXIMO:
        erros["nome"] = [MSG_NOME_LONGO]

    email_valido = False
    if not email:
        erros["email"] = [MSG_EMAIL_VAZIO]
    elif not _email_bem_formado(email):
        erros["email"] = [MSG_EMAIL_INVALIDO]
    else:
        email_valido = True

    if not senha:
        erros["senha"] = [MSG_SENHA_VAZIA]
    elif len(senha) < SENHA_TAMANHO_MINIMO:
        erros["senha"] = [MSG_SENHA_CURTA]
    elif len(senha) > SENHA_TAMANHO_MAXIMO:
        erros["senha"] = [MSG_SENHA_LONGA]

    email_duplicado = email_valido and Usuario.objects.filter(email=email).exists()
    if email_duplicado:
        erros["email"] = [MSG_EMAIL_DUPLICADO]

    if erros:
        if email_duplicado and len(erros) == 1:
            raise EmailJaCadastrado(erros)
        raise ValidacaoError(erros)

    try:
        with transaction.atomic():
            return Usuario.objects.create_user(
                email, senha, nome=nome, papel=Usuario.Papel.PARTICIPANTE
            )
    except IntegrityError as erro:
        # Duas inscrições simultâneas com o mesmo e-mail: a restrição unique decide.
        raise EmailJaCadastrado({"email": [MSG_EMAIL_DUPLICADO]}) from erro
