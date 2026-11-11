from django.db import migrations

# Los cuatro ítems generales mínimos de HU-26 (criterio 1). Se copian aquí para que la migración no dependa del código.
ITEMS = (
    ("INFORMACION_COMPLETA", "La información está completa: no faltan datos, secciones ni anexos exigidos."),
    ("CONSISTENCIA", "Los datos son consistentes entre sí y con las fuentes (cifras, nombres y totales coinciden)."),
    ("FECHAS_VIGENCIA", "Las fechas son correctas y los documentos adjuntos están vigentes."),
    ("FORMATO", "El entregable respeta el formato exigido por el cliente."),
)


def crear(apps, schema_editor):
    ItemCalidad = apps.get_model("checklists", "ItemCalidad")
    for orden, (categoria, texto) in enumerate(ITEMS, start=1):
        ItemCalidad.objects.get_or_create(
            cliente=None, texto=texto, defaults={"categoria": categoria, "obligatorio": True, "orden": orden}
        )


def borrar(apps, schema_editor):
    ItemCalidad = apps.get_model("checklists", "ItemCalidad")
    ItemCalidad.objects.filter(cliente=None, texto__in=[t for _, t in ITEMS]).delete()


class Migration(migrations.Migration):
    dependencies = [("checklists", "0001_checklists")]
    operations = [migrations.RunPython(crear, borrar)]
