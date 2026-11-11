from django.urls import path

from . import views

urlpatterns = [
    path("reportes/", views.reportes, name="reportes"),
]
