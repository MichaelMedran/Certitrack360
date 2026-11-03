"""Agrega puesto al usuario y el modelo Ausencia (RF-31)."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cuentas", "0002_alter_usuario_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="puesto",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="puesto"),
        ),
        migrations.CreateModel(
            name="Ausencia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("desde", models.DateField(verbose_name="desde")),
                ("hasta", models.DateField(verbose_name="hasta")),
                ("motivo", models.CharField(max_length=200, verbose_name="motivo")),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                (
                    "registrada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="registrada por",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ausencias",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="colaborador",
                    ),
                ),
            ],
            options={
                "verbose_name": "ausencia",
                "verbose_name_plural": "ausencias",
                "ordering": ["desde", "hasta", "id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("hasta__gte", models.F("desde"))),
                        name="ausencia_rango_valido",
                        violation_error_message="La fecha de fin no puede ser anterior a la fecha de inicio.",
                    ),
                ],
            },
        ),
    ]
