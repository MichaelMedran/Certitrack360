"""Datos del consolidado del gerente (SDD RF-16): solo lectura y solo para GERENTE y ADMIN.

El control de acceso se hace aquí, en el servidor, y no depende de lo que la interfaz muestre u oculte.
Todo sale del queryset de visibilidad de `entregables`, igual que el resto de las pantallas.
"""
import datetime
from collections import Counter

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

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


def datos_consolidado(usuario, params=None, hoy=None, ventana=None):
    """Arma todo lo que muestra la pantalla «Consolidado». Lanza PermissionDenied si no es gerente o admin.

    Filtros (en `params`): cliente, contrato, estado, desde y hasta (rango del plazo, AAAA-MM-DD).
    Los valores no válidos se ignoran. `ventana` son los días de «próximos a vencer» (por defecto la configuración).
    """
    if not getattr(usuario, "is_authenticated", False) or not usuario.es_gerente_o_admin:
        raise PermissionDenied("El consolidado es solo para el gerente y el admin.")
    params = params or {}
    hoy = hoy or timezone.localdate()
    ventana = settings.CONSOLIDADO_WINDOW_DAYS if ventana is None else ventana

    qs = entregables_visibles(usuario)
    activos = {}
    cliente = entero(params.get("cliente"))
    if cliente is not None:
        qs, activos["cliente"] = qs.filter(contrato__cliente_id=cliente), cliente
    contrato = entero(params.get("contrato"))
    if contrato is not None:
        qs, activos["contrato"] = qs.filter(contrato_id=contrato), contrato
    estado = params.get("estado")
    if estado in E.values:
        qs, activos["estado"] = qs.filter(estado=estado), estado
    desde = _fecha(params.get("desde"))
    if desde:
        qs, activos["desde"] = qs.filter(plazo__gte=desde), desde
    hasta = _fecha(params.get("hasta"))
    if hasta:
        qs, activos["hasta"] = qs.filter(plazo__lte=hasta), hasta

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
