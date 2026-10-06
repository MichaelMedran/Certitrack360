from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class UsuarioManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Quien se crea con `createsuperuser` es el administrador técnico de la plataforma.
        extra_fields.setdefault("rol", "ADMIN")
        return super().create_superuser(username, email, password, **extra_fields)


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        JUNIOR = "JUNIOR", "Junior"
        SENIOR = "SENIOR", "Senior"
        GERENTE = "GERENTE", "Gerente de Proyectos"
        ADMIN = "ADMIN", "Administrador"

    rol = models.CharField("rol", max_length=10, choices=Rol.choices, default=Rol.JUNIOR)

    objects = UsuarioManager()

    def save(self, *args, **kwargs):
        # El panel técnico (/admin/) es solo para el rol ADMIN (SDD §11): el rol manda sobre las banderas de Django,
        # de modo que subir o bajar el rol de alguien también le da o le quita el acceso al panel.
        self.is_staff = self.is_superuser = self.rol == self.Rol.ADMIN
        super().save(*args, **kwargs)

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
