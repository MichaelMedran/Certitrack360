"""Datos del consolidado del gerente (SDD RF-16): solo lectura y solo para GERENTE y ADMIN.

El control de acceso se hace aquí, en el servidor, y no depende de lo que la interfaz muestre u oculte.
Todo sale del queryset de visibilidad de `entregables`, igual que el resto de las pantallas.
"""
import datetime
from collections import Counter

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.clientes.models import Cliente, Contrato
from apps.cuentas.models import Usuario
from apps.entregables.filtros import entero
from apps.entregables.models import Entregable
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado


def _fecha(valor):
    try:
        return datetime.date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


def _resumen(filas, clave_id, clave_nombre, hoy, extra=None):
    """Una fila por cliente o contrato: total, activos, vencidos y cuántos hay en cada estado."""
    grupos = {}
    for f in filas:
        g = grupos.setdefault(f[clave_id], {
            "id": f[clave_id], "nombre": f[clave_nombre], "total": 0, "activos": 0, "vencidos": 0,
            "por_estado": dict.fromkeys(E.values, 0), **({k: f[v] for k, v in extra.items()} if extra else {}),
        })
        activo = f["estado"] != E.HECHO
        g["total"] += 1
        g["activos"] += activo
        g["vencidos"] += activo and f["plazo"] < hoy
        g["por_estado"][f["estado"]] += 1
    return sorted(grupos.values(), key=lambda g: g["nombre"])


def _carga(rol, contador):
    """Entregables activos por persona; incluye a quienes hoy no tienen ninguno."""
    ids = set(contador) | set(Usuario.objects.filter(rol=rol, is_active=True).values_list("pk", flat=True))
    personas = [{"usuario": u, "activos": contador.get(u.pk, 0)} for u in Usuario.objects.filter(pk__in=ids)]
    return sorted(personas, key=lambda p: (-p["activos"], p["usuario"].nombre))


def _filtrar(usuario, params):
    """Aplica los filtros comunes (cliente, sector, contrato, desde y hasta) sobre lo que el usuario puede ver.

    Devuelve `(queryset, activos)`; `activos` tiene solo los filtros realmente aplicados. Los valores no válidos se ignoran.
    """
    qs = entregables_visibles(usuario)
    activos = {}
    cliente = entero(params.get("cliente"))
    if cliente is not None:
        qs, activos["cliente"] = qs.filter(contrato__cliente_id=cliente), cliente
    sector = params.get("sector")
    if sector in Cliente.Sector.values:
        qs, activos["sector"] = qs.filter(contrato__cliente__sector=sector), sector
    contrato = entero(params.get("contrato"))
    if contrato is not None:
        qs, activos["contrato"] = qs.filter(contrato_id=contrato), contrato
    desde = _fecha(params.get("desde"))
    if desde:
        qs, activos["desde"] = qs.filter(plazo__gte=desde), desde
    hasta = _fecha(params.get("hasta"))
    if hasta:
        qs, activos["hasta"] = qs.filter(plazo__lte=hasta), hasta
    return qs, activos


def _exigir_gestion(usuario):
    if not getattr(usuario, "is_authenticated", False) or not usuario.es_gerente_o_admin:
        raise PermissionDenied("El consolidado es solo para el gerente y el admin.")


def datos_consolidado(usuario, params=None, hoy=None, ventana=None):
    """Arma todo lo que muestra la pantalla «Consolidado». Lanza PermissionDenied si no es gerente o admin.

    Filtros (en `params`): cliente, sector del cliente, contrato, estado, desde y hasta (rango del plazo, AAAA-MM-DD).
    Los valores no válidos se ignoran. `ventana` son los días de «próximos a vencer» (por defecto la configuración).
    """
    _exigir_gestion(usuario)
    params = params or {}
    hoy = hoy or timezone.localdate()
    ventana = settings.CONSOLIDADO_WINDOW_DAYS if ventana is None else ventana

    base, activos = _filtrar(usuario, params)
    qs = base
    estado = params.get("estado")
    if estado in E.values:
        qs, activos["estado"] = qs.filter(estado=estado), estado

    filas = list(qs.values(
        "estado", "plazo", "junior_asignado_id", "senior_revisor_id", "contrato_id", "contrato__numero_contrato",
        "contrato__cliente_id", "contrato__cliente__nombre",
    ))
    por_estado = Counter(f["estado"] for f in filas)
    vigentes = [f for f in filas if f["estado"] != E.HECHO]

    abiertos = qs.exclude(estado=E.HECHO).select_related("contrato__cliente", "junior_asignado", "senior_revisor")
    vencidos = list(abiertos.filter(plazo__lt=hoy).order_by("plazo", "id"))
    proximos = list(abiertos.filter(plazo__gte=hoy, plazo__lte=hoy + datetime.timedelta(days=ventana)).order_by("plazo", "id"))

    return {
        "filtros": activos,
        "hoy": hoy,
        "ventana_dias": ventana,
        "total": len(filas),
        "activos": len(vigentes),
        "por_estado": [{"estado": v, "etiqueta": etiqueta, "total": por_estado.get(v, 0)} for v, etiqueta in E.choices],
        "vencidos": vencidos,
        "proximos": proximos,
        "por_cliente": _resumen(filas, "contrato__cliente_id", "contrato__cliente__nombre", hoy),
        "por_contrato": _resumen(
            filas, "contrato_id", "contrato__numero_contrato", hoy, extra={"cliente": "contrato__cliente__nombre"}
        ),
        "carga_juniors": _carga(Usuario.Rol.JUNIOR, Counter(f["junior_asignado_id"] for f in vigentes)),
        "carga_seniors": _carga(Usuario.Rol.SENIOR, Counter(f["senior_revisor_id"] for f in vigentes)),
    }


def texto_filtro(activos):
    """«Filtro aplicado: Cliente: X · Sector: Banca · …», o «Sin filtros». Los gráficos lo muestran tal cual."""
    partes = []
    if "cliente" in activos:
        c = Cliente.objects.filter(pk=activos["cliente"]).first()
        partes.append(f"Cliente: {c.nombre if c else 'no disponible'}")
    if "sector" in activos:
        partes.append(f"Sector: {Cliente.Sector(activos['sector']).label}")
    if "contrato" in activos:
        c = Contrato.objects.filter(pk=activos["contrato"]).first()
        partes.append(f"Contrato: {c.numero_contrato if c else 'no disponible'}")
    if "desde" in activos:
        partes.append(f"Plazo desde {activos['desde']:%d/%m/%Y}")
    if "hasta" in activos:
        partes.append(f"Plazo hasta {activos['hasta']:%d/%m/%Y}")
    return "Filtro aplicado: " + " · ".join(partes) if partes else "Sin filtros"


def datos_graficos(usuario, params=None):
    """Cifras de los cuatro gráficos gerenciales (RF-49). Solo gerente y admin (si no, PermissionDenied).

    Salen de los registros, sin ingreso manual, y parten de `entregables_visibles`. Filtros: cliente, sector, contrato y
    rango de fechas del plazo (el estado del consolidado no aplica: los gráficos miden todo el ciclo). La fecha de
    entrega se determina igual que en los indicadores (`fecha_entrega_entregable`, SDD del Sprint 2, §7.8).
    """
    from django.db.models import Prefetch

    from apps.entregables.models import Entrega, HistorialEstado, Observacion, TipoError
    from apps.indicadores.servicios import _fecha_inicio_elaboracion, fecha_entrega_entregable

    _exigir_gestion(usuario)
    qs, activos = _filtrar(usuario, params or {})

    # 1. Entregables activos por persona (junior y senior), solo quienes tienen alguno.
    vigentes = list(qs.exclude(estado=E.HECHO).values("junior_asignado_id", "senior_revisor_id"))
    personas = []
    for campo, nombre_rol in (("junior_asignado_id", "Junior"), ("senior_revisor_id", "Senior")):
        conteo = Counter(f[campo] for f in vigentes)
        for u in Usuario.objects.filter(pk__in=conteo):
            personas.append({"nombre": u.nombre, "rol": nombre_rol, "activos": conteo[u.pk]})
    personas.sort(key=lambda p: (-p["activos"], p["nombre"], p["rol"]))

    # 2 y 3. Entregados: cumplimiento del plazo por mes y días de atención por cliente.
    entregados = qs.filter(estado=E.HECHO).select_related("contrato__cliente").prefetch_related(
        Prefetch("entregas", queryset=Entrega.objects.order_by("numero", "id")),
        Prefetch("historial", queryset=HistorialEstado.objects.order_by("fecha", "id")),
    )
    hoy = timezone.localdate()
    por_mes, por_cliente = {}, {}
    for e in entregados:
        fecha = fecha_entrega_entregable(e)
        if fecha is None:
            continue
        mes = por_mes.setdefault((fecha.year, fecha.month), {"entregados": 0, "a_tiempo": 0})
        mes["entregados"] += 1
        mes["a_tiempo"] += fecha <= e.plazo
        dias = max(0, (fecha - _fecha_inicio_elaboracion(e, hoy)).days)
        por_cliente.setdefault(e.contrato.cliente.nombre, []).append(dias)
    cumplidos = [
        {"mes": f"{m:02d}/{a}", "entregados": v["entregados"], "a_tiempo": v["a_tiempo"],
         "porcentaje": round(100 * v["a_tiempo"] / v["entregados"])}
        for (a, m), v in sorted(por_mes.items())
    ]
    atencion = sorted(
        ({"cliente": nombre, "entregados": len(dias), "dias_promedio": round(sum(dias) / len(dias), 1)}
         for nombre, dias in por_cliente.items()),
        key=lambda c: (-c["dias_promedio"], c["cliente"]),
    )

    # 4. Observaciones por tipo de error.
    etiquetas = dict(TipoError.choices)
    conteo_tipos = Counter(Observacion.objects.filter(entregable__in=qs.values("pk")).values_list("tipo_error", flat=True))
    observaciones = sorted(
        ({"tipo_error": t, "etiqueta": str(etiquetas.get(t, t)), "cantidad": n} for t, n in conteo_tipos.items()),
        key=lambda o: (-o["cantidad"], o["etiqueta"]),
    )

    return {
        "filtros": activos,
        "texto_filtro": texto_filtro(activos),
        "activos_por_persona": personas,
        "cumplidos_por_mes": cumplidos,
        "atencion_por_cliente": atencion,
        "observaciones_por_tipo": observaciones,
    }
