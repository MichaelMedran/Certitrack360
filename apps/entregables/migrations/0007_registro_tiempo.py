"""Agrega el modelo RegistroTiempo (RF-32)."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("entregables", "0006_responsables_apoyo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistroTiempo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "etapa",
                    models.CharField(
                        choices=[
                            ("RECOPILACION", "Recopilación"),
                            ("CONSOLIDACION", "Consolidación"),
                            ("REVISION", "Revisión"),
                        ],
                        max_length=20,
                        verbose_name="etapa",
                    ),
                ),
                ("inicio", models.DateTimeField(verbose_name="inicio")),
                ("fin", models.DateTimeField(blank=True, null=True, verbose_name="fin")),
                ("cierra_etapa", models.BooleanField(default=False, verbose_name="cierra etapa")),
                ("manual", models.BooleanField(default=False, verbose_name="ajuste manual")),
                ("motivo", models.CharField(blank=True, max_length=255, verbose_name="motivo del ajuste")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                (
                    "entregable",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registros_tiempo",
                        to="entregables.entregable",
                        verbose_name="entregable",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="registros_tiempo",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="colaborador",
                    ),
                ),
            ],
            options={
                "verbose_name": "registro de tiempo",
                "verbose_name_plural": "registros de tiempo",
                "ordering": ["-inicio", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("fin__isnull", True)),
                        fields=("usuario",),
                        name="un_registro_tiempo_abierto_por_usuario",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("manual", False), models.Q(("motivo", ""), _negated=True), _connector="OR"),
                        name="tiempo_manual_con_motivo",
                    ),
                ],
            },
        ),
    ]
