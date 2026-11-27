from django.urls import path

from web import views
from web.views import contas, organizador

# Toda rota sob organizador/ usa a guarda organizador_requerido (ver web/acesso.py).
urlpatterns = [
    path("saude/", views.saude, name="saude"),
    path("contas/cadastro/", contas.cadastro, name="contas_cadastro"),
    path("contas/entrar/", contas.entrar, name="contas_entrar"),
    path("contas/sair/", contas.sair, name="contas_sair"),
    path("organizador/", organizador.inicio, name="organizador_inicio"),
    path("", views.inicio, name="inicio"),
]
