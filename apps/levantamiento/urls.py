from django.urls import path

from . import views

urlpatterns = [
    path("fichas/", views.lista, name="fichas"),
    path("fichas/nueva/", views.nueva, name="ficha_nueva"),
    path("fichas/<int:pk>/", views.detalle, name="ficha_detalle"),
    path("fichas/<int:pk>/vista-previa/", views.vista_previa, name="ficha_vista_previa"),
    path("fichas/<int:pk>/confirmar/", views.confirmar, name="ficha_confirmar"),
    path("fichas/<int:pk>/archivo/", views.descargar_archivo, name="ficha_archivo"),
]
