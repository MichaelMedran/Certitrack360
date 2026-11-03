"""SDD del Sprint 2, hito S2-H11 (RF-37: HU-10): modelos Procedimiento y ConsultaAsistente."""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0005_lineas_de_servicio"),
        ("conocimiento", "0003_leccionaprendida_embedding_and_more"),
        ("repositorio", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Procedimiento",
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
                ("titulo", models.CharField(max_length=200)),
                ("contenido", models.TextField()),
                ("aprobado_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("vigente", models.BooleanField(default=True)),
                ("embedding", models.JSONField(blank=True, null=True)),
                ("embedding_modelo", models.CharField(blank=True, max_length=100)),
                (
                    "aprobado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "documento",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="procedimientos",
                        to="repositorio.documentorepositorio",
                    ),
                ),
                (
                    "linea_servicio",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="procedimientos",
                        to="clientes.lineaservicio",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "procedimientos",
                "ordering": ["-aprobado_en", "titulo"],
            },
        ),
        migrations.CreateModel(
            name="ConsultaAsistente",
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
                ("pregunta", models.CharField(max_length=500)),
                ("respuesta", models.TextField(blank=True)),
                ("fuentes", models.JSONField(blank=True, default=dict)),
                ("util", models.BooleanField(blank=True, null=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consultas_asistente",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "consultas al asistente",
                "ordering": ["-creada_en", "-id"],
            },
        ),
    ]
