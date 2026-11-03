"""Servicios de la ficha de levantamiento y generación de entregables (SDD del Sprint 2, RF-30 y §7.5)."""
import calendar
import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.entregables import servicios as entregables_servicios
from apps.entregables.forms import EntregableForm
from apps.entregables.models import Entregable

from .models import FichaLevantamiento, ItemFicha
from .visibilidad import puede_actualizar_documental, puede_confirmar, puede_editar_borrador

CAMPOS_ESTADO_INICIAL = (
    "id_tdr",
    "nombre_archivo_tdr",
    "requerimientos",
    "formatos",
    "frecuencia_reportes",
    "penalidades",
    "responsable",
    "documentos_disponibles",
    "documentos_faltantes",
    "formato_esperado",
    "fecha_limite",
)


def construir_estado_inicial(ficha):
    """Foto congelada de todos los campos de la ficha al momento de confirmarla (HU-06)."""
    return {
        "id_tdr": ficha.id_tdr,
        "nombre_archivo_tdr": ficha.nombre_archivo_tdr,
        "requerimientos": ficha.requerimientos,
        "formatos": ficha.formatos,
        "frecuencia_reportes": ficha.frecuencia_reportes,
        "penalidades": ficha.penalidades,
        "responsable": ficha.responsable.nombre if ficha.responsable_id else "",
        "documentos_disponibles": ficha.documentos_disponibles,
        "documentos_faltantes": ficha.documentos_faltantes,
        "formato_esperado": ficha.formato_esperado,
        "fecha_limite": ficha.fecha_limite.isoformat() if ficha.fecha_limite else None,
    }


def validar_dato_campo(item_nombre, campo_def, valor_crudo):
    """Valida un campo obligatorio de la plantilla para un ítem de la ficha y devuelve el valor normalizado en texto."""
    etiqueta = campo_def["etiqueta"]
    tipo = campo_def.get("tipo", "texto")
    if isinstance(valor_crudo, datetime.date):
        texto = valor_crudo.isoformat()
    else:
        texto = "" if valor_crudo is None else str(valor_crudo).strip()
    if not texto:
        raise ValidationError(f"En «{item_nombre}» falta completar el campo «{etiqueta}».")
    if tipo == "numero":
        try:
            Decimal(texto)
        except (InvalidOperation, ValueError):
            raise ValidationError(f"En «{item_nombre}» el campo «{etiqueta}» debe ser un número.")
    elif tipo == "fecha":
        try:
            datetime.date.fromisoformat(texto)
        except ValueError:
            raise ValidationError(f"En «{item_nombre}» el campo «{etiqueta}» debe ser una fecha válida.")
    elif tipo == "opcion":
        opciones = campo_def.get("opciones", [])
        if texto not in opciones:
            raise ValidationError(f"En «{item_nombre}» elija una opción válida para «{etiqueta}».")
    return texto


def validar_ficha(ficha):
    """Valida todos los campos obligatorios de la ficha y de sus ítems (Poka-Yoke, §7.5). Devuelve la lista de ítems."""
    errores = []
    if not ficha.contrato_id:
        errores.append("Falta elegir el contrato.")
    elif not ficha.contrato.activo or not ficha.contrato.cliente.activo:
        errores.append("El contrato elegido está dado de baja y no admite entregables.")
    if not (ficha.id_tdr or "").strip():
        errores.append("Falta el ID-TDR.")
    if not ficha.archivo_tdr or not getattr(ficha.archivo_tdr, "name", ""):
        errores.append("Falta adjuntar el archivo del TDR.")
    if not (ficha.requerimientos or "").strip():
        errores.append("Falta indicar los requerimientos del servicio.")
    if not ficha.responsable_id:
        errores.append("Falta elegir el responsable de la ficha.")

    items = list(ficha.items.select_related("plantilla", "junior", "senior").all()) if ficha.pk else []
    if not items:
        errores.append("Debe registrar al menos un entregable en la ficha.")
    juniors_contrato = set(ficha.contrato.juniors.values_list("pk", flat=True)) if ficha.contrato_id else set()

    for idx, item in enumerate(items, start=1):
        nombre = (item.nombre or "").strip()
        ref = f"«{nombre}»" if nombre else f"el entregable n.º {idx}"
        if not nombre:
            errores.append(f"Falta el nombre del entregable en la fila {idx}.")
        if not item.plantilla_id:
            errores.append(f"En {ref} falta elegir la plantilla.")
        elif ficha.contrato_id and item.plantilla.cliente_id and item.plantilla.cliente_id != ficha.contrato.cliente_id:
            errores.append(f"En {ref} la plantilla «{item.plantilla.nombre}» pertenece a otro cliente.")
        if item.frecuencia not in ItemFicha.Frecuencia.values:
            errores.append(f"En {ref} falta elegir la frecuencia.")
        if not item.primera_fecha:
            errores.append(f"En {ref} falta la primera fecha.")
        elif item.hasta and item.hasta < item.primera_fecha:
            errores.append(f"En {ref} la fecha final («Hasta») no puede ser anterior a la primera fecha.")
        elif (
            ficha.contrato_id
            and item.frecuencia != ItemFicha.Frecuencia.UNICA
            and (item.hasta or ficha.contrato.fecha_fin) < item.primera_fecha
        ):
            errores.append(f"En {ref} la primera fecha es posterior al fin del contrato.")
        if not item.junior_id:
            errores.append(f"En {ref} falta asignar un junior.")
        elif ficha.contrato_id and item.junior_id not in juniors_contrato:
            errores.append(f"En {ref} el junior {item.junior.nombre} no está asignado al contrato elegido.")
        if item.plantilla_id:
            datos_item = item.datos or {}
            for campo in item.plantilla.campos_requeridos:
                try:
                    validar_dato_campo(nombre or f"fila {idx}", campo, datos_item.get(campo["nombre"]))
                except ValidationError as exc:
                    errores.extend(exc.messages)

    if errores:
        raise ValidationError(errores)
    return items


def _sumar_meses(fecha, meses):
    total = (fecha.year * 12 + (fecha.month - 1)) + meses
    anio, mes = divmod(total, 12)
    mes += 1
    ultimo = calendar.monthrange(anio, mes)[1]
    return datetime.date(anio, mes, min(fecha.day, ultimo))


def fechas_item(item, fecha_fin_contrato=None):
    """Lista de pares (plazo, titulo) para un ItemFicha según su frecuencia (§7.5)."""
    inicio = item.primera_fecha
    fin = item.hasta or fecha_fin_contrato or item.ficha.contrato.fecha_fin
    frec = item.frecuencia
    if frec == ItemFicha.Frecuencia.UNICA:
        return [(inicio, f"{item.nombre}")]
    if fin < inicio:
        return []
    salida = []
    paso = 0
    while True:
        if frec == ItemFicha.Frecuencia.SEMANAL:
            fecha = inicio + datetime.timedelta(days=7 * paso)
            titulo = f"{item.nombre} — {fecha:%Y-%m-%d}"
        elif frec == ItemFicha.Frecuencia.QUINCENAL:
            fecha = inicio + datetime.timedelta(days=15 * paso)
            titulo = f"{item.nombre} — {fecha:%Y-%m-%d}"
        elif frec == ItemFicha.Frecuencia.MENSUAL:
            fecha = _sumar_meses(inicio, paso)
            titulo = f"{item.nombre} — {fecha:%Y-%m}"
        elif frec == ItemFicha.Frecuencia.TRIMESTRAL:
            fecha = _sumar_meses(inicio, 3 * paso)
            trimestre = (fecha.month - 1) // 3 + 1
            titulo = f"{item.nombre} — {fecha.year}-T{trimestre}"
        else:
            break
        if fecha > fin:
            break
        salida.append((fecha, titulo))
        paso += 1
    return salida


def calcular_vista_previa(ficha, excluidos=None, incluidos=None, hoy=None):
    """Calcula los entregables que generaría la ficha, descartando fechas pasadas y aplicando exclusiones."""
    items = validar_ficha(ficha)
    hoy = hoy or timezone.localdate()
    excluidos_set = {str(x).strip() for x in (excluidos or []) if str(x).strip() != ""}
    incluidos_set = (
        {str(x).strip() for x in incluidos if str(x).strip() != ""} if incluidos is not None else None
    )

    todas = []
    entregables = []
    excluidas = []
    omitidas = 0
    indice = 0

    for item in items:
        item.ficha = ficha
        senior = item.senior or ficha.contrato.senior_responsable
        for plazo, titulo in fechas_item(item, ficha.contrato.fecha_fin):
            if plazo < hoy:
                omitidas += 1
                continue
            clave = f"{item.pk}:{plazo.isoformat()}"
            entrada = {
                "indice": indice,
                "clave": clave,
                "item": item,
                "titulo": titulo,
                "plazo": plazo,
                "junior": item.junior,
                "senior": senior,
                "plantilla": item.plantilla,
                "datos": dict(item.datos or {}),
            }
            todas.append(entrada)
            identificadores = {str(indice), clave, plazo.isoformat(), titulo}
            indice += 1
            if incluidos_set is not None and not (identificadores & incluidos_set):
                excluidas.append(entrada)
                continue
            if identificadores & excluidos_set:
                excluidas.append(entrada)
                continue
            entregables.append(entrada)

    return {
        "entregables": entregables,
        "todas": todas,
        "omitidas": omitidas,
        "excluidas": excluidas,
        "indices_excluidos": [str(e["indice"]) for e in excluidas],
        "total": len(entregables),
        "maximo": settings.FICHA_MAX_ENTREGABLES,
        "excede_maximo": len(entregables) > settings.FICHA_MAX_ENTREGABLES,
    }


def pedir_confirmacion(ficha, usuario):
    """Avisa al senior responsable del contrato que una ficha en borrador espera su confirmación (§7.5 punto 4)."""
    if not puede_editar_borrador(usuario, ficha):
        raise PermissionDenied("No tiene permiso para pedir la confirmación de esta ficha.")
    if ficha.confirmada:
        raise ValidationError("Esta ficha ya fue confirmada.")
    return Notificacion.objects.create(
        usuario=ficha.contrato.senior_responsable,
        entregable=None,
        tipo=Notificacion.Tipo.FICHA,
        enlace=reverse("ficha_detalle", args=[ficha.pk]),
        mensaje=(
            f"La ficha de levantamiento {ficha.id_tdr} del contrato "
            f"{ficha.contrato.numero_contrato} espera su confirmación."
        )[:255],
    )


def confirmar(ficha, usuario, excluidos=None, incluidos=None, hoy=None):
    """Confirma la ficha en una transacción: congela `estado_inicial` y genera los entregables con Poka-Yoke (§7.5)."""
    if not puede_confirmar(usuario, ficha):
        raise PermissionDenied("Solo el senior responsable del contrato, el gerente y el admin pueden confirmar la ficha.")
    hoy_real = timezone.localdate()
    hoy = hoy or hoy_real
    ficha_original = ficha
    with transaction.atomic():
        ficha = (
            FichaLevantamiento.objects.select_for_update()
            .select_related("contrato__cliente", "contrato__senior_responsable", "responsable")
            .get(pk=ficha.pk)
        )
        if ficha.confirmada:
            raise ValidationError("Esta ficha ya fue confirmada.")
        previa = calcular_vista_previa(ficha, excluidos=excluidos, incluidos=incluidos, hoy=hoy)
        propuestos = previa["entregables"]
        if not propuestos:
            raise ValidationError(
                "No hay entregables por generar: todas las fechas quedaron en el pasado o fueron descartadas."
            )
        if len(propuestos) > settings.FICHA_MAX_ENTREGABLES:
            raise ValidationError(
                f"La ficha generaría {len(propuestos)} entregables y el máximo permitido por confirmación es "
                f"{settings.FICHA_MAX_ENTREGABLES}."
            )

        creados = []
        for entrada in propuestos:
            if hoy == hoy_real:
                datos_form = {
                    **entrada["datos"],
                    "contrato": ficha.contrato_id,
                    "titulo": entrada["titulo"],
                    "id_tdr": ficha.id_tdr,
                    "fecha_recepcion": hoy.isoformat(),
                    "plazo": entrada["plazo"].isoformat(),
                    "junior_asignado": entrada["junior"].pk,
                    "senior_revisor": entrada["senior"].pk,
                }
                form = EntregableForm(usuario, entrada["plantilla"], datos_form)
                if not form.is_valid():
                    mensajes = [m for errs in form.errors.values() for m in errs]
                    raise ValidationError(mensajes)
                entregable = form.guardar(usuario)
            else:
                entregable = Entregable.objects.create(
                    contrato=ficha.contrato,
                    plantilla=entrada["plantilla"],
                    titulo=entrada["titulo"],
                    datos=entrada["datos"],
                    plazo=entrada["plazo"],
                    junior_asignado=entrada["junior"],
                    senior_revisor=entrada["senior"],
                    creado_por=usuario,
                    id_tdr=ficha.id_tdr,
                    fecha_recepcion=hoy,
                )
            entregables_servicios.registrar_creacion(entregable, usuario)
            entrada["item"].entregables_generados.add(entregable)
            creados.append(entregable)

        ficha.estado = FichaLevantamiento.Estado.CONFIRMADA
        ficha.estado_inicial = construir_estado_inicial(ficha)
        ficha.confirmada_por = usuario
        ficha.confirmada_en = timezone.now()
        ficha.save(update_fields=["estado", "estado_inicial", "confirmada_por", "confirmada_en", "actualizada_en"])
        ficha_original.estado = ficha.estado
        ficha_original.estado_inicial = ficha.estado_inicial
        ficha_original.confirmada_por = ficha.confirmada_por
        ficha_original.confirmada_en = ficha.confirmada_en
        ficha_original.actualizada_en = ficha.actualizada_en
    return creados, previa["omitidas"]


def actualizar_estado_documental(
    ficha,
    usuario,
    documentos_disponibles="",
    documentos_faltantes="",
    formato_esperado="",
    fecha_limite=None,
    estado_documental=None,
):
    """Actualiza el estado documental actual de una ficha confirmada sin alterar jamás `estado_inicial` (HU-06)."""
    if not puede_actualizar_documental(usuario, ficha):
        raise PermissionDenied("No tiene permiso para actualizar el estado documental de esta ficha.")
    if not ficha.confirmada:
        raise ValidationError("La ficha aún está en borrador: edite sus datos directamente.")
    if estado_documental not in FichaLevantamiento.EstadoDocumental.values:
        raise ValidationError("Elija un estado documental válido.")
    ficha.documentos_disponibles = (documentos_disponibles or "").strip()
    ficha.documentos_faltantes = (documentos_faltantes or "").strip()
    ficha.formato_esperado = (formato_esperado or "").strip()
    ficha.fecha_limite = fecha_limite
    ficha.estado_documental = estado_documental
    ficha.save(
        update_fields=[
            "documentos_disponibles",
            "documentos_faltantes",
            "formato_esperado",
            "fecha_limite",
            "estado_documental",
            "actualizada_en",
        ]
    )
    return ficha
