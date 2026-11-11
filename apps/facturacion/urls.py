from django.urls import path

from . import views

urlpatterns = [
    # Verificación del número de factura (RF-46)
    path("entregables/<int:pk>/factura/", views.factura, name="entregable_factura"),
]
