"""URLs só para testes: views de exemplo protegidas pelas guardas da F01.

Até a F03 nenhuma rota real usa `participante_requerido`; estas views permitem testar as
duas guardas sem depender de features futuras.
"""

from django.http import HttpResponse
from django.urls import include, path

from web.acesso import organizador_requerido, participante_requerido

CHAMADAS = []


@organizador_requerido
def so_organizador(request):
    CHAMADAS.append(("organizador", request.method))
    return HttpResponse("area-do-organizador")


@participante_requerido
def so_participante(request):
    CHAMADAS.append(("participante", request.method))
    return HttpResponse("area-do-participante")


urlpatterns = [
    path("teste/organizador/", so_organizador),
    path("teste/participante/", so_participante),
    path("", include("catraca.urls")),
]
