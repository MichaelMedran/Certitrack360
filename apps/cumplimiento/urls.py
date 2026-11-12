from django.urls import path

from . import views

urlpatterns = [
    path("penalidades/", views.penalidades, name="penalidades"),
    path("entregables/<int:pk>/penalidades/", views.registrar_penalidad, name="entregable_penalidad"),
    path("penalidades/<int:pk>/eliminar/", views.eliminar_penalidad, name="penalidad_eliminar"),
    path("vigencias/", views.vigencias, name="vigencias"),
    path("vigencias/<int:pk>/", views.actualizar_vigencia, name="vigencia_actualizar"),
]
