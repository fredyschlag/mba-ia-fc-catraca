import pytest


@pytest.fixture(autouse=True)
def _hasher_de_senha_rapido(settings):
    """Hash de senha barato nos testes; o produto usa o hasher padrão do Django."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
