import pytest
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from dominio.models import Usuario

pytestmark = pytest.mark.django_db


def test_usuario_e_o_auth_user_model():
    assert settings.AUTH_USER_MODEL == "dominio.Usuario"
    assert get_user_model() is Usuario
    assert Usuario.USERNAME_FIELD == "email"


def test_cria_participante_por_padrao_e_entra_por_email():
    u = Usuario.objects.create_user(email="Ana@Example.com", password="senha-123", nome="Ana")
    assert u.papel == Usuario.Papel.PARTICIPANTE
    assert u.email == "ana@example.com"
    assert u.check_password("senha-123")
    assert authenticate(username="ANA@example.com", password="senha-123") == u
    assert authenticate(username="ana@example.com", password="errada") is None


def test_email_unico_mesmo_com_maiusculas():
    Usuario.objects.create_user(email="bia@example.com", password="x-12345678", nome="Bia")
    with pytest.raises(IntegrityError):
        Usuario.objects.create_user(email="BIA@example.com", password="x-12345678", nome="Bia 2")


def test_papel_aceita_so_participante_ou_organizador():
    org = Usuario.objects.create_user(
        email="org@example.com", password="x-12345678", nome="Org", papel="organizador"
    )
    assert org.eh_organizador and not org.eh_participante

    invalido = Usuario(email="x@example.com", nome="X", papel="admin")
    with pytest.raises(ValidationError):
        invalido.full_clean(exclude=["password"])
    with pytest.raises(IntegrityError):
        invalido.save()
