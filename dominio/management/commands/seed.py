from django.core.management.base import BaseCommand

from dominio.seed import executar_seed


class Command(BaseCommand):
    help = "Cria ou atualiza as contas de desenvolvimento (organizador A, B e participante)."

    def handle(self, *args, **options):
        for usuario, criado in executar_seed():
            acao = "criada" if criado else "atualizada"
            self.stdout.write(f"seed: conta {acao}: {usuario.email} ({usuario.papel})")
        self.stdout.write(self.style.SUCCESS("seed: concluída"))
