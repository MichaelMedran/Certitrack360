from django.urls import path

from . import views

urlpatterns = [
    path("calendario/", views.pagina, name="calendario"),
    path("calendario/eventos/", views.eventos, name="calendario_eventos"),
]
