from django.urls import path

from web import views

urlpatterns = [
    path("saude/", views.saude, name="saude"),
    path("", views.inicio, name="inicio"),
]
