from django.urls import path

from . import views

urlpatterns = [
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/generar/", views.reporte_generar, name="reporte_generar"),
    path("reportes/<int:pk>/", views.reporte_detalle, name="reporte_detalle"),
    path("reportes/<int:pk>/pdf/", views.reporte_pdf, name="reporte_pdf"),
]
