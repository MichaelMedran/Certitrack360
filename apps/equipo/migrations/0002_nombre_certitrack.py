"""La plataforma pasa a llamarse «CertiTrack» (antes «CertiTrack 360»): renombra los textos ya guardados."""

from django.db import migrations

ANTES = "CertiTrack 360"
AHORA = "CertiTrack"

CAMPOS = [
    ("conocimiento", "Procedimiento", ["titulo", "contenido"]),
    ("equipo", "ActividadPlan", ["titulo", "etiqueta_recurso"]),
]


def renombrar(apps, schema_editor):
    for app, modelo, campos in CAMPOS:
        Modelo = apps.get_model(app, modelo)
        for obj in Modelo.objects.all():
            cambiados = [c for c in campos if ANTES in getattr(obj, c)]
            for c in cambiados:
                setattr(obj, c, getattr(obj, c).replace(ANTES, AHORA))
            if cambiados:
                obj.save(update_fields=cambiados)


class Migration(migrations.Migration):
    dependencies = [
        ("equipo", "0001_initial"),
        ("conocimiento", "0004_procedimientos_y_consultas"),
    ]

    operations = [migrations.RunPython(renombrar, migrations.RunPython.noop)]
