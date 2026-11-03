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
    # Sprint 2 (RF-31 y RF-38): puesto opcional del colaborador (p. ej. «Asistente de Proyectos»).
    puesto = models.CharField("puesto", max_length=100, blank=True, default="")

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


class Ausencia(models.Model):
    """Ausencia registrada por gerente o admin (SDD del Sprint 2, RF-31, §6.2 y §7.6).

    Solo se usa para avisar conflictos al asignar o reasignar responsables; no bloquea nada.
    """

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="ausencias", verbose_name="colaborador")
    desde = models.DateField("desde")
    hasta = models.DateField("hasta")
    motivo = models.CharField("motivo", max_length=200)
    registrada_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="registrada por"
    )
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["desde", "hasta", "id"]
        verbose_name = "ausencia"
        verbose_name_plural = "ausencias"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hasta__gte=models.F("desde")),
                name="ausencia_rango_valido",
                violation_error_message="La fecha de fin no puede ser anterior a la fecha de inicio.",
            ),
        ]

    def __str__(self):
        return f"{self.usuario.nombre}: {self.desde:%d/%m/%Y} a {self.hasta:%d/%m/%Y} · {self.motivo}"
