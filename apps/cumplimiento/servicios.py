"""Penalidades incurridas por entregable y vigencia de los documentos del cliente (certificados ISO, pólizas, licencias)."""
import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.busqueda.servicios import clientes_visibles_busqueda
from apps.clientes.models import Cliente, Contrato
from apps.cuentas.models import Usuario
from apps.entregables.extensiones import Advertencia
from apps.entregables.models import Entregable, HistorialEstado
from apps.entregables.visibilidad import entregables_visibles, es_senior_del_entregable

from .models import DocumentoVigencia, Penalidad

E = Entregable.Estado
CLAVE_VIGENCIA = "vigencia_vencida"


def _fecha(valor, nombre):
    if isinstance(valor, datetime.date):
        return valor
    try:
        return datetime.date.fromisoformat((valor or "").strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{nombre} no es una fecha válida.") from None


# ------------------------------------------------------------------ Penalidades

def puede_registrar_penalidad(usuario, entregable):
    """El senior del entregable, el gerente y el admin."""
    return es_senior_del_entregable(usuario, entregable)


def dias_atraso(entregable, hoy=None):
    """Días de atraso respecto del plazo: hasta la entrega si ya se entregó, o hasta hoy si sigue abierto."""
    from apps.indicadores.servicios import fecha_entrega_entregable

    hoy = hoy or timezone.localdate()
    referencia = fecha_entrega_entregable(entregable) if entregable.estado == E.HECHO else hoy
    return max(0, ((referencia or hoy) - entregable.plazo).days)


def _monto(texto):
    texto = (texto or "").strip().replace("S/", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto:  # 1.250,50 → 1250.50
        texto = texto.replace(".", "").replace(",", ".")
    try:
        monto = Decimal(texto)
    except InvalidOperation:
        raise ValidationError("El monto no es un número válido (p. ej. 1250,50).") from None
    if not monto.is_finite() or monto < 0 or monto >= Decimal("10000000000"):
        raise ValidationError("El monto debe ser un número positivo.")
    return monto.quantize(Decimal("0.01"))


@transaction.atomic
def registrar_penalidad(usuario, entregable, motivo, monto="", fecha=None):
    if not puede_registrar_penalidad(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin registran penalidades.")
    motivo = " ".join((motivo or "").split())
    if not motivo:
        raise ValidationError("Indique el motivo de la penalidad.")
    fecha = _fecha(fecha, "La fecha de la penalidad") if fecha else timezone.localdate()
    if fecha > timezone.localdate():
        raise ValidationError("La fecha de la penalidad no puede ser futura.")
    penalidad = Penalidad.objects.create(
        entregable=entregable, motivo=motivo[:255], monto=_monto(monto), fecha=fecha, registrada_por=usuario,
    )
    _historial(entregable, usuario, f"Registró una penalidad: {penalidad.motivo}")
    return penalidad


@transaction.atomic
def eliminar_penalidad(usuario, penalidad):
    if not puede_registrar_penalidad(usuario, penalidad.entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin eliminan penalidades.")
    _historial(penalidad.entregable, usuario, f"Eliminó una penalidad: {penalidad.motivo}")
    penalidad.delete()


def _historial(entregable, usuario, detalle):
    HistorialEstado.objects.create(
        entregable=entregable, estado_anterior=entregable.estado, estado_nuevo=entregable.estado, usuario=usuario,
        detalle=detalle[:255],
    )


def penalidades_pactadas(entregable):
    """Lo que el TDR dice sobre penalidades, tomado de la ficha de levantamiento confirmada más reciente del contrato."""
    ficha = (
        entregable.contrato.fichas.filter(confirmada_en__isnull=False).exclude(penalidades="")
        .order_by("-confirmada_en", "-id").first()
    )
    return ficha.penalidades if ficha else ""


def seccion_penalidades(usuario, entregable):
    penalidades = list(entregable.penalidades.select_related("registrada_por"))
    puede = puede_registrar_penalidad(usuario, entregable)
    atraso = dias_atraso(entregable)
    if not penalidades and not puede and not atraso:
        return None
    return {
        "plantilla": "cumplimiento/_penalidades.html", "orden": 60,
        "contexto": {
            "penalidades": penalidades, "puede": puede, "atraso": atraso,
            "total": sum((p.monto for p in penalidades if p.monto is not None), Decimal("0")),
            "pactadas": penalidades_pactadas(entregable), "hoy": timezone.localdate(),
        },
    }


def listado_penalidades(usuario, cliente_id=None):
    """Penalidades de los entregables visibles, con el total general y por cliente (para la pestaña «Penalidades»)."""
    qs = Penalidad.objects.filter(entregable__in=entregables_visibles(usuario)).select_related(
        "entregable__contrato__cliente", "registrada_por")
    if cliente_id:
        qs = qs.filter(entregable__contrato__cliente_id=cliente_id)
    por_cliente = list(
        qs.order_by().values("entregable__contrato__cliente__nombre")
        .annotate(total=Sum("monto")).order_by("entregable__contrato__cliente__nombre")
    )
    return {
        "penalidades": list(qs),
        "total": qs.aggregate(t=Sum("monto"))["t"] or Decimal("0"),
        "por_cliente": [{"cliente": f["entregable__contrato__cliente__nombre"], "total": f["total"] or Decimal("0")}
                        for f in por_cliente],
        "clientes": clientes_visibles_busqueda(usuario).order_by("nombre"),
    }


# ------------------------------------------------------------------ Vigencia de documentos

VENCIDO, POR_VENCER, VIGENTE = "vencido", "por-vencer", "vigente"
ETIQUETAS = {VENCIDO: "Vencido", POR_VENCER: "Por vencer", VIGENTE: "Vigente"}
CLASES = {VENCIDO: "acta-observada", POR_VENCER: "acta-pendiente", VIGENTE: "acta-recibida"}  # colores ya definidos


def estado_vigencia(documento, hoy=None):
    hoy = hoy or timezone.localdate()
    dias = (documento.vence - hoy).days
    if dias < 0:
        return VENCIDO
    return POR_VENCER if dias <= settings.VIGENCIA_DIAS_AVISO else VIGENTE


def _anotar(documentos, hoy=None):
    hoy = hoy or timezone.localdate()
    for d in documentos:
        d.estado = estado_vigencia(d, hoy)
        d.estado_texto = ETIQUETAS[d.estado]
        d.clase = CLASES[d.estado]
        d.dias = (d.vence - hoy).days
    return documentos


def clientes_gestionables(usuario):
    """Clientes cuyos documentos puede registrar: todos para gerente y admin; los de sus contratos para el senior."""
    if usuario.es_gerente_o_admin:
        return Cliente.objects.filter(activo=True)
    if usuario.es_senior:
        return Cliente.objects.filter(activo=True, contratos__senior_responsable=usuario).distinct()
    return Cliente.objects.none()


def puede_gestionar_vigencias(usuario, cliente):
    return clientes_gestionables(usuario).filter(pk=cliente.pk).exists()


def documentos_visibles(usuario):
    return DocumentoVigencia.objects.filter(activo=True, cliente__in=clientes_visibles_busqueda(usuario)).select_related("cliente")


def _validar_documento(nombre, vence):
    nombre = " ".join((nombre or "").split())
    if not nombre:
        raise ValidationError("Indique el nombre del documento (p. ej. Certificado ISO 9001).")
    return nombre[:150], _fecha(vence, "La fecha de vencimiento")


def registrar_documento(usuario, cliente, nombre, vence, notas=""):
    if not puede_gestionar_vigencias(usuario, cliente):
        raise PermissionDenied("No puede registrar documentos de ese cliente.")
    nombre, vence = _validar_documento(nombre, vence)
    return DocumentoVigencia.objects.create(
        cliente=cliente, nombre=nombre, vence=vence, notas=" ".join((notas or "").split())[:255], creado_por=usuario,
    )


def renovar_documento(usuario, documento, vence):
    """Nueva fecha de vencimiento (el cliente renovó el certificado): los avisos vuelven a empezar."""
    if not puede_gestionar_vigencias(usuario, documento.cliente):
        raise PermissionDenied("No puede modificar documentos de ese cliente.")
    documento.vence = _fecha(vence, "La fecha de vencimiento")
    documento.aviso_previo_en = documento.aviso_vencido_en = None
    documento.save(update_fields=["vence", "aviso_previo_en", "aviso_vencido_en"])
    return documento


def retirar_documento(usuario, documento):
    if not puede_gestionar_vigencias(usuario, documento.cliente):
        raise PermissionDenied("No puede modificar documentos de ese cliente.")
    documento.activo = False
    documento.save(update_fields=["activo"])


def seccion_vigencias(usuario, entregable):
    cliente = entregable.contrato.cliente
    documentos = _anotar(list(DocumentoVigencia.objects.filter(cliente=cliente, activo=True)))
    puede = puede_gestionar_vigencias(usuario, cliente)
    if not documentos and not puede:
        return None
    return {
        "plantilla": "cumplimiento/_vigencias.html", "orden": 25,
        "contexto": {"documentos": documentos, "puede": puede, "cliente": cliente,
                     "hay_vencidos": any(d.estado == VENCIDO for d in documentos)},
    }


def condicion_vigencias(entregable, nuevo_estado, usuario, opciones):
    """Antes de enviar a Revisión senior: avisa si el cliente tiene un documento vencido. No bloquea."""
    if nuevo_estado != E.VERIFICACION_SENIOR:
        return None
    vencidos = list(
        DocumentoVigencia.objects.filter(cliente=entregable.contrato.cliente, activo=True, vence__lt=timezone.localdate())
        .order_by("vence")[:3]
    )
    if not vencidos:
        return None
    nombres = ", ".join(f"«{d.nombre}» (venció el {d.vence:%d/%m/%Y})" for d in vencidos)
    return Advertencia(
        CLAVE_VIGENCIA,
        f"El cliente tiene documentos vencidos: {nombres}. Verifique que el entregable no los incluya. "
        f"¿Enviar a «{E.VERIFICACION_SENIOR.label}» de todos modos?",
    )


def _destinatarios(cliente):
    seniors = Usuario.objects.filter(
        is_active=True, pk__in=Contrato.objects.filter(cliente=cliente, activo=True).values("senior_responsable"))
    gerentes = Usuario.objects.filter(is_active=True, rol=Usuario.Rol.GERENTE)
    return list(dict.fromkeys([*seniors, *gerentes]))


def generar_alertas_vigencia(hoy=None):
    """Avisa una vez cuando un documento está por vencer y otra cuando vence. Idempotente. Devuelve los avisos creados."""
    hoy = hoy or timezone.localdate()
    limite = hoy + datetime.timedelta(days=settings.VIGENCIA_DIAS_AVISO)
    creadas = 0
    candidatos = DocumentoVigencia.objects.filter(activo=True, cliente__activo=True, vence__lte=limite).select_related("cliente")
    for doc in candidatos.order_by("pk"):
        vencido = doc.vence < hoy
        campo = "aviso_vencido_en" if vencido else "aviso_previo_en"
        if getattr(doc, campo):
            continue
        with transaction.atomic():
            # UPDATE condicional: dos ejecuciones simultáneas del programador no duplican el aviso.
            reclamado = DocumentoVigencia.objects.filter(pk=doc.pk, **{f"{campo}__isnull": True}).update(
                **{campo: timezone.now()})
            if not reclamado:
                continue
            dias = (doc.vence - hoy).days
            if vencido:
                cuando = f"venció el {doc.vence:%d/%m/%Y}"
            elif dias == 0:
                cuando = "vence hoy"
            else:
                cuando = f"vence en {dias} día{'s' if dias != 1 else ''}, el {doc.vence:%d/%m/%Y}"
            texto = f"{doc.nombre} de {doc.cliente.nombre} {cuando}."[:255]
            for usuario in _destinatarios(doc.cliente):
                Notificacion.objects.create(
                    usuario=usuario, tipo=Notificacion.Tipo.VIGENCIA, mensaje=texto, enlace=reverse("vigencias"))
                creadas += 1
    return creadas
