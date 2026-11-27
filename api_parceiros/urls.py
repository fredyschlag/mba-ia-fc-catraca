"""Rotas da API de parceiros (contrato fixo do brief), sem barra no fim."""

from django.urls import path

from api_parceiros import views

urlpatterns = [
    path("events", views.eventos, name="api-eventos"),
    path("events/<str:evento_id>/purchases", views.comprar, name="api-comprar"),
    path("tickets/<str:ticket_id>", views.ingresso, name="api-ingresso"),
]
