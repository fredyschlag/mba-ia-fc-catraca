import pytest
from django.contrib.auth import authenticate
from django.db import IntegrityError

from dominio.excecoes import EmailJaCadastrado, ValidacaoError
from dominio.models import Usuario
from dominio.servicos import contas
from dominio.servicos.contas import cadastrar_participante

pytestmark = pytest.mark.django_db

SENHA = "Senha-Valida-123"


def test_cadastrar_participante_cria_participante_com_senha_em_hash():
    usuario = cadastrar_participante("Ana", "ana@example.com", SENHA)

    usuario.refresh_from_db()
    assert usuario.papel == Usuario.Papel.PARTICIPANTE
    assert not usuario.is_staff
    assert not usuario.is_superuser
    assert usuario.password != SENHA
    assert SENHA not in usuario.password
    assert usuario.check_password(SENHA)
    assert authenticate(username="ana@example.com", password=SENHA) == usuario


def test_cadastrar_participante_normaliza_email_e_nome():
    usuario = cadastrar_participante("  Ana Teste  ", "  Ana.Teste@Example.COM ", SENHA)

    assert usuario.nome == "Ana Teste"
    assert usuario.email == "ana.teste@example.com"


def test_cadastrar_participante_rejeita_email_duplicado():
    cadastrar_participante("Ana", "ana@example.com", SENHA)

    with pytest.raises(EmailJaCadastrado) as erro:
        cadastrar_participante("Outra Ana", "ANA@Example.com", "Outra-Senha-123")

    assert erro.value.erros == {"email": ["Já existe uma conta com este e-mail."]}
    assert isinstance(erro.value, ValidacaoError)
    assert Usuario.objects.count() == 1


@pytest.mark.parametrize(
    ("nome", "email", "senha", "campo", "mensagem"),
    [
        ("", "a@example.com", SENHA, "nome", "Informe o seu nome."),
        ("   ", "a@example.com", SENHA, "nome", "Informe o seu nome."),
        ("x" * 151, "a@example.com", SENHA, "nome", "O nome pode ter no máximo 150 caracteres."),
        ("Ana", "", SENHA, "email", "Informe o seu e-mail."),
        ("Ana", "ana@", SENHA, "email", "Informe um e-mail válido."),
        ("Ana", "ana teste@example.com", SENHA, "email", "Informe um e-mail válido."),
        ("Ana", "a" * 250 + "@x.com", SENHA, "email", "Informe um e-mail válido."),
        ("Ana", "a@example.com", "", "senha", "Informe uma senha."),
        (
            "Ana",
            "a@example.com",
            "1234567",
            "senha",
            "A senha precisa ter pelo menos 8 caracteres.",
        ),
        ("Ana", "a@example.com", "x" * 129, "senha", "A senha pode ter no máximo 128 caracteres."),
    ],
)
def test_cadastrar_participante_valida_campos(nome, email, senha, campo, mensagem):
    with pytest.raises(ValidacaoError) as erro:
        cadastrar_participante(nome, email, senha)

    assert erro.value.erros == {campo: [mensagem]}
    assert not isinstance(erro.value, EmailJaCadastrado)
    assert Usuario.objects.count() == 0


def test_cadastrar_participante_aceita_limites():
    usuario = cadastrar_participante("x" * 150, "limite@example.com", "x" * 8)
    assert usuario.pk is not None
    outro = cadastrar_participante("Ana", "limite2@example.com", "x" * 128)
    assert outro.pk is not None


def test_cadastrar_participante_junta_todos_os_erros():
    cadastrar_participante("Ana", "ana@example.com", SENHA)

    with pytest.raises(ValidacaoError) as erro:
        cadastrar_participante("", "ana@example.com", "curta")

    assert not isinstance(erro.value, EmailJaCadastrado)
    assert erro.value.erros == {
        "nome": ["Informe o seu nome."],
        "email": ["Já existe uma conta com este e-mail."],
        "senha": ["A senha precisa ter pelo menos 8 caracteres."],
    }
    assert Usuario.objects.count() == 1


def test_cadastrar_participante_converte_integrity_error_em_email_ja_cadastrado(monkeypatch):
    def criar_com_corrida(*args, **kwargs):
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(contas.Usuario.objects, "create_user", criar_com_corrida)

    with pytest.raises(EmailJaCadastrado) as erro:
        cadastrar_participante("Ana", "ana@example.com", SENHA)

    assert erro.value.erros == {"email": ["Já existe uma conta com este e-mail."]}
