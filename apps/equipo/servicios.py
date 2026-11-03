"""Servicios del plan de incorporación por rol (SDD del Sprint 2, §7.12 y §8, RF-38: HU-15, Caso 28)."""
import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.conocimiento.models import Procedimiento
from apps.cuentas.models import Usuario
from apps.entregables.filtros import entero
from apps.repositorio.models import DocumentoRepositorio

from .models import ActividadPlan, AvanceActividad, Incorporacion, PlanIncorporacion

# Plan «Asistente junior de Proyectos» (2 semanas, 12 actividades — SDD §7.12)
ACTIVIDADES_JUNIOR = [
    (
        1,
        1,
        "Recorrer CertiTrack 360: inicio, tablero, calendario, avisos y buscador",
        "proc:Guía rápida de CertiTrack 360",
        "Guía rápida de CertiTrack 360",
        "Senior asignado",
        "El ingresante la marca como completada",
    ),
    (
        2,
        1,
        "Leer la política de confidencialidad y el uso de documentos anonimizados (NDA)",
        "proc:Confidencialidad y datos de clientes",
        "Confidencialidad y datos de clientes",
        "Gerente",
        "Marcada por el ingresante",
    ),
    (
        3,
        1,
        "Conocer el flujo de un entregable: estados, Poka-Yoke, adjuntos requeridos y observaciones",
        "proc:Flujo de un entregable",
        "Flujo de un entregable",
        "Senior asignado",
        "Marcada por el ingresante",
    ),
    (
        4,
        1,
        "Revisar las fichas de levantamiento de los contratos asignados (requerimientos, frecuencia, penalidades)",
        "/fichas/",
        "Fichas de levantamiento de sus contratos",
        "Senior asignado",
        "Marcada por el ingresante",
    ),
    (
        5,
        1,
        "Revisar las plantillas vigentes de los clientes asignados",
        "/repositorio/?pestana=plantillas",
        "Repositorio › plantillas del cliente",
        "Senior asignado",
        "Marcada por el ingresante",
    ),
    (
        6,
        1,
        "Revisar dos ejemplos anonimizados de entregables aprobados",
        "/repositorio/?pestana=anonimizados",
        "Repositorio › ejemplos anonimizados",
        "Senior asignado",
        "Marcada por el ingresante",
    ),
    (
        7,
        1,
        "Consultar en el asistente los errores más frecuentes de sus clientes",
        "/asistente/",
        "Asistente (lecciones aprendidas)",
        "Senior asignado",
        "Marcada por el ingresante",
    ),
    (
        8,
        2,
        "Elaborar un entregable real como responsable de apoyo, acompañado por el junior titular, hasta Revisión senior",
        "/tablero/",
        "Entregable asignado (responsable de apoyo, RF-31)",
        "Senior asignado",
        "El entregable llega a Revisión senior",
    ),
    (
        9,
        2,
        "Registrar el tiempo por etapa de ese entregable",
        "/tiempos/",
        "Sección «Tiempo» del detalle (RF-32)",
        "Senior asignado",
        "Hay registros de tiempo suyos",
    ),
    (
        10,
        2,
        "Atender una observación: registrar la acción correctiva y la evidencia",
        "/observaciones/",
        "Sección «Observaciones» del detalle (RF-25)",
        "Senior asignado",
        "Una observación suya pasa a «En corrección»",
    ),
    (
        11,
        2,
        "Registrar una entrega con cargo de recepción y el acta de conformidad",
        "/entregas/",
        "Formulario «Marcar como entregado» (RF-29)",
        "Senior asignado",
        "La entrega queda registrada",
    ),
    (
        12,
        2,
        "Reunión de cierre: dudas pendientes y confirmación del plan",
        "",
        "—",
        "Senior asignado y gerente",
        "El responsable confirma la finalización",
    ),
]

# Plan «Senior de Proyectos» (1 semana, 7 actividades — SDD §7.12: 1, 2, 4 y 5 + 3 propias de senior)
ACTIVIDADES_SENIOR = [
    ACTIVIDADES_JUNIOR[0],
    ACTIVIDADES_JUNIOR[1],
    (3, 1, ACTIVIDADES_JUNIOR[3][2], ACTIVIDADES_JUNIOR[3][3], ACTIVIDADES_JUNIOR[3][4], "Gerente", "Marcada por el ingresante"),
    (4, 1, ACTIVIDADES_JUNIOR[4][2], ACTIVIDADES_JUNIOR[4][3], ACTIVIDADES_JUNIOR[4][4], "Gerente", "Marcada por el ingresante"),
    (
        5,
        1,
        "Revisar el panel de indicadores de sus contratos",
        "/indicadores/",
        "Panel de indicadores (RF-33)",
        "Gerente",
        "Marcada por el ingresante",
    ),
    (
        6,
        1,
        "Confirmar una ficha de levantamiento de prueba",
        "/fichas/",
        "Fichas de levantamiento (RF-30)",
        "Gerente",
        "Marcada por el ingresante",
    ),
    (
        7,
        1,
        "Confirmar o rechazar una corrección",
        "/observaciones/",
        "Sección «Observaciones» del detalle (RF-25)",
        "Gerente",
        "Marcada por el ingresante",
    ),
]


def _resolver_usuario(valor, etiqueta):
    if isinstance(valor, Usuario):
        return valor
    uid = entero(valor)
    if uid is None:
        raise ValidationError(f"Falta elegir {etiqueta}.")
    u = Usuario.objects.filter(pk=uid, is_active=True).first()
    if u is None:
        raise ValidationError(f"El usuario seleccionado para {etiqueta} no existe.")
    return u


def _resolver_plan(valor):
    if isinstance(valor, PlanIncorporacion):
        return valor
    pid = entero(valor)
    if pid is None:
        raise ValidationError("Falta elegir el plan de incorporación.")
    plan = PlanIncorporacion.objects.filter(pk=pid).first()
    if plan is None:
        raise ValidationError("El plan de incorporación seleccionado no existe.")
    return plan


def _parsear_fecha(valor):
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, datetime.date):
        return valor
    if not valor:
        return timezone.localdate()
    try:
        return datetime.date.fromisoformat(str(valor).strip())
    except ValueError as exc:
        raise ValidationError("La fecha de inicio no tiene un formato válido (AAAA-MM-DD).") from exc


@transaction.atomic
def guardar_plan(autor, *, nombre, rol, puesto="", activo=True, actividades=None, plan=None):
    """Crea o actualiza un `PlanIncorporacion` y, opcionalmente, sus actividades (solo gerente y admin: §8)."""
    if not getattr(autor, "es_gerente_o_admin", False):
        raise PermissionDenied("Solo el gerente y el administrador pueden gestionar planes de incorporación.")

    nombre_limpio = (nombre or "").strip()[:150]
    rol_limpio = (rol or "").strip().upper()
    puesto_limpio = (puesto or "").strip()[:100]

    errores = []
    if not nombre_limpio:
        errores.append("Falta el nombre del plan de incorporación.")
    if rol_limpio not in Usuario.Rol.values:
        errores.append("Elija un rol válido para el plan de incorporación.")
    if errores:
        raise ValidationError(errores)

    if plan is None:
        plan = PlanIncorporacion.objects.create(
            nombre=nombre_limpio,
            rol=rol_limpio,
            puesto=puesto_limpio,
            activo=bool(activo),
            creado_por=autor,
        )
    else:
        plan.nombre = nombre_limpio
        plan.rol = rol_limpio
        plan.puesto = puesto_limpio
        plan.activo = bool(activo)
        plan.save()

    if actividades is not None:
        for idx, datos in enumerate(actividades, 1):
            titulo = (datos.get("titulo") or "").strip()[:200]
            if not titulo:
                continue
            agregar_actividad(
                autor,
                plan,
                titulo=titulo,
                semana=datos.get("semana", 1),
                orden=datos.get("orden", idx),
                descripcion=datos.get("descripcion", ""),
                documento=datos.get("documento"),
                procedimiento=datos.get("procedimiento"),
                enlace_interno=datos.get("enlace_interno", ""),
                etiqueta_recurso=datos.get("etiqueta_recurso", ""),
                rol_responsable=datos.get("rol_responsable", "Senior asignado"),
                como_se_comprueba=datos.get("como_se_comprueba", ""),
            )

    return plan


@transaction.atomic
def agregar_actividad(
    autor,
    plan,
    *,
    titulo,
    semana=1,
    orden=None,
    descripcion="",
    documento=None,
    procedimiento=None,
    enlace_interno="",
    etiqueta_recurso="",
    rol_responsable="Senior asignado",
    como_se_comprueba="",
):
    """Agrega una actividad a un plan de incorporación (solo gerente y admin: §8)."""
    if not getattr(autor, "es_gerente_o_admin", False):
        raise PermissionDenied("Solo el gerente y el administrador pueden modificar actividades de incorporación.")

    titulo_limpio = (titulo or "").strip()[:200]
    if not titulo_limpio:
        raise ValidationError("Falta el título de la actividad.")

    semana_num = entero(semana) if not isinstance(semana, int) else semana
    if semana_num is None or semana_num < 1:
        raise ValidationError("La semana de la actividad debe ser un número entero mayor o igual a 1.")

    if orden is None or orden == "":
        ultimo = plan.actividades.order_by("-orden").values_list("orden", flat=True).first() or 0
        orden_num = ultimo + 1
    else:
        orden_num = entero(orden) if not isinstance(orden, int) else orden
        if orden_num is None or orden_num < 1:
            orden_num = 1

    doc_obj = None
    if isinstance(documento, DocumentoRepositorio):
        doc_obj = documento
    elif documento not in (None, ""):
        did = entero(documento)
        if did is not None:
            doc_obj = DocumentoRepositorio.objects.filter(pk=did).first()

    proc_obj = None
    if isinstance(procedimiento, Procedimiento):
        proc_obj = procedimiento
    elif procedimiento not in (None, ""):
        pid = entero(procedimiento)
        if pid is not None:
            proc_obj = Procedimiento.objects.filter(pk=pid).first()

    enlace_limpio = (enlace_interno or "").strip()[:200]
    if enlace_limpio and not enlace_limpio.startswith("/"):
        raise ValidationError("El enlace interno debe comenzar con «/».")

    act = ActividadPlan.objects.create(
        plan=plan,
        orden=orden_num,
        semana=semana_num,
        titulo=titulo_limpio,
        descripcion=(descripcion or "").strip(),
        documento=doc_obj,
        procedimiento=proc_obj,
        enlace_interno=enlace_limpio,
        etiqueta_recurso=(etiqueta_recurso or "").strip()[:150],
        rol_responsable=(rol_responsable or "Senior asignado").strip()[:60] or "Senior asignado",
        como_se_comprueba=(como_se_comprueba or "").strip()[:255],
    )

    # Sincroniza incorporaciones en curso (no confirmadas) para que tengan el avance en PENDIENTE
    for inc in plan.incorporaciones.filter(confirmada_en__isnull=True):
        AvanceActividad.objects.get_or_create(
            incorporacion=inc,
            actividad=act,
            defaults={"estado": AvanceActividad.Estado.PENDIENTE},
        )
    return act


@transaction.atomic
def asignar_plan(plan, ingresante, responsable, fecha_inicio=None, autor=None, emitir_notificaciones=True):
    """Asigna un plan de incorporación a un ingresante creando todos sus avances en `PENDIENTE` (§7.12)."""
    if autor is not None and not getattr(autor, "es_gerente_o_admin", False):
        raise PermissionDenied("Solo el gerente y el administrador pueden asignar planes de incorporación.")

    plan_obj = _resolver_plan(plan)
    ingresante_obj = _resolver_usuario(ingresante, "el ingresante")
    responsable_obj = _resolver_usuario(responsable, "el responsable")
    fecha_obj = _parsear_fecha(fecha_inicio)

    actividades = list(plan_obj.actividades.order_by("semana", "orden", "id"))
    if not actividades:
        raise ValidationError("El plan de incorporación debe tener al menos una actividad antes de asignarse.")

    incorporacion = Incorporacion.objects.create(
        plan=plan_obj,
        ingresante=ingresante_obj,
        responsable=responsable_obj,
        fecha_inicio=fecha_obj,
    )
    AvanceActividad.objects.bulk_create(
        [
            AvanceActividad(
                incorporacion=incorporacion,
                actividad=act,
                estado=AvanceActividad.Estado.PENDIENTE,
            )
            for act in actividades
        ]
    )

    if emitir_notificaciones:
        enlace = reverse("incorporacion")
        Notificacion.objects.create(
            usuario=ingresante_obj,
            entregable=None,
            tipo=Notificacion.Tipo.INCORPORACION,
            enlace=enlace,
            mensaje=f"Se le asignó el plan de incorporación «{plan_obj.nombre}» con {responsable_obj.nombre} como responsable.",
        )
        if responsable_obj.pk != ingresante_obj.pk:
            Notificacion.objects.create(
                usuario=responsable_obj,
                entregable=None,
                tipo=Notificacion.Tipo.INCORPORACION,
                enlace=enlace,
                mensaje=f"Fue asignado como responsable de la incorporación de {ingresante_obj.nombre} («{plan_obj.nombre}»).",
            )

    return incorporacion


@transaction.atomic
def marcar_avance(avance, nuevo_estado, usuario):
    """El ingresante marca el avance de una actividad de su propia incorporación (§7.12, §8)."""
    if not getattr(usuario, "is_authenticated", False) or usuario.pk != avance.incorporacion.ingresante_id:
        raise PermissionDenied("Solo el ingresante titular puede marcar el avance de sus actividades de incorporación.")

    if avance.incorporacion.confirmada_en is not None:
        raise ValidationError("El plan de incorporación ya fue confirmado y no admite modificaciones.")

    estado_limpio = (nuevo_estado or "").strip().upper()
    if estado_limpio not in AvanceActividad.Estado.values:
        raise ValidationError("El estado de avance indicado no es válido.")

    avance.estado = estado_limpio
    avance.completada_en = timezone.now() if estado_limpio == AvanceActividad.Estado.COMPLETADA else None
    avance.save(update_fields=["estado", "completada_en", "actualizado_en"])
    return avance


@transaction.atomic
def confirmar_finalizacion(incorporacion, usuario):
    """Caso 28 (§13): solo el responsable confirma la finalización, y solo cuando todas las actividades están completadas."""
    if not getattr(usuario, "is_authenticated", False) or usuario.pk != incorporacion.responsable_id:
        raise PermissionDenied("Solo el responsable asignado puede confirmar la finalización del plan de incorporación.")

    if incorporacion.confirmada_en is not None:
        raise ValidationError("La finalización de este plan de incorporación ya fue confirmada.")

    avances = list(incorporacion.avances.all())
    if not avances:
        raise ValidationError("No se puede confirmar un plan de incorporación sin actividades.")

    pendientes = [a for a in avances if a.estado != AvanceActividad.Estado.COMPLETADA]
    if pendientes:
        n = len(pendientes)
        raise ValidationError(
            f"No se puede confirmar la finalización: aún falta(n) {n} actividad(es) por completar."
        )

    incorporacion.confirmada_por = usuario
    incorporacion.confirmada_en = timezone.now()
    incorporacion.save(update_fields=["confirmada_por", "confirmada_en"])

    Notificacion.objects.create(
        usuario=incorporacion.ingresante,
        entregable=None,
        tipo=Notificacion.Tipo.INCORPORACION,
        enlace=reverse("incorporacion"),
        mensaje=f"{usuario.nombre} confirmó la finalización de su plan de incorporación «{incorporacion.plan.nombre}».",
    )
    return incorporacion


def incorporacion_activa_de(usuario):
    """Devuelve la incorporación en curso (no confirmada) del usuario para la tarjeta de Inicio, o None."""
    if not getattr(usuario, "is_authenticated", False):
        return None
    return (
        Incorporacion.objects.filter(ingresante=usuario, confirmada_en__isnull=True)
        .select_related("plan", "responsable")
        .prefetch_related("avances__actividad__documento", "avances__actividad__procedimiento")
        .order_by("-creada_en", "-id")
        .first()
    )


@transaction.atomic
def crear_planes_iniciales(autor=None, plantilla_doc=None, ejemplo_anon_doc=None):
    """Crea o devuelve los dos planes del SDD §7.12 («Asistente junior de Proyectos» y «Senior de Proyectos»)."""
    proc_por_titulo = {p.titulo: p for p in Procedimiento.objects.filter(vigente=True)}

    def _poblar_actividades(plan, definiciones):
        if plan.actividades.exists():
            return
        for orden, semana, titulo, ref, etiqueta, resp, comprobacion in definiciones:
            proc = None
            doc = None
            enlace = ""
            if ref.startswith("proc:"):
                nombre_proc = ref.split(":", 1)[1]
                proc = proc_por_titulo.get(nombre_proc)
                if proc is None:
                    enlace = "/repositorio/?pestana=procedimientos"
            else:
                enlace = ref
            if orden == 5 and plantilla_doc is not None:
                doc = plantilla_doc
            elif orden == 6 and plan.rol == Usuario.Rol.JUNIOR and ejemplo_anon_doc is not None:
                doc = ejemplo_anon_doc
            ActividadPlan.objects.create(
                plan=plan,
                orden=orden,
                semana=semana,
                titulo=titulo,
                procedimiento=proc,
                documento=doc,
                enlace_interno=enlace if (proc is None and doc is None) else "",
                etiqueta_recurso=etiqueta,
                rol_responsable=resp,
                como_se_comprueba=comprobacion,
            )

    plan_junior, _ = PlanIncorporacion.objects.get_or_create(
        nombre="Asistente junior de Proyectos",
        defaults={
            "rol": Usuario.Rol.JUNIOR,
            "puesto": "Asistente junior de Proyectos",
            "activo": True,
            "creado_por": autor,
        },
    )
    _poblar_actividades(plan_junior, ACTIVIDADES_JUNIOR)

    plan_senior, _ = PlanIncorporacion.objects.get_or_create(
        nombre="Senior de Proyectos",
        defaults={
            "rol": Usuario.Rol.SENIOR,
            "puesto": "Senior de Proyectos",
            "activo": True,
            "creado_por": autor,
        },
    )
    _poblar_actividades(plan_senior, ACTIVIDADES_SENIOR)

    return plan_junior, plan_senior
