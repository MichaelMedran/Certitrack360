"""SDD del Sprint 3, hito S3-H2 (RF-41): una etiqueta por cada línea de servicio existente, con colores distintos."""
from django.db import migrations

# Copia fija de los colores de la lista cerrada (la migración no debe cambiar si el modelo cambia).
COLORES = ("AZUL", "VERDE", "AMBAR", "ROJO", "MORADO", "TURQUESA", "ROSA", "GRIS")


def crear_etiquetas(apps, schema_editor):
    Linea = apps.get_model("clientes", "LineaServicio")
    Etiqueta = apps.get_model("etiquetas", "Etiqueta")
    ocupados = {n.casefold() for n in Etiqueta.objects.values_list("nombre", flat=True)}
    for i, linea in enumerate(Linea.objects.order_by("id")):
        if linea.nombre.casefold() in ocupados or Etiqueta.objects.filter(linea_servicio=linea).exists():
            continue
        Etiqueta.objects.create(nombre=linea.nombre[:40], color=COLORES[i % len(COLORES)], linea_servicio=linea)
        ocupados.add(linea.nombre.casefold())


def borrar_etiquetas(apps, schema_editor):
    # Solo las de línea de servicio; las personalizadas no las creó esta migración.
    apps.get_model("etiquetas", "Etiqueta").objects.filter(linea_servicio__isnull=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("etiquetas", "0001_etiqueta"),
    ]

    operations = [
        migrations.RunPython(crear_etiquetas, borrar_etiquetas),
    ]
