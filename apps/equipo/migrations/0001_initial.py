"""SDD del Sprint 2, hito S2-H12 (RF-38: HU-15): modelos de planes y avances de incorporación."""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("conocimiento", "0004_procedimientos_y_consultas"),
        ("repositorio", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanIncorporacion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=150)),
                (
                    "rol",
                    models.CharField(
                        choices=[
                            ("JUNIOR", "Junior"),
                            ("SENIOR", "Senior"),
                            ("GERENTE", "Gerente de Proyectos"),
                            ("ADMIN", "Administrador"),
                        ],
                        default="JUNIOR",
                        max_length=10,
                    ),
                ),
                ("puesto", models.CharField(blank=True, default="", max_length=100)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                (
                    "creado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "plan de incorporación",
                "verbose_name_plural": "planes de incorporación",
                "ordering": ["nombre", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ActividadPlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("orden", models.PositiveIntegerField(default=1)),
                ("semana", models.PositiveIntegerField(default=1)),
                ("titulo", models.CharField(max_length=200)),
                ("descripcion", models.TextField(blank=True)),
                ("enlace_interno", models.CharField(blank=True, max_length=200)),
                ("etiqueta_recurso", models.CharField(blank=True, max_length=150)),
                ("rol_responsable", models.CharField(default="Senior asignado", max_length=60)),
                ("como_se_comprueba", models.CharField(blank=True, max_length=255)),
                (
                    "documento",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="repositorio.documentorepositorio",
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="actividades",
                        to="equipo.planincorporacion",
                    ),
                ),
                (
                    "procedimiento",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="conocimiento.procedimiento",
                    ),
                ),
            ],
            options={
                "verbose_name": "actividad de incorporación",
                "verbose_name_plural": "actividades de incorporación",
                "ordering": ["semana", "orden", "id"],
            },
        ),
        migrations.CreateModel(
            name="Incorporacion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("fecha_inicio", models.DateField(default=django.utils.timezone.localdate)),
                ("confirmada_en", models.DateTimeField(blank=True, null=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                (
                    "confirmada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ingresante",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incorporaciones",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incorporaciones",
                        to="equipo.planincorporacion",
                    ),
                ),
                (
                    "responsable",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incorporaciones_a_cargo",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "incorporación",
                "verbose_name_plural": "incorporaciones",
                "ordering": ["-creada_en", "-id"],
            },
        ),
        migrations.CreateModel(
            name="AvanceActividad",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente"),
                            ("EN_CURSO", "En curso"),
                            ("COMPLETADA", "Completada"),
                        ],
                        default="PENDIENTE",
                        max_length=15,
                    ),
                ),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("completada_en", models.DateTimeField(blank=True, null=True)),
                (
                    "actividad",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="avances",
                        to="equipo.actividadplan",
                    ),
                ),
                (
                    "incorporacion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="avances",
                        to="equipo.incorporacion",
                    ),
                ),
            ],
            options={
                "verbose_name": "avance de actividad",
                "verbose_name_plural": "avances de actividad",
                "ordering": ["actividad__semana", "actividad__orden", "actividad__id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("incorporacion", "actividad"),
                        name="avance_actividad_unico",
                    ),
                ],
            },
        ),
    ]
