"""Modelos do domínio.

A W0 entrega só o usuário (AUTH_USER_MODEL na migration 0001). Evento, Ingresso e
CobrancaGateway chegam nas features F02 e F03, conforme docs/prd.md.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _criar(self, email, senha, **campos):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        usuario = self.model(email=email, **campos)
        usuario.set_password(senha)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **campos):
        campos.setdefault("papel", Usuario.Papel.PARTICIPANTE)
        campos.setdefault("is_staff", False)
        campos.setdefault("is_superuser", False)
        return self._criar(email, password, **campos)

    def create_superuser(self, email, password=None, **campos):
        campos.setdefault("papel", Usuario.Papel.ORGANIZADOR)
        campos["is_staff"] = True
        campos["is_superuser"] = True
        return self._criar(email, password, **campos)

    def get_by_natural_key(self, username):
        return self.get(email=Usuario.normalizar_email(username))


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Conta da Catraca. Login por e-mail; o papel separa participante de organizador."""

    class Papel(models.TextChoices):
        PARTICIPANTE = "participante", "Participante"
        ORGANIZADOR = "organizador", "Organizador"

    email = models.EmailField("e-mail", unique=True)
    nome = models.CharField("nome", max_length=150)
    papel = models.CharField(
        "papel", max_length=20, choices=Papel.choices, default=Papel.PARTICIPANTE
    )
    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("equipe", default=False)
    criado_em = models.DateTimeField("criado em", default=timezone.now)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(papel__in=["participante", "organizador"]),
                name="usuario_papel_valido",
            ),
        ]

    def __str__(self):
        return f"{self.nome} <{self.email}>"

    @staticmethod
    def normalizar_email(email):
        return (email or "").strip().lower()

    def save(self, *args, **kwargs):
        self.email = self.normalizar_email(self.email)
        super().save(*args, **kwargs)

    @property
    def eh_organizador(self):
        return self.papel == self.Papel.ORGANIZADOR

    @property
    def eh_participante(self):
        return self.papel == self.Papel.PARTICIPANTE
