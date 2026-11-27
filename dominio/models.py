"""Modelos do domínio.

A W0 entrega o usuário (AUTH_USER_MODEL na migration 0001); a F02, o Evento; a F03, o
Ingresso e a CobrancaGateway, conforme docs/prd.md.
"""

import secrets

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


ALFABETO_ID_PUBLICO = "abcdefghijklmnopqrstuvwxyz0123456789"


def gerar_id_publico(prefixo: str, tamanho: int = 8) -> str:
    """`<prefixo>_` + `tamanho` caracteres de [a-z0-9], sorteados com `secrets`."""
    sufixo = "".join(secrets.choice(ALFABETO_ID_PUBLICO) for _ in range(tamanho))
    return f"{prefixo}_{sufixo}"


def gerar_id_evento() -> str:
    return gerar_id_publico("evt")


class Evento(models.Model):
    """Evento de um organizador (F02). Nasce em rascunho; só publicado vende (R02)."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        PUBLICADO = "publicado", "Publicado"
        CANCELADO = "cancelado", "Cancelado"

    id_publico = models.CharField(
        "id público", max_length=12, unique=True, default=gerar_id_evento, editable=False
    )
    organizador = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="eventos", verbose_name="organizador"
    )
    nome = models.CharField("nome", max_length=150)
    inicio = models.DateTimeField("início")
    local = models.CharField("local", max_length=200)
    lotacao = models.PositiveIntegerField("lotação")
    preco_centavos = models.PositiveIntegerField("preço em centavos")
    status = models.CharField(
        "status", max_length=20, choices=Status.choices, default=Status.RASCUNHO
    )
    criado_em = models.DateTimeField("criado em", default=timezone.now)

    class Meta:
        verbose_name = "evento"
        verbose_name_plural = "eventos"
        ordering = ["inicio", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(lotacao__gte=1), name="evento_lotacao_minima"
            ),
            models.CheckConstraint(
                condition=models.Q(preco_centavos__gt=0), name="evento_preco_positivo"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["rascunho", "publicado", "cancelado"]),
                name="evento_status_valido",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.id_publico})"

    @property
    def pode_ser_editado(self):
        """Cancelado é irreversível: não edita (R11)."""
        return self.status != self.Status.CANCELADO

    @property
    def pode_ser_publicado(self):
        return self.status == self.Status.RASCUNHO

    @property
    def pode_ser_cancelado(self):
        """Só evento publicado é cancelado (R11)."""
        return self.status == self.Status.PUBLICADO


ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gerar_id_ingresso() -> str:
    return gerar_id_publico("tkt")


def gerar_codigo_ingresso() -> str:
    """8 caracteres maiúsculos, sem I, O, 0 e 1 (fáceis de confundir no check-in)."""
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(8))


class Ingresso(models.Model):
    """Um ingresso de um evento, comprado na vitrine ou pela API (F03).

    O status é o valor da API (pending, confirmed…); o rótulo é o da interface (pendente…).
    Check-in não é status: é `check_in_em`, preenchido só pela F05.
    """

    class Status(models.TextChoices):
        PENDENTE = "pending", "pendente"
        CONFIRMADO = "confirmed", "confirmado"
        RECUSADO = "declined", "recusado"
        CANCELADO = "cancelled", "cancelado"
        ESTORNADO = "refunded", "estornado"

    class Canal(models.TextChoices):
        VITRINE = "vitrine", "vitrine"
        API = "api", "api"

    id_publico = models.CharField(
        "id público", max_length=12, unique=True, default=gerar_id_ingresso, editable=False
    )
    codigo = models.CharField("código", max_length=8, unique=True, default=gerar_codigo_ingresso)
    evento = models.ForeignKey(
        Evento, on_delete=models.PROTECT, related_name="ingressos", verbose_name="evento"
    )
    comprador = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ingressos",
        verbose_name="comprador",
    )
    email_comprador = models.EmailField("e-mail do comprador", max_length=254)
    canal = models.CharField("canal", max_length=10, choices=Canal.choices)
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.PENDENTE
    )
    valor_centavos = models.PositiveIntegerField("valor pago em centavos")
    cartao_final = models.CharField("final do cartão", max_length=4)
    check_in_em = models.DateTimeField("check-in em", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", default=timezone.now)

    class Meta:
        verbose_name = "ingresso"
        verbose_name_plural = "ingressos"
        ordering = ["id"]
        indexes = [models.Index(fields=["evento", "status"], name="ingresso_evento_status")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["pending", "confirmed", "declined", "cancelled", "refunded"]
                ),
                name="ingresso_status_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(canal__in=["vitrine", "api"]), name="ingresso_canal_valido"
            ),
            models.CheckConstraint(
                condition=models.Q(valor_centavos__gt=0), name="ingresso_valor_positivo"
            ),
            models.CheckConstraint(
                condition=models.Q(codigo__regex=r"^[A-Z0-9]{8}$"), name="ingresso_codigo_formato"
            ),
            models.CheckConstraint(
                condition=models.Q(cartao_final__regex=r"^[0-9]{4}$"),
                name="ingresso_cartao_final_4_digitos",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} ({self.id_publico}, {self.status})"


class CobrancaGateway(models.Model):
    """Pedido ao gateway simulado: resultado sorteado na compra e quando a resposta "chega"."""

    class Resultado(models.TextChoices):
        APROVADO = "aprovado", "aprovado"
        RECUSADO = "recusado", "recusado"

    ingresso = models.OneToOneField(
        Ingresso, on_delete=models.CASCADE, related_name="cobranca", verbose_name="ingresso"
    )
    resultado = models.CharField("resultado", max_length=10, choices=Resultado.choices)
    responder_em = models.DateTimeField("responder em")
    processada_em = models.DateTimeField("processada em", null=True, blank=True)
    criada_em = models.DateTimeField("criada em", default=timezone.now)

    class Meta:
        verbose_name = "cobrança do gateway"
        verbose_name_plural = "cobranças do gateway"
        indexes = [
            models.Index(
                fields=["responder_em"],
                condition=models.Q(processada_em__isnull=True),
                name="cobranca_a_processar",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(resultado__in=["aprovado", "recusado"]),
                name="cobranca_resultado_valido",
            )
        ]

    def __str__(self):
        return f"cobrança de {self.ingresso_id}: {self.resultado}"
