from django.urls import path

from . import views

urlpatterns = [
    path("extraccion/nueva/", views.nueva, name="extraccion_nueva"),
    path("extraccion/<int:pk>/", views.vista, name="extraccion_vista"),
]
