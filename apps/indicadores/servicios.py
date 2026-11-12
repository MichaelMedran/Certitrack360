"""Cálculo al momento de los indicadores de desempeño (SDD del Sprint 2, RF-33: HU-13, §7.8).

Reglas clave:
- Siempre parte de `entregables_visibles(usuario)`:
  - Junior: ve únicamente sus propios entregables y NO ve la tabla «Por responsable».
  - Senior: ve los entregables de sus contratos (`entregables_visibles`).
  - Gerente y Admin: ven todos los entregables.
- Los filtros (`desde`, `hasta`, `cliente`, `plantilla`, `responsable`) se aplican sobre `entregables_visibles` y nunca
  amplían la visibilidad. Los valores fuera de rango o mal formados se ignoran sin provocar error 500.
- Determinación de la fecha de entrega (§7.8):
  - Si el entregable tiene registros en `Entrega`, se usa la `fecha_entrega` de la última entrega registrada.
  - Para los entregables en `HECHO` cerrados antes del Sprint 2 (sin `Entrega`), se usa la fecha local del paso a `HECHO`
    en `HistorialEstado` (con respaldo en la fecha local de `actualizado_en`).
"""
import datetime
from collections import Counter, defaultdict

from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.clientes.models import Cliente, PlantillaTDR
from apps.cuentas.models import Usuario
from apps.entregables.filtros import entero
from apps.entregables.models import (
    Entrega,
    Entregable,
    HistorialEstado,
    Observacion,
    RegistroTiempo,
    TipoError,
)
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado

FORMULA_A_TIEMPO = (
    "Entregables con entrega registrada en una fecha ≤ plazo ÷ entregables entregados en el periodo."
)
FORMULA_REPROCESO = (
    "Entregables con al menos una devolución (Revisión senior → En proceso en el historial) "
    "÷ entregables que pasaron por revisión."
)
FORMULA_TIEMPO = (
    "Promedio de días entre la creación y la entrega; y, si hay registros de tiempo, horas registradas promedio."
)
FORMULA_OBSERVACIONES = "Conteo de observaciones registradas en el periodo, por tipo de error."
FORMULA_AUTOMATIZADO = (
    "Entregables del periodo cuyos datos no se digitaron a mano (generados desde una ficha de levantamiento o "
    "prellenados desde un documento) ÷ entregables del periodo."
)

TITULOS_FILTROS = [
    ("desde", "Desde"),
    ("hasta", "Hasta"),
    ("cliente", "Cliente"),
    ("plantilla", "Tipo de entregable"),
    ("responsable", "Responsable"),
]


def _fecha(valor):
    """Convierte AAAA-MM-DD en `datetime.date`, o devuelve `None` si no es válida."""
    try:
        return datetime.date.fromisoformat((valor or "").strip())
    except (TypeError, ValueError):
        return None


def _formatear_decimal(valor):
    """Formatea un número con un decimal y coma española (p. ej. `6,4`), o `—` si es `None`."""
    if valor is None:
        return "—"
    return f"{valor:.1f}".replace(".", ",")


def fecha_entrega_entregable(entregable, entregas=None, historial=None):
    """Determina la fecha de entrega de un entregable según el SDD §7.8.

    - Si tiene `Entrega`, la `fecha_entrega` de la última entrega (mayor `numero` / `id`).
    - Si está en `HECHO` sin `Entrega` (cerrado antes del Sprint 2), la fecha local del último paso a `HECHO` en
      `HistorialEstado`, o en su defecto la fecha local de `actualizado_en`.
    - Si no está entregado, devuelve `None`.
    """
    lista_entregas = entregas if entregas is not None else list(entregable.entregas.all())
    if entregable.estado != E.HECHO and not lista_entregas:
        return None
    if lista_entregas:
        ultima = max(lista_entregas, key=lambda en: (en.numero, en.pk or 0))
        return ultima.fecha_entrega
    if entregable.estado != E.HECHO:
        return None
    lista_historial = historial if historial is not None else list(entregable.historial.all())
    pasos_hecho = [h for h in lista_historial if h.estado_nuevo == E.HECHO]
    if pasos_hecho:
        ultimo_paso = max(pasos_hecho, key=lambda h: (h.fecha, h.pk or 0))
        return timezone.localdate(ultimo_paso.fecha)
    if entregable.actualizado_en:
        return timezone.localdate(entregable.actualizado_en)
    return timezone.localdate()


def _fecha_inicio_elaboracion(entregable, hoy):
    """Fecha de inicio para los días de elaboración: `fecha_recepcion` o la fecha local de `creado_en`."""
    fecha_creado = timezone.localdate(entregable.creado_en) if entregable.creado_en else hoy
    if entregable.fecha_recepcion and (entregable.fecha_recepcion != hoy or fecha_creado == hoy):
        return entregable.fecha_recepcion
    return fecha_creado


def _paso_por_revision(entregable, historial):
    """True si el entregable pasó por `VERIFICACION_SENIOR` o está en revisión, aprobado o entregado."""
    if entregable.estado in (E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA, E.HECHO):
        return True
    return any(
        h.estado_anterior == E.VERIFICACION_SENIOR or h.estado_nuevo == E.VERIFICACION_SENIOR
        for h in historial
    )


def _tuvo_reproceso(historial):
    """True si el entregable tiene al menos una devolución `VERIFICACION_SENIOR → EN_PROCESO`."""
    return any(
        h.estado_anterior == E.VERIFICACION_SENIOR and h.estado_nuevo == E.EN_PROCESO
        for h in historial
    )


def _en_periodo(fecha, desde, hasta):
    if fecha is None:
        return False
    if desde is not None and fecha < desde:
        return False
    if hasta is not None and fecha > hasta:
        return False
    return True


def opciones_filtros(usuario):
    """Opciones de los desplegables de `/indicadores/`, acotadas a lo que el usuario puede ver."""
    visibles = entregables_visibles(usuario).values("pk")
    if usuario.es_junior:
        responsables = Usuario.objects.filter(pk=usuario.pk)
    else:
        responsables = (
            Usuario.objects.filter(
                Q(entregables_asignados__in=visibles)
                | Q(entregables_a_revisar__in=visibles)
                | Q(apoyos_asignados__entregable__in=visibles, apoyos_asignados__activo=True)
            )
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
    return {
        "clientes": Cliente.objects.filter(contratos__entregables__in=visibles).distinct().order_by("nombre"),
        "plantillas": PlantillaTDR.objects.filter(entregables__in=visibles).distinct().order_by("nombre"),
        "responsables": responsables,
    }


def chips_filtros(params, activos, opciones):
    """Chips para quitar cada filtro activo conservando los demás."""
    nombres = {
        "cliente": {c.pk: c.nombre for c in opciones["clientes"]},
        "plantilla": {p.pk: p.nombre for p in opciones["plantillas"]},
        "responsable": {u.pk: u.nombre for u in opciones["responsables"]},
    }
    salida = []
    for clave, titulo in TITULOS_FILTROS:
        if clave in activos:
            resto = params.copy()
            resto.pop(clave, None)
            if clave == "plantilla":
                resto.pop("tipo_entregable", None)
            if clave in ("desde", "hasta"):
                valor = activos[clave].strftime("%d/%m/%Y")
            else:
                valor = nombres[clave].get(activos[clave], "no disponible")
            salida.append({"clave": clave, "texto": f"{titulo}: {valor}", "quitar": "?" + resto.urlencode()})
    return salida


def nota_alcance_rol(usuario):
    if usuario.es_gerente_o_admin:
        return "Calculados al momento con los registros de la plataforma. Usted ve todos los contratos y entregables."
    if usuario.es_senior:
        return "Calculados al momento con los registros de la plataforma. Usted ve los contratos a su cargo."
    return "Calculados al momento con los registros de la plataforma. Usted ve solo sus propios entregables."


def calcular_indicadores(usuario, params=None, hoy=None):
    """Calcula los cuatro indicadores de RF-33 y sus tablas de desglose sobre `entregables_visibles(usuario)`."""
    params = params or {}
    hoy = hoy or timezone.localdate()

    qs = entregables_visibles(usuario)
    activos = {}

    desde = _fecha(params.get("desde"))
    if desde is not None:
        activos["desde"] = desde

    hasta = _fecha(params.get("hasta"))
    if hasta is not None:
        activos["hasta"] = hasta

    cliente = entero(params.get("cliente"))
    if cliente is not None:
        qs = qs.filter(contrato__cliente_id=cliente)
        activos["cliente"] = cliente

    plantilla = entero(params.get("plantilla") or params.get("tipo_entregable"))
    if plantilla is not None:
        qs = qs.filter(plantilla_id=plantilla)
        activos["plantilla"] = plantilla

    responsable = entero(params.get("responsable"))
    if responsable is not None:
        qs = qs.filter(
            Q(junior_asignado_id=responsable)
            | Q(senior_revisor_id=responsable)
            | Q(responsables_apoyo__usuario_id=responsable, responsables_apoyo__activo=True)
        ).distinct()
        activos["responsable"] = responsable

    entregables_base = list(
        qs.select_related("plantilla", "junior_asignado", "contrato__cliente").prefetch_related(
            Prefetch("entregas", queryset=Entrega.objects.order_by("numero", "id")),
            Prefetch("historial", queryset=HistorialEstado.objects.order_by("fecha", "id")),
            Prefetch(
                "registros_tiempo",
                queryset=RegistroTiempo.objects.filter(fin__isnull=False).order_by("inicio", "id"),
            ),
            Prefetch("observaciones", queryset=Observacion.objects.order_by("creada_en", "id")),
        )
    )

    entregados = []
    revisados = []
    con_reproceso = []
    dias_por_entregable = {}
    horas_por_entregable = {}
    fechas_periodo = {}
    entregables_en_periodo = []

    for e in entregables_base:
        entregas_e = [en for en in e.entregas.all() if e.estado == E.HECHO]
        historial_e = list(e.historial.all())
        f_entrega = fecha_entrega_entregable(e, entregas=entregas_e, historial=historial_e) if e.estado == E.HECHO else None
        f_inicio = _fecha_inicio_elaboracion(e, hoy)
        f_periodo = f_entrega or f_inicio
        fechas_periodo[e.pk] = f_periodo

        if not _en_periodo(f_periodo, desde, hasta):
            continue

        entregables_en_periodo.append(e)

        tiempos_cerrados = list(e.registros_tiempo.all())
        if tiempos_cerrados:
            seg = sum(max(0, (r.fin - r.inicio).total_seconds()) for r in tiempos_cerrados)
            horas_por_entregable[e.pk] = seg / 3600.0

        if f_entrega is not None:
            e.fecha_entrega_calculada = f_entrega
            dias_por_entregable[e.pk] = max(0, (f_entrega - f_inicio).days)
            entregados.append(e)

        if _paso_por_revision(e, historial_e):
            revisados.append(e)
            if _tuvo_reproceso(historial_e):
                con_reproceso.append(e)

    # 1. % entregados a tiempo
    entregados_total = len(entregados)
    a_tiempo_num = sum(1 for e in entregados if e.fecha_entrega_calculada <= e.plazo)
    a_tiempo_pct = round(100 * a_tiempo_num / entregados_total) if entregados_total else None

    # 2. % con reproceso
    revisados_total = len(revisados)
    reproceso_num = len(con_reproceso)
    reproceso_pct = round(100 * reproceso_num / revisados_total) if revisados_total else None

    # 3. Tiempo promedio de elaboración (días y horas registradas)
    lista_dias = [dias_por_entregable[e.pk] for e in entregados]
    dias_promedio = round(sum(lista_dias) / len(lista_dias), 1) if lista_dias else None

    lista_horas = [horas_por_entregable[e.pk] for e in entregables_en_periodo if e.pk in horas_por_entregable]
    horas_promedio = round(sum(lista_horas) / len(lista_horas), 1) if lista_horas else None

    # Desglose por tipo de entregable (plantilla)
    grupos_plantilla = defaultdict(lambda: {"entregados": [], "todos": []})
    for e in entregables_en_periodo:
        grupos_plantilla[e.plantilla]["todos"].append(e)
    for e in entregados:
        grupos_plantilla[e.plantilla]["entregados"].append(e)

    por_plantilla = []
    for p, datos_p in grupos_plantilla.items():
        ent_p = datos_p["entregados"]
        if not ent_p and not any(x.pk in horas_por_entregable for x in datos_p["todos"]):
            continue
        n_ent = len(ent_p)
        n_ok = sum(1 for x in ent_p if x.fecha_entrega_calculada <= x.plazo)
        pct_ok = round(100 * n_ok / n_ent) if n_ent else None
        d_prom = round(sum(dias_por_entregable[x.pk] for x in ent_p) / n_ent, 1) if n_ent else None
        horas_p = [horas_por_entregable[x.pk] for x in datos_p["todos"] if x.pk in horas_por_entregable]
        h_prom = round(sum(horas_p) / len(horas_p), 1) if horas_p else None
        por_plantilla.append(
            {
                "plantilla": p,
                "nombre": p.nombre,
                "entregados": n_ent,
                "dias_promedio": d_prom,
                "dias_promedio_texto": _formatear_decimal(d_prom),
                "horas_promedio": h_prom,
                "horas_promedio_texto": _formatear_decimal(h_prom),
                "a_tiempo_num": n_ok,
                "a_tiempo_pct": pct_ok,
            }
        )
    por_plantilla.sort(key=lambda fila: (-fila["entregados"], fila["nombre"]))

    # 4. Observaciones por tipo de error en el periodo
    observaciones_periodo = []
    obs_por_junior = Counter()
    for e in entregables_base:
        f_periodo_e = fechas_periodo[e.pk]
        for obs in e.observaciones.all():
            f_obs_db = timezone.localdate(obs.creada_en) if obs.creada_en else hoy
            f_obs = f_obs_db if f_obs_db != hoy else f_periodo_e
            if _en_periodo(f_obs, desde, hasta):
                observaciones_periodo.append(obs)
                obs_por_junior[e.junior_asignado_id] += 1

    conteo_tipos = Counter(obs.tipo_error for obs in observaciones_periodo)
    etiquetas_tipo = dict(TipoError.choices)
    tope_obs = max(conteo_tipos.values(), default=0) or 1
    por_tipo_error = [
        {
            "tipo_error": codigo,
            "etiqueta": str(etiquetas_tipo.get(codigo, codigo)),
            "cantidad": cantidad,
            "porcentaje": round(100 * cantidad / tope_obs),
        }
        for codigo, cantidad in conteo_tipos.items()
        if cantidad > 0
    ]
    por_tipo_error.sort(key=lambda fila: (-fila["cantidad"], fila["etiqueta"]))

    # 5. Desglose «Por responsable» (solo para Senior, Gerente y Admin; oculto para Junior)
    mostrar_por_responsable = not usuario.es_junior
    por_responsable = []
    if mostrar_por_responsable:
        revisados_ids = {e.pk for e in revisados}
        reproceso_ids = {e.pk for e in con_reproceso}
        entregados_ids = {e.pk for e in entregados}
        juniors_map = {}
        por_j = defaultdict(list)
        for e in entregables_en_periodo:
            juniors_map[e.junior_asignado_id] = e.junior_asignado
            por_j[e.junior_asignado_id].append(e)
        for e in entregables_base:
            if obs_por_junior[e.junior_asignado_id] and e.junior_asignado_id not in juniors_map:
                juniors_map[e.junior_asignado_id] = e.junior_asignado

        for jid, junior in juniors_map.items():
            lista_j = por_j[jid]
            ent_j = [x for x in lista_j if x.pk in entregados_ids]
            rev_j = [x for x in lista_j if x.pk in revisados_ids]
            rep_j = [x for x in lista_j if x.pk in reproceso_ids]
            n_ent_j = len(ent_j)
            n_ok_j = sum(1 for x in ent_j if x.fecha_entrega_calculada <= x.plazo)
            n_rev_j = len(rev_j)
            n_rep_j = len(rep_j)
            n_obs_j = obs_por_junior[jid]
            por_responsable.append(
                {
                    "responsable": junior,
                    "nombre": junior.nombre,
                    "entregados": n_ent_j,
                    "a_tiempo_num": n_ok_j,
                    "a_tiempo_pct": round(100 * n_ok_j / n_ent_j) if n_ent_j else None,
                    "revisados": n_rev_j,
                    "reproceso_num": n_rep_j,
                    "reproceso_pct": round(100 * n_rep_j / n_rev_j) if n_rev_j else None,
                    "observaciones": n_obs_j,
                }
            )
        por_responsable.sort(key=lambda fila: (-fila["entregados"], -fila["observaciones"], fila["nombre"]))

    # 6. Información automatizada: entregables cuyos datos llegaron de una ficha o de la lectura de un documento
    ids_periodo = [e.pk for e in entregables_en_periodo]
    automatizados = set(
        Entregable.objects.filter(pk__in=ids_periodo, items_ficha__isnull=False).values_list("pk", flat=True)
    ) | set(
        Entregable.objects.filter(pk__in=ids_periodo, extracciones__aplicada_en__isnull=False).values_list("pk", flat=True)
    )
    periodo_total = len(ids_periodo)
    automatizado_num = len(automatizados)

    opciones = opciones_filtros(usuario)
    return {
        "periodo_total": periodo_total,
        "automatizado_num": automatizado_num,
        "automatizado_pct": round(100 * automatizado_num / periodo_total) if periodo_total else None,
        "formula_automatizado": FORMULA_AUTOMATIZADO,
        "filtros_activos": activos,
        "n_filtros": len(activos),
        "opciones": opciones,
        "nota_alcance": nota_alcance_rol(usuario),
        "mostrar_por_responsable": mostrar_por_responsable,
        "entregados_total": entregados_total,
        "a_tiempo_num": a_tiempo_num,
        "a_tiempo_pct": a_tiempo_pct,
        "formula_a_tiempo": FORMULA_A_TIEMPO,
        "revisados_total": revisados_total,
        "reproceso_num": reproceso_num,
        "reproceso_pct": reproceso_pct,
        "formula_reproceso": FORMULA_REPROCESO,
        "dias_promedio": dias_promedio,
        "dias_promedio_texto": _formatear_decimal(dias_promedio),
        "horas_promedio": horas_promedio,
        "horas_promedio_texto": _formatear_decimal(horas_promedio),
        "formula_tiempo": FORMULA_TIEMPO,
        "observaciones_total": len(observaciones_periodo),
        "formula_observaciones": FORMULA_OBSERVACIONES,
        "por_plantilla": por_plantilla,
        "por_tipo_error": por_tipo_error,
        "por_responsable": por_responsable,
    }
