from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("ingresar/", auth_views.LoginView.as_view(template_name="cuentas/login.html"), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
]
