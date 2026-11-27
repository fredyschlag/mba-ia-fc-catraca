"""Worker do gateway simulado (serviço `gateway` do Compose).

A cada volta (0,5 s) processa as cobranças vencidas
(`dominio.servicos.gateway.processar_cobrancas_vencidas`). Erros de banco, como o Postgres
reiniciando, são registrados e a volta seguinte tenta de novo: as cobranças ficam no banco, então
nada se perde ao derrubar e subir o ambiente.
"""

import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import connection

from dominio.servicos.gateway import processar_cobrancas_vencidas

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
            self._uma_volta()
            volta += 1
            if voltas and volta >= voltas:
                break
            time.sleep(INTERVALO_VOLTA_S)
        logger.info("gateway_worker: encerrado")

    def _uma_volta(self):
        try:
            processadas = processar_cobrancas_vencidas()
            if processadas:
                logger.info("gateway_worker: %d cobrança(s) processada(s)", processadas)
        except Exception:  # noqa: BLE001 — o worker não pode morrer por um erro passageiro
            logger.exception("gateway_worker: erro ao processar; tenta de novo na próxima volta")
            connection.close()

    def _parar(self, signum, frame):
        self._rodando = False
