"""Worker do gateway simulado.

Na W0 é só um laço que registra batimento. A F03 completa: a cada volta, processa as
cobranças vencidas (dominio.servicos.gateway.processar_cobrancas_vencidas).
"""

import logging
import signal
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger("catraca.gateway")

INTERVALO_VOLTA_S = 0.5
INTERVALO_BATIMENTO_S = 30.0


class Command(BaseCommand):
    help = "Roda o worker do gateway de pagamento simulado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--voltas",
            type=int,
            default=0,
            help="Número de voltas antes de sair (0 = infinito; útil em testes).",
        )

    def handle(self, *args, voltas=0, **options):
        self._rodando = True
        signal.signal(signal.SIGTERM, self._parar)
        signal.signal(signal.SIGINT, self._parar)

        logger.info("gateway_worker: iniciado")
        ultimo_batimento = 0.0
        volta = 0
        while self._rodando:
            agora = time.monotonic()
            if agora - ultimo_batimento >= INTERVALO_BATIMENTO_S:
                logger.info("gateway_worker: batimento")
                ultimo_batimento = agora
            volta += 1
            if voltas and volta >= voltas:
                break
            time.sleep(INTERVALO_VOLTA_S)
        logger.info("gateway_worker: encerrado")

    def _parar(self, signum, frame):
        self._rodando = False
