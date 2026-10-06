from django.urls import path

from . import views

urlpatterns = [path("consolidado/", views.consolidado, name="consolidado")]
