from django.urls import path

from web import views
from web.views import cancelamento, checkin, compras, contas, organizador, vitrine

# Toda rota sob organizador/ usa a guarda organizador_requerido (ver web/acesso.py).
urlpatterns = [
    path("saude/", views.saude, name="saude"),
    path("contas/cadastro/", contas.cadastro, name="contas_cadastro"),
    path("contas/entrar/", contas.entrar, name="contas_entrar"),
    path("contas/sair/", contas.sair, name="contas_sair"),
    path("organizador/", organizador.inicio, name="organizador_inicio"),
    path("organizador/eventos/novo/", organizador.novo, name="organizador_evento_novo"),
    path("organizador/eventos/<str:evento_id>/", organizador.gestao, name="organizador_gestao"),
    path(
        "organizador/eventos/<str:evento_id>/editar/",
        organizador.editar,
        name="organizador_evento_editar",
    ),
    path(
        "organizador/eventos/<str:evento_id>/publicar/",
        organizador.publicar,
        name="organizador_evento_publicar",
    ),
    path(
        "organizador/eventos/<str:evento_id>/check-in/",
        checkin.check_in,
        name="organizador_check_in",
    ),
    path(
        "organizador/eventos/<str:evento_id>/cancelar/",
        cancelamento.cancelar,
        name="organizador_evento_cancelar",
    ),
    path("eventos/<str:evento_id>/", vitrine.detalhe, name="vitrine_detalhe"),
    path("eventos/<str:evento_id>/comprar/", compras.comprar, name="vitrine_comprar"),
    path("meus-ingressos/", compras.meus_ingressos, name="meus_ingressos"),
    path("", vitrine.vitrine, name="vitrine"),
]
