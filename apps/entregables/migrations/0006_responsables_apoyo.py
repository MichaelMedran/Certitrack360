import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("entregables", "0005_versiones_y_entregas"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ResponsableApoyo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "funcion",
                    models.CharField(
                        choices=[("ELABORACION", "Elaboración"), ("REVISION", "Revisión"), ("APOYO", "Apoyo")],
                        default="ELABORACION",
                        max_length=15,
                        verbose_name="función",
                    ),
                ),
                ("fecha_limite", models.DateField(blank=True, null=True, verbose_name="fecha límite")),
                ("asignado_en", models.DateTimeField(auto_now_add=True)),
                ("activo", models.BooleanField(default=True)),
                (
                    "asignado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "entregable",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responsables_apoyo",
                        to="entregables.entregable",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="apoyos_asignados",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="persona",
                    ),
                ),
            ],
            options={
                "verbose_name": "responsable de apoyo",
                "verbose_name_plural": "responsables de apoyo",
                "ordering": ["asignado_en", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("activo", True)),
                        fields=("entregable", "usuario", "funcion"),
                        name="responsable_apoyo_activo_unico",
                    )
                ],
            },
        ),
    ]
