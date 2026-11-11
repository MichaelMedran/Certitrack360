from django.urls import path

from . import views

urlpatterns = [
    path("entregables/<int:pk>/exportar/<str:formato>/", views.exportar, name="entregable_exportar"),
]
