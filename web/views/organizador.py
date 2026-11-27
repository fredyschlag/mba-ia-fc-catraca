"""Área do organizador (F01: esqueleto; a F02 traz a lista de eventos).

Toda view deste módulo usa `organizador_requerido` como decorador mais externo; o teste
`test_rotas_do_organizador_barram_visitante_e_participante` cobra isso de cada rota.
"""

from django.shortcuts import render
from django.views.decorators.http import require_GET

from web.acesso import organizador_requerido


@organizador_requerido
@require_GET
def inicio(request):
    return render(request, "web/organizador/inicio.html")
