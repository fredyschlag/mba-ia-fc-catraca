"""Views gerais da web: healthcheck, página inicial e falha de CSRF.

As views de cada assunto ficam em módulos próprios deste pacote (contas, organizador…).
"""

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def saude(request):
    """Healthcheck: responde 200 se o processo atende e o banco responde."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


@require_GET
def inicio(request):
    """Página inicial provisória; a vitrine chega na F02."""
    return render(request, "web/inicio.html")


def falha_csrf(request, reason=""):
    """CSRF_FAILURE_VIEW: 403 com a página genérica, sem detalhes do motivo."""
    return render(request, "403.html", status=403)
