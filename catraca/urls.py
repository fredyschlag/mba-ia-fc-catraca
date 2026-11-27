from django.urls import include, path

urlpatterns = [
    path("api/partner/", include("api_parceiros.urls")),
    path("", include("web.urls")),
]
