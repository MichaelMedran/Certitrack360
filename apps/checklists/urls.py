from django.urls import path

from . import views

urlpatterns = [
    path("checklists/", views.checklists, name="checklists"),
    path("calidad/", views.calidad, name="calidad"),
]
