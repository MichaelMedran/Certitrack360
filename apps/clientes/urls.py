from django.urls import path

from . import views

urlpatterns = [
    path("administracion/", views.administracion, name="administracion"),
    path("administracion/<str:entidad>/", views.lista, name="adm_lista"),
    path("administracion/<str:entidad>/nuevo/", views.editar, name="adm_nuevo"),
    path("administracion/<str:entidad>/<int:pk>/", views.editar, name="adm_editar"),
]
