"""Contas de desenvolvimento criadas pela seed (W0).

Valores só para desenvolvimento e avaliação local; publicados no README.
"""

from django.db import transaction

from dominio.models import Usuario

SENHA_DEV = "catraca123"

CONTAS_DEV = [
    {"email": "org.a@catraca.test", "nome": "Organizadora A", "papel": Usuario.Papel.ORGANIZADOR},
    {"email": "org.b@catraca.test", "nome": "Organizador B", "papel": Usuario.Papel.ORGANIZADOR},
    {
        "email": "participante@catraca.test",
        "nome": "Participante da Seed",
        "papel": Usuario.Papel.PARTICIPANTE,
    },
]


@transaction.atomic
def executar_seed():
    """Cria ou atualiza as contas de desenvolvimento. Idempotente.

    Nome, papel e `is_active` sempre voltam aos valores de CONTAS_DEV. A senha só é gravada
    quando a conta acabou de ser criada ou quando SENHA_DEV não confere mais: se já confere,
    o hash fica como está, e as sessões abertas dessas contas continuam válidas (o Django
    invalida a sessão quando o hash da senha muda).
    """
    resultado = []
    for conta in CONTAS_DEV:
        usuario, criado = Usuario.objects.update_or_create(
            email=conta["email"],
            defaults={"nome": conta["nome"], "papel": conta["papel"], "is_active": True},
        )
        if criado or not usuario.check_password(SENHA_DEV):
            usuario.set_password(SENHA_DEV)
            usuario.save(update_fields=["password"])
        resultado.append((usuario, criado))
    return resultado
