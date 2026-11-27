"""Gateway de pagamento simulado (F03).

O resultado e o atraso dependem do final do cartão, conforme a tabela do brief. A compra grava
uma `CobrancaGateway` com o resultado sorteado e o momento em que a resposta "chega"; o worker
(`manage.py gateway_worker`, serviço `gateway` do Compose) chama `processar_cobrancas_vencidas`
a cada meia volta e aplica as respostas.

A resposta só muda ingresso pendente: `aplicar_resposta_gateway` é um único
`UPDATE … WHERE status = 'pending'` (R08, R11). Assim, uma resposta que chega depois do
cancelamento do evento (F07) não muda nada.
"""

import random
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from dominio.models import CobrancaGateway, Ingresso

# final do cartão → (aprovado, lento)
_TABELA = {
    "0001": (True, False),
    "0002": (False, False),
    "0003": (True, True),
    "0004": (False, True),
}
_PADRAO = (False, False)  # qualquer outro final: recusado, rápido

# Faixas sorteadas, com folga dentro das do brief ([2, 5] s e [30, 40] s): os rápidos respondem
# antes de 5 s, os lentos continuam pendentes aos 30 s e estão resolvidos aos 45 s.
FAIXA_RAPIDA_S = (2.0, 4.0)
FAIXA_LENTA_S = (32.0, 38.0)

LOTE = 100


class GatewaySimulado:
    """Resultado e atraso pelo final do cartão (tabela do brief)."""

    @staticmethod
    def _linha(cartao: str):
        return _TABELA.get(str(cartao)[-4:], _PADRAO)

    @classmethod
    def resultado_para(cls, cartao: str) -> bool:
        """True se o gateway aprova."""
        return cls._linha(cartao)[0]

    @classmethod
    def atraso_para(cls, cartao: str, aleatorio=random) -> timedelta:
        """Atraso sorteado na faixa do final, multiplicado por `GATEWAY_FATOR_ATRASO`.

        O fator vale 1 no modo padrão (a variável não existe no compose.yaml); só os testes o
        mudam, para não esperar os cartões lentos.
        """
        minimo, maximo = FAIXA_LENTA_S if cls._linha(cartao)[1] else FAIXA_RAPIDA_S
        segundos = aleatorio.uniform(minimo, maximo) * float(settings.GATEWAY_FATOR_ATRASO)
        return timedelta(seconds=segundos)


def aplicar_resposta_gateway(ingresso_id: int, aprovado: bool) -> bool:
    """Aplica a resposta ao ingresso se ele ainda estiver pendente. True se mudou.

    Um único UPDATE condicional: não há leitura seguida de escrita, então nem o cancelamento
    concorrente (F07) nem uma resposta repetida conseguem sobrescrever outro status.
    """
    novo = Ingresso.Status.CONFIRMADO if aprovado else Ingresso.Status.RECUSADO
    alterados = Ingresso.objects.filter(pk=ingresso_id, status=Ingresso.Status.PENDENTE).update(
        status=novo
    )
    return alterados == 1


def processar_cobrancas_vencidas(agora=None) -> int:
    """Processa as cobranças cuja resposta já "chegou". Devolve quantas processou.

    Cada cobrança é marcada como processada mesmo quando o ingresso já não estava pendente.
    `skip_locked` deixa dois workers (ou um worker e um teste) trabalharem sem se bloquear.
    """
    total = 0
    while True:
        momento = agora or timezone.now()
        with transaction.atomic():
            lote = list(
                CobrancaGateway.objects.select_for_update(skip_locked=True)
                .filter(processada_em__isnull=True, responder_em__lte=momento)
                .order_by("responder_em", "id")[:LOTE]
            )
            for cobranca in lote:
                aplicar_resposta_gateway(
                    cobranca.ingresso_id, cobranca.resultado == CobrancaGateway.Resultado.APROVADO
                )
                cobranca.processada_em = timezone.now()
                cobranca.save(update_fields=["processada_em"])
        total += len(lote)
        if len(lote) < LOTE:
            return total
