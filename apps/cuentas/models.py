from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        JUNIOR = "JUNIOR", "Junior"
        SENIOR = "SENIOR", "Senior"
        GERENTE = "GERENTE", "Gerente de Proyectos"
        ADMIN = "ADMIN", "Administrador"

    rol = models.CharField("rol", max_length=10, choices=Rol.choices, default=Rol.JUNIOR)

    @property
    def nombre(self):
        return self.get_full_name() or self.username

    @property
    def es_junior(self):
        return self.rol == self.Rol.JUNIOR

    @property
    def es_senior(self):
        return self.rol == self.Rol.SENIOR

    @property
    def es_gerente_o_admin(self):
        return self.rol in (self.Rol.GERENTE, self.Rol.ADMIN)

    @property
    def puede_crear_entregables(self):
        return self.rol != self.Rol.JUNIOR

    def __str__(self):
        return self.nombre
