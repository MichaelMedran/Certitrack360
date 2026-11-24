import datetime
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.checklists import tdr as tdr_srv
from apps.checklists.models import ItemChecklistTDR, RevisionCalidad
from apps.clientes.models import LINEAS_INICIALES, Cliente, Contrato, LineaServicio, PlantillaTDR
from apps.conocimiento.models import ConsultaAsistente, LeccionAprendida, Procedimiento
from apps.cuentas.models import Ausencia, Usuario
from apps.cumplimiento.models import DocumentoVigencia, Penalidad
from apps.entregables import adjuntos
from apps.entregables.demo_archivos import contenido_demo
from apps.entregables.models import (
    Adjunto,
    Entregable,
    Entrega,
    HistorialEstado,
    Observacion,
    RegistroTiempo,
    ResponsableApoyo,
)
from apps.equipo.models import ActividadPlan, AvanceActividad, Incorporacion, PlanIncorporacion
from apps.etiquetas.models import Etiqueta
from apps.etiquetas.signals import crear_etiqueta_de_linea
from apps.extraccion.models import Extraccion
from apps.facturacion.models import FacturaSimulada
from apps.levantamiento.models import FichaLevantamiento, ItemFicha
from apps.reportes.models import ReporteAvance
from apps.repositorio import servicios as repo_srv
from apps.repositorio.models import DocumentoRepositorio, RegistroAccesoDocumento, VersionDocumento
from apps.urgencias.models import AlertaUrgente

CLAVE = "demo1234"


class Command(BaseCommand):
    help = (
        "Prepara una base limpia para testeo con usuario: 1 cliente, 1 contrato, 1 plantilla, "
        "1 factura válida y 1 único entregable inicial en estado «Por hacer»."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Aceptado por compatibilidad (el comando siempre reinicia la base de testeo).",
        )

    def handle(self, *args, **opts):
        with transaction.atomic():
            self._borrar()
        with transaction.atomic():
            resumen = self._crear()
        self.stdout.write(self.style.SUCCESS(resumen))

    @staticmethod
    def _borrar():
        PlantillaTDR.objects.update(documento_formato=None)
        for extraccion in Extraccion.objects.all():
            extraccion.archivo.delete(save=False)
        Extraccion.objects.all().delete()
        for modelo in (
            Penalidad,
            DocumentoVigencia,
            ReporteAvance,
            AlertaUrgente,
            RevisionCalidad,
            ItemChecklistTDR,
            FacturaSimulada,
            AvanceActividad,
            Incorporacion,
            ActividadPlan,
            PlanIncorporacion,
            ConsultaAsistente,
            Procedimiento,
            RegistroAccesoDocumento,
            VersionDocumento,
            DocumentoRepositorio,
            ItemFicha,
            FichaLevantamiento,
            RegistroTiempo,
            ResponsableApoyo,
            Ausencia,
            Notificacion,
            LeccionAprendida,
            Entrega,
            HistorialEstado,
            Adjunto,
            Observacion,
            Entregable,
            PlantillaTDR,
            Contrato,
            Cliente,
        ):
            modelo.objects.all().delete()
        Etiqueta.objects.filter(linea_servicio__isnull=True).delete()
        Usuario.objects.all().delete()

    @staticmethod
    def _crear():
        hoy = timezone.localdate()

        usuarios_def = [
            ("junior1", "JUNIOR", "Julia", "Jiménez", "Asistente junior de Proyectos"),
            ("senior1", "SENIOR", "Sofía", "Sánchez", "Senior de Proyectos"),
            ("gerente_demo", "GERENTE", "Gabriel", "Gerente", "Gerente de Proyectos"),
            ("admin_demo", "ADMIN", "Alicia", "Administradora", "Administradora de la plataforma"),
        ]
        u = {}
        for username, rol, nombre, apellido, puesto in usuarios_def:
            obj = Usuario(
                username=username,
                rol=rol,
                first_name=nombre,
                last_name=apellido,
                puesto=puesto,
                email=f"{username}@demo.invalid",
            )
            obj.set_password(CLAVE)
            obj.save()
            u[username] = obj

        lineas = list(LineaServicio.objects.filter(activa=True).order_by("pk"))
        if not lineas:
            lineas = [LineaServicio.objects.get_or_create(nombre=n)[0] for n in LINEAS_INICIALES]
        for linea in lineas:
            crear_etiqueta_de_linea(linea)

        cliente = Cliente.objects.create(
            nombre="Banco Andino Ficticio",
            sector="BANCA",
            tipo=Cliente.Tipo.ESTRATEGICO,
        )

        plantilla = PlantillaTDR.objects.create(
            nombre="Informe técnico mensual",
            formato="Informe en PDF",
            plazo_dias_por_defecto=10,
            adjuntos_requeridos=["BORRADOR"],
            campos_requeridos=[
                {"nombre": "c_periodo_reportado", "etiqueta": "Periodo reportado", "tipo": "texto"},
                {"nombre": "c_responsable_del_cliente", "etiqueta": "Responsable del cliente", "tipo": "texto"},
            ],
            cliente=None,
        )

        contrato = Contrato.objects.create(
            cliente=cliente,
            numero_contrato="DEMO-2026-001",
            descripcion="Servicio de supervisión y reportes mensuales",
            fecha_inicio=hoy - datetime.timedelta(days=30),
            fecha_fin=hoy + datetime.timedelta(days=180),
            senior_responsable=u["senior1"],
            linea_servicio=lineas[0],
        )
        contrato.juniors.set([u["junior1"]])

        # Un documento en repositorio y un certificado vigente del cliente para contexto real.
        pdf_formato = contenido_demo(
            "pdf",
            "Formato Informe Técnico Mensual — Banco Andino",
            "Guía de estructura y carátula oficial del cliente.",
        )
        repo_srv.cargar_plantilla(
            u["senior1"],
            titulo="Formato oficial Informe Técnico Mensual",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=ContentFile(pdf_formato, name="formato_informe_mensual.pdf"),
            cliente=cliente,
            linea_servicio=lineas[0],
            comentario="Formato base aprobado por el cliente para los reportes mensuales.",
        )

        DocumentoVigencia.objects.create(
            cliente=cliente,
            nombre="Certificado ISO 27001",
            vence=hoy + datetime.timedelta(days=90),
            notas="Certificado vigente para adjuntar en los informes del cliente.",
            creado_por=u["senior1"],
        )

        # Factura simulada válida para verificar durante la elaboración.
        FacturaSimulada.objects.create(
            numero="F001-00001",
            cliente_nombre=cliente.nombre,
            contrato_numero=contrato.numero_contrato,
            estado=FacturaSimulada.Estado.EMITIDA,
            fecha_emision=hoy - datetime.timedelta(days=5),
            monto=Decimal("1475.00"),
        )

        # Único entregable del testeo, en estado inicial "Por hacer".
        entregable = Entregable.objects.create(
            contrato=contrato,
            plantilla=plantilla,
            titulo="Informe técnico mensual — Octubre 2026",
            datos={
                "c_periodo_reportado": "Octubre 2026",
                "c_responsable_del_cliente": "Carlos Mendoza",
            },
            plazo=hoy + datetime.timedelta(days=5),
            estado=Entregable.Estado.A_REALIZAR,
            junior_asignado=u["junior1"],
            senior_revisor=u["senior1"],
            creado_por=u["senior1"],
            id_tdr="TDR-BAF-001",
            fecha_recepcion=hoy - datetime.timedelta(days=2),
        )

        HistorialEstado.objects.create(
            entregable=entregable,
            estado_anterior="",
            estado_nuevo=Entregable.Estado.A_REALIZAR,
            usuario=u["senior1"],
            detalle="Entregable creado y asignado para elaboración",
        )

        # Checklist por TDR para que el junior marque los requisitos antes de enviar a revisión.
        for texto, tipo, obligatorio in (
            ("Carátula con periodo y responsable del cliente", ItemChecklistTDR.Tipo.REQUISITO, True),
            ("Borrador del informe técnico adjunto", ItemChecklistTDR.Tipo.DOCUMENTO, True),
            ("Archivo PDF menor a 10 MB", ItemChecklistTDR.Tipo.FORMATO, False),
        ):
            tdr_srv.agregar(entregable, u["senior1"], texto, tipo, obligatorio)

        # Adjunto inicial de TDR cargado por el senior al crear el pedido.
        pdf_tdr = contenido_demo(
            "pdf",
            "TDR-BAF-001 — Términos de Referencia",
            f"Cliente: {cliente.nombre}. Contrato: {contrato.numero_contrato}.",
        )
        adjuntos.crear_adjunto(
            entregable,
            u["senior1"],
            ContentFile(pdf_tdr, name="tdr_baf_001.pdf"),
            "TDR",
            "TDR del pedido del cliente",
        )

        Notificacion.objects.create(
            usuario=u["junior1"],
            entregable=entregable,
            tipo=Notificacion.Tipo.ASIGNACION,
            mensaje=f"Se le asignó el entregable {entregable.codigo}: {entregable.titulo}.",
        )

        return (
            f"Base de testeo lista: 1 entregable ({entregable.codigo} — «{entregable.titulo}», estado: {entregable.get_estado_display()}).\n"
            f"Usuarios (clave {CLAVE}): junior1 (Julia), senior1 (Sofía), gerente_demo (Gabriel), admin_demo (Alicia).\n"
            f"Factura válida disponible para verificar: F001-00001."
        )
