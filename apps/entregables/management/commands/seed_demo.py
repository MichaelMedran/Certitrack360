"""Datos simulados para la demostración (SDD §16, SDD Sprint 2 §12.1 y SDD Sprint 3 §12.1). Nada de esto corresponde a empresas o personas reales."""
import datetime
import random
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from faker import Faker

from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas
from apps.checklists import calidad as calidad_srv
from apps.checklists import tdr as tdr_srv
from apps.checklists.models import ItemCalidad, ItemChecklistTDR, RevisionCalidad
from apps.clientes.models import LINEAS_INICIALES, Cliente, Contrato, LineaServicio, PlantillaTDR
from apps.conocimiento.models import ConsultaAsistente, LeccionAprendida, Procedimiento
from apps.conocimiento.servicios import generar_lecciones, indexar_embeddings
from apps.cuentas.models import Ausencia, Usuario
from apps.entregables import adjuntos, servicios
from apps.entregables.demo_archivos import contenido_demo, pdf_minimo
from apps.entregables.models import (
    Adjunto,
    Entrega,
    Entregable,
    HistorialEstado,
    Observacion,
    RegistroTiempo,
    ResponsableApoyo,
)
from apps.equipo import servicios as equipo_srv
from apps.equipo.models import ActividadPlan, AvanceActividad, Incorporacion, PlanIncorporacion
from apps.etiquetas import servicios as etiquetas_srv
from apps.etiquetas.models import Etiqueta
from apps.etiquetas.signals import crear_etiqueta_de_linea
from apps.exportacion import servicios as exportacion_srv
from apps.extraccion import servicios as extraccion_srv
from apps.extraccion.models import Extraccion
from apps.facturacion import verificacion as factura_srv
from apps.facturacion.models import FacturaSimulada
from apps.levantamiento.models import FichaLevantamiento, ItemFicha
from apps.repositorio import servicios as repo_srv
from apps.reportes import servicios as reportes_srv
from apps.reportes.models import ConfiguracionReporte, ReporteAvance
from apps.repositorio.models import DocumentoRepositorio, RegistroAccesoDocumento, VersionDocumento
from apps.urgencias import servicios as urgencias_srv
from apps.urgencias.models import AlertaUrgente

CLAVE = "demo1234"
E = Entregable.Estado
TC = Cliente.Tipo

USUARIOS = [
    ("admin_demo", "ADMIN", "Alicia", "Administradora", "Administradora de la plataforma"),
    ("gerente_demo", "GERENTE", "Gabriel", "Gerente", "Gerente de Proyectos"),
    ("senior1", "SENIOR", "Sofía", "Sánchez", "Senior de Proyectos"),
    ("senior2", "SENIOR", "Sergio", "Salazar", "Senior de Proyectos"),
    ("junior1", "JUNIOR", "Julia", "Jiménez", "Asistente junior de Proyectos"),
    ("junior2", "JUNIOR", "Javier", "Juárez", "Asistente junior de Proyectos"),
    ("junior3", "JUNIOR", "Jimena", "Jara", "Asistente junior de Proyectos"),
]

# nombre, sector, tipo de cliente (Sprint 3: pesa en la prioridad calculada)
CLIENTES = [
    ("Banco Andino Ficticio", "BANCA", TC.ESTRATEGICO), ("Financiera Costa Sur (demo)", "BANCA", TC.REGULAR),
    ("Telecom Pacífico Demo", "TELECOM", TC.ESTRATEGICO), ("Redes Altiplano (demo)", "TELECOM", TC.OCASIONAL),
    ("Municipalidad Provincial Ficticia", "PUBLICO", TC.REGULAR), ("Instituto Regional de Prueba", "PUBLICO", TC.OCASIONAL),
]

# nombre, formato, plazo por defecto, adjuntos obligatorios, índice de cliente (None = genérica), campos
PLANTILLAS = [
    ("Informe técnico mensual", "Informe en PDF", 10, ["BORRADOR"], None,
     [("Periodo reportado", "texto"), ("Responsable del cliente", "texto")]),
    ("Acta de conformidad", "Acta firmada", 7, ["EVIDENCIA"], None,
     [("Fecha de reunión", "fecha"), ("Participantes", "texto_largo"), ("Número de acta", "texto")]),
    ("Matriz de riesgos", "Hoja de cálculo", 15, [], None,
     [("Nivel de riesgo", "numero"), ("Impacto", "opcion", ["Alto", "Medio", "Bajo"]),
      ("Descripción del riesgo", "texto_largo")]),
    ("Informe técnico mensual (Banco Andino)", "Informe en PDF", 12, ["BORRADOR", "TDR"], 0,
     [("Periodo reportado", "texto"), ("Responsable del cliente", "texto"), ("Código de riesgo operacional", "texto")]),
]

# El título de cada entregable parte del nombre de su plantilla, para que la demo sea coherente.
TITULO_BASE = {
    "Informe técnico mensual": "Informe técnico",
    "Acta de conformidad": "Acta de conformidad",
    "Matriz de riesgos": "Matriz de riesgos",
    "Informe técnico mensual (Banco Andino)": "Informe técnico Banco Andino",
}
ESTADOS = [E.A_REALIZAR] * 7 + [E.EN_PROCESO] * 7 + [E.VERIFICACION_SENIOR] * 5 + [E.LISTO_PARA_ENTREGA] * 4 + [E.HECHO] * 7
PLAZOS = [-6, -2, 0, 1, 2, 4, 5, 8, 12, 20]

# Lecciones ficticias: (tipo de error, sector del cliente o None, problema, solución). Cada una nace de una observación
# resuelta de un entregable cerrado, igual que en la operación real.
LECCIONES = [
    ("DATO_FALTANTE", None, "El informe mensual se devolvió porque faltaba el periodo reportado en la carátula.", "Verificar la carátula contra la plantilla antes de enviar a revisión; el periodo va con formato mes-año."),
    ("DATO_FALTANTE", None, "El acta de conformidad no tenía la lista completa de participantes del cliente.", "Pedir el listado de asistentes al terminar la reunión y adjuntarlo al acta el mismo día."),
    ("FORMATO", "BANCA", "El cliente bancario rechazó el informe por usar una plantilla con numeración de páginas distinta.", "Usar la plantilla vigente del TDR; la numeración debe ser «Página X de Y» en el pie."),
    ("FORMATO", "TELECOM", "La matriz de riesgos se entregó en un formato que el cliente de telecomunicaciones no pudo abrir.", "Exportar la matriz en el formato exigido por el TDR y probar la apertura antes de entregar."),
    ("PLAZO", None, "El informe de cierre llegó fuera de plazo por una revisión tardía del senior.", "Enviar a revisión senior al menos tres días antes del vencimiento."),
    ("PLAZO", None, "Se confundió el plazo del TDR con el plazo interno y se entregó un día después.", "Registrar siempre el plazo contractual en el sistema y usar la alerta de cinco días."),
    ("CONTENIDO", "PUBLICO", "El informe técnico no incluía las conclusiones que pide el TDR del sector público.", "Revisar la lista de secciones obligatorias del TDR; las conclusiones van antes de los anexos."),
    ("CONTENIDO", None, "Cifras inconsistentes entre el resumen ejecutivo y el anexo de datos.", "Actualizar el resumen al final, copiando las cifras del anexo ya validado."),
    ("DATO_FALTANTE", "PUBLICO", "No se consignó el número de contrato en el acta del instituto regional.", "El número de contrato debe copiarse desde la ficha del contrato en CertiTrack, no escribirse a mano."),
    ("FORMATO", "PUBLICO", "El archivo superó el tamaño máximo que acepta la mesa de partes del cliente público.", "Comprimir las imágenes y entregar un PDF menor a 10 MB; adjuntar anexos aparte."),
    ("OTRO", None, "El cliente pidió una versión firmada digitalmente y se entregó solo la versión escaneada.", "Confirmar al inicio si el TDR exige firma digital y coordinar con el firmante autorizado."),
    ("CONTENIDO", "BANCA", "La descripción del riesgo era demasiado genérica para el cliente bancario.", "Incluir causa, impacto y responsable en cada riesgo, con un ejemplo concreto."),
    ("PLAZO", None, "La prórroga acordada por teléfono no quedó registrada y el entregable figuró como vencido.", "Registrar toda prórroga por escrito y actualizar el plazo en el sistema."),
    ("DATO_FALTANTE", None, "Faltaba el nombre del responsable del cliente en el informe técnico mensual.", "Mantener el responsable del cliente en la ficha del contrato y revisarlo cada trimestre."),
    ("OTRO", None, "Se usó una versión antigua del anexo técnico.", "Descargar siempre el anexo desde la carpeta vigente del contrato y verificar la fecha de versión."),
    ("FORMATO", "TELECOM", "Los títulos del informe no seguían el estilo exigido por el TDR de telecomunicaciones.", "Aplicar los estilos de título de la plantilla; no formatear manualmente."),
]

# Observaciones abiertas (una por tipo, repetidas si hace falta) para que los filtros por tipo tengan qué mostrar.
OBSERVACIONES_ABIERTAS = {
    "DATO_FALTANTE": "Falta el nombre del responsable del cliente en la carátula.",
    "FORMATO": "Ajustar los títulos al estilo de la plantilla.",
    "PLAZO": "El plazo de la tabla de hitos no coincide con el del TDR.",
    "CONTENIDO": "Falta la sección de conclusiones antes de los anexos.",
    "OTRO": "Confirmar con el cliente si se requiere firma digital.",
}
# Observaciones ya resueltas en entregables que siguen en curso (historial de devoluciones anteriores).
OBSERVACIONES_RESUELTAS = [
    ("FORMATO", "Los márgenes no respetaban la plantilla.", "Se aplicaron los márgenes de la plantilla oficial."),
    ("CONTENIDO", "El resumen ejecutivo superaba una página.", "Se acortó el resumen a media página."),
    ("DATO_FALTANTE", "No figuraba la fecha de la reunión.", "Se agregó la fecha tomada de la convocatoria."),
    ("PLAZO", "La fecha de entrega estaba mal copiada.", "Se corrigió con el plazo de la ficha del contrato."),
]

# Requisitos y documentos de la ficha confirmada del primer contrato: una línea cada uno, de ahí sale el checklist por TDR.
REQUERIMIENTOS_FICHA = (
    "Presentar el informe técnico mensual dentro del plazo\n"
    "Acta de conformidad firmada por el cliente\n"
    "Anexos de datos validados por el senior"
)
DOCUMENTOS_FICHA = "TDR firmado\nCronograma base\nDirectorio de contactos del cliente"

# Checklist por TDR agregado a mano en los entregables de contratos sin ficha confirmada: (texto, tipo, obligatorio)
ITEMS_TDR_MANUALES = [
    ("Carátula con el periodo y el responsable del cliente", "REQUISITO", True),
    ("TDR vigente adjunto al entregable", "DOCUMENTO", True),
    ("Anexo técnico con la fecha de versión", "DOCUMENTO", True),
    ("Entrega en PDF de hasta 10 MB", "FORMATO", False),
]
# Avance objetivo del checklist por TDR, repetido en ese orden entre los entregables que lo tienen
AVANCES_TDR = [0.34, 1.0, 0.5, 0.0, 0.67, 1.0]

PROCEDIMIENTOS_DEMO = [
    (
        "Guía rápida de CertiTrack 360",
        None,
        "Recorrido por las pantallas principales: Inicio muestra sus entregables activos, plazos próximos, avisos y su "
        "plan de incorporación; Tablero permite mover entregables según el flujo validado por el servidor; Calendario "
        "muestra los vencimientos con responsable y filtros; Buscador localiza entregables, contratos, adjuntos y "
        "plantillas respetando la visibilidad de su rol.",
    ),
    (
        "Confidencialidad y datos de clientes",
        None,
        "Política NDA del área de Proyectos: las plantillas específicas de un cliente solo las consultan quienes están "
        "asignados a sus contratos activos. Para compartir un ejemplo aprobado con todo el equipo, publíquelo en el "
        "repositorio como ejemplo anonimizado tras verificar que se eliminaron nombres de clientes, montos, números de "
        "contrato y datos personales.",
    ),
    (
        "Flujo de un entregable",
        None,
        "Todo entregable pasa por cinco estados: Por hacer, En proceso, Revisión senior, Aprobado y Entregado. El "
        "Poka-Yoke impide crear entregables sin campos obligatorios o sin ID-TDR, e impide enviar a Revisión senior si "
        "faltan adjuntos requeridos o si quedan observaciones en estado Pendiente.",
    ),
    (
        "Registro de entregas, cargos de recepción y actas de conformidad",
        "BPO",
        "Para cerrar un entregable en estado Entregado es obligatorio registrar la entrega adjuntando el cargo de "
        "recepción, la fecha y el medio de envío; la versión enviada queda bloqueada contra eliminación. El acta de "
        "conformidad nace Pendiente y, si supera los 5 días sin recibirse, el sistema alerta al junior y al senior. Si "
        "el cliente observa el acta, se registra como Observada y se reabre el entregable para una reentrega.",
    ),
    (
        "Levantamiento de TDR y estado documental inicial",
        "Digitalización",
        "Al iniciar un contrato, el junior o el senior redactan la ficha de levantamiento con el archivo del TDR, los "
        "requerimientos, las penalidades y los ítems de entregables recurrentes. Al confirmarla el senior responsable, "
        "queda congelada la foto del estado documental inicial (HU-06) y se generan los entregables en el tablero.",
    ),
]


class Command(BaseCommand):
    help = (
        "Carga datos simulados de demostración (idempotente: si ya existen, no duplica). "
        "Con --reset BORRA todos los clientes, contratos, plantillas, entregables, adjuntos, repositorio, fichas, "
        "procedimientos, planes de incorporación y lecciones, más los usuarios de demostración, y los vuelve a crear."
    )

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra los datos existentes antes de crearlos.")

    def handle(self, *args, **opts):
        if opts["reset"]:
            with transaction.atomic():  # se confirma antes de crear, para que los archivos viejos se borren primero
                self._borrar()
        if Entregable.objects.exists() and Usuario.objects.filter(username="gerente_demo").exists():
            self.stdout.write("Ya existen datos de demostración. Use --reset para recrearlos.")
            return
        with transaction.atomic():
            resumen = self._crear()
        self.stdout.write(self.style.SUCCESS(resumen))
        _, aviso = indexar_embeddings()
        if aviso:
            self.stdout.write(
                "Nota: la búsqueda por significado del asistente necesita Ollama. Con Ollama en marcha, ejecute "
                "«python manage.py indexar_lecciones»; mientras tanto el asistente busca por palabras."
            )

    # ------------------------------------------------------------------ creación

    def _crear(self):
        rnd = random.Random(2026)
        fake = Faker("es_ES")
        fake.seed_instance(2026)
        hoy = timezone.localdate()

        u = {}
        for username, rol, nombre, apellido, puesto in USUARIOS:
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
        seniors, juniors = [u["senior1"], u["senior2"]], [u["junior1"], u["junior2"], u["junior3"]]

        clientes = [Cliente.objects.create(nombre=n, sector=s, tipo=t) for n, s, t in CLIENTES]
        plantillas = [self._plantilla(p, clientes) for p in PLANTILLAS]
        lineas = self._lineas()

        contratos = []
        for i in range(10):
            c = Contrato.objects.create(
                cliente=clientes[i % len(clientes)], numero_contrato=f"DEMO-2026-{i + 1:03d}",
                descripcion=f"Servicio de consultoría simulado {i + 1}", fecha_inicio=hoy - datetime.timedelta(days=120),
                fecha_fin=hoy + datetime.timedelta(days=240), senior_responsable=seniors[i % 2],
                linea_servicio=lineas[i % len(lineas)],
            )
            c.juniors.set(rnd.sample(juniors, 2))
            contratos.append(c)
        Contrato.objects.create(  # un contrato dado de baja (baja lógica), sin entregables
            cliente=clientes[5], numero_contrato="DEMO-2026-011", descripcion="Servicio finalizado (dado de baja)",
            fecha_inicio=hoy - datetime.timedelta(days=400), fecha_fin=hoy - datetime.timedelta(days=30),
            senior_responsable=seniors[1], activo=False,
        )

        entregables = []
        for i, estado in enumerate(ESTADOS):
            contrato = contratos[i % len(contratos)]
            candidatas = [p for p in plantillas if p.cliente_id in (None, contrato.cliente_id)]
            plantilla = candidatas[i % len(candidatas)]
            plazo = hoy - datetime.timedelta(days=30 + 28 * (i % 3)) if estado == E.HECHO else hoy + datetime.timedelta(days=PLAZOS[i % len(PLAZOS)])
            e = Entregable.objects.create(  # el código CT-AAAA-NNNNN lo asigna el modelo al crearlo
                contrato=contrato, plantilla=plantilla, titulo=f"{TITULO_BASE[plantilla.nombre]} {i + 1:02d}",
                datos={c["nombre"]: self._valor(c, fake, rnd, hoy) for c in plantilla.campos_requeridos},
                plazo=plazo, estado=estado, junior_asignado=rnd.choice(list(contrato.juniors.all())),
                senior_revisor=contrato.senior_responsable, creado_por=contrato.senior_responsable,
                # Datos de recepción (HU-01): ID-TDR ficticio y recepción unos días antes de hoy y del plazo.
                id_tdr=f"TDR-{self._siglas(contrato.cliente.nombre)}-{i + 1:03d}",
                fecha_recepcion=min(hoy, plazo) - datetime.timedelta(days=3 + i % 8),
            )
            self._historial(e)
            entregables.append(e)

        self._observaciones(entregables)
        sin_adjuntos = self._adjuntos(entregables)
        self._entregas(entregables, hoy)
        self._personal_y_apoyos(u, entregables, hoy)
        self._tiempos(entregables, hoy)
        self._fichas(contratos, plantillas, entregables, u, hoy)
        docs_repo = self._repositorio(clientes, lineas, plantillas, u)
        self._procedimientos_e_incorporacion(lineas, docs_repo, u, hoy)
        self._notificaciones(entregables)
        generar_alertas(hoy)
        demo3 = self._sprint_3(u, clientes, contratos, entregables, hoy)

        bloqueados = ", ".join(f"«{e.titulo}» ({e.junior_asignado.username})" for e in sin_adjuntos)
        return (
            f"Listo: {Usuario.objects.count()} usuarios, {Cliente.objects.count()} clientes, {Contrato.objects.count()} contratos, "
            f"{PlantillaTDR.objects.count()} plantillas, {Entregable.objects.count()} entregables, "
            f"{Adjunto.objects.count()} archivos ficticios, {Observacion.objects.count()} observaciones, "
            f"{DocumentoRepositorio.objects.count()} documentos en repositorio, {Procedimiento.objects.count()} procedimientos, "
            f"{PlanIncorporacion.objects.count()} planes de incorporación, "
            f"{Notificacion.objects.count()} notificaciones y {LeccionAprendida.objects.count()} lecciones. "
            f"Contraseña de prueba: {CLAVE}\n"
            f"Para ver el bloqueo por adjuntos faltantes, mueva a «{E.VERIFICACION_SENIOR.label}»: {bloqueados}.\n"
            f"{demo3}"
        )

    @staticmethod
    def _lineas():
        """Las líneas de servicio activas del catálogo (las crea la migración); si no hubiera, las cinco iniciales."""
        lineas = list(LineaServicio.objects.filter(activa=True).order_by("pk"))
        return lineas or [LineaServicio.objects.get_or_create(nombre=n)[0] for n in LINEAS_INICIALES]

    @staticmethod
    def _siglas(nombre):
        """Iniciales del cliente ficticio para su ID-TDR: «Banco Andino Ficticio» → BAF."""
        return "".join(palabra[0] for palabra in nombre.split() if palabra[:1].isupper())

    @staticmethod
    def _plantilla(definicion, clientes):
        nombre, formato, dias, adjuntos_requeridos, cliente, campos = definicion
        lista = []
        for campo in campos:
            etiqueta, tipo = campo[0], campo[1]
            item = {"nombre": "c_" + "".join(ch if ch.isalnum() else "_" for ch in etiqueta.lower()), "etiqueta": etiqueta, "tipo": tipo}
            if tipo == "opcion":
                item["opciones"] = campo[2]
            lista.append(item)
        return PlantillaTDR.objects.create(
            nombre=nombre, formato=formato, plazo_dias_por_defecto=dias, adjuntos_requeridos=adjuntos_requeridos,
            campos_requeridos=lista, cliente=None if cliente is None else clientes[cliente],
        )

    @staticmethod
    def _valor(campo, fake, rnd, hoy):
        tipo = campo["tipo"]
        if tipo == "fecha":
            return (hoy - datetime.timedelta(days=rnd.randint(2, 20))).isoformat()
        if tipo == "numero":
            return str(rnd.randint(1, 5))
        if tipo == "opcion":
            return rnd.choice(campo["opciones"])
        if tipo == "texto_largo":
            return fake.sentence(nb_words=6)
        return fake.name() if "Responsable" in campo["etiqueta"] else fake.word().capitalize()

    @staticmethod
    def _historial(e):
        HistorialEstado.objects.create(
            entregable=e, estado_anterior="", estado_nuevo=E.A_REALIZAR, usuario=e.creado_por, detalle="Entregable creado"
        )
        ruta = [E.A_REALIZAR, E.EN_PROCESO, E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA, E.HECHO]
        for anterior, nuevo in zip(ruta, ruta[1:ruta.index(e.estado) + 1]):
            quien = e.junior_asignado if nuevo in (E.EN_PROCESO, E.VERIFICACION_SENIOR) else e.senior_revisor
            HistorialEstado.objects.create(entregable=e, estado_anterior=anterior, estado_nuevo=nuevo, usuario=quien)

    @staticmethod
    def _observaciones(entregables):
        hechos = [e for e in entregables if e.estado == E.HECHO]
        # Cada lección sale de una observación resuelta de un entregable cerrado (de un cliente del sector que corresponde).
        for n, (tipo, sector, problema, solucion) in enumerate(LECCIONES):
            candidatos = [e for e in hechos if sector in (None, e.contrato.cliente.sector)]
            e = candidatos[n % len(candidatos)]
            Observacion.objects.create(
                entregable=e, autor=e.senior_revisor, tipo_error=tipo, descripcion=problema, solucion=solucion, resuelta=True
            )
        for e in hechos:
            generar_lecciones(e)

        en_proceso = [e for e in entregables if e.estado == E.EN_PROCESO]
        ahora = timezone.now()
        for n, e in enumerate(en_proceso):  # abiertas: cubren los cinco tipos y los estados PENDIENTE y EN_CORRECCION (§12.1)
            tipo = list(OBSERVACIONES_ABIERTAS)[n % len(OBSERVACIONES_ABIERTAS)]
            en_correccion = n >= 5  # las dos últimas quedan «En corrección» con acción correctiva registrada
            Observacion.objects.create(
                entregable=e,
                autor=e.senior_revisor,
                responsable=e.junior_asignado,
                tipo_error=tipo,
                descripcion=OBSERVACIONES_ABIERTAS[tipo],
                estado=Observacion.Estado.EN_CORRECCION if en_correccion else Observacion.Estado.PENDIENTE,
                solucion="Se completó el dato observado en la versión corregida." if en_correccion else "",
                corregida_por=e.junior_asignado if en_correccion else None,
                corregida_en=ahora if en_correccion else None,
                resuelta=False,
            )
        previos = [e for e in entregables if e.estado in (E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA)]
        for n, (tipo, problema, solucion) in enumerate(OBSERVACIONES_RESUELTAS):  # resueltas, aún sin cerrar
            e = previos[n % len(previos)]
            Observacion.objects.create(
                entregable=e, autor=e.senior_revisor, tipo_error=tipo, descripcion=problema, solucion=solucion, resuelta=True
            )

    @staticmethod
    def _subir(e, tipo, usuario, comentario=""):
        extension = "txt" if tipo in ("EVIDENCIA", "OTRO") else "pdf"
        nombre = f"{slugify(e.titulo)}_{tipo.lower()}.{extension}"
        contenido = contenido_demo(
            extension, f"{e.titulo} - {adjuntos.etiqueta_tipo(tipo)}", f"Cliente: {e.contrato.cliente}. Contrato: {e.contrato.numero_contrato}."
        )
        adjuntos.crear_adjunto(e, usuario, ContentFile(contenido, name=nombre), tipo, comentario)

    def _adjuntos(self, entregables):
        # Los dos primeros entregables «en proceso» que exigen adjuntos quedan sin ellos: así se ve el bloqueo del Poka-Yoke.
        sin_adjuntos = [e for e in entregables if e.estado == E.EN_PROCESO and e.plantilla.adjuntos_requeridos][:2]
        for i, e in enumerate(entregables):
            requeridos, junior, senior = e.plantilla.adjuntos_requeridos, e.junior_asignado, e.senior_revisor
            if e.estado == E.A_REALIZAR:
                if i % 2 == 0:
                    self._subir(e, "TDR", senior, "TDR del cliente")
            elif e.estado == E.EN_PROCESO:
                if e in sin_adjuntos:
                    continue
                for tipo in requeridos or ["TDR"]:
                    self._subir(e, tipo, senior if tipo == "TDR" else junior)
            else:
                for tipo in requeridos:
                    quien = senior if tipo == "TDR" else junior
                    if i % 3 == 0:  # más de una versión en algunos casos
                        self._subir(e, tipo, quien, "Primera versión")
                        self._subir(e, tipo, quien, "Corregido tras la revisión")
                    else:
                        self._subir(e, tipo, quien)
                if e.estado in (E.LISTO_PARA_ENTREGA, E.HECHO):
                    self._subir(e, "VERSION_FINAL", senior, "Versión aprobada para entrega")
                if e.estado == E.HECHO and "EVIDENCIA" not in requeridos and i % 2 == 1:
                    self._subir(e, "EVIDENCIA", senior, "Cargo de recepción")
        return sin_adjuntos

    @staticmethod
    def _entrega_ficticia(e, tipo, usuario, comentario):
        """Cargo o acta ficticios del entregable cerrado (PDF diminuto); nacen bloqueados, como en la operación real."""
        nombre = f"{slugify(e.titulo)}_{tipo.lower()}.pdf"
        contenido = contenido_demo(
            "pdf", f"{e.titulo} - {adjuntos.etiqueta_tipo(tipo)}", f"Cliente: {e.contrato.cliente}. Contrato: {e.contrato.numero_contrato}."
        )
        return adjuntos.crear_adjunto(e, usuario, ContentFile(contenido, name=nombre), tipo, comentario, bloqueado=True)

    def _entregas(self, entregables, hoy):
        """Cargo de recepción, entrega y acta de los entregables cerrados (RF-29 y §12.1).
        La entrega con acta PENDIENTE lleva 6 días desde la entrega (> ACTA_DIAS_PENDIENTE=5), lista para demostrar la alerta."""
        actas = [Entrega.ActaEstado.RECIBIDA, Entrega.ActaEstado.RECIBIDA, Entrega.ActaEstado.PENDIENTE,
                 Entrega.ActaEstado.RECIBIDA, Entrega.ActaEstado.OBSERVADA, Entrega.ActaEstado.RECIBIDA,
                 Entrega.ActaEstado.RECIBIDA]
        medios = list(Entrega.Medio.values)
        for n, e in enumerate((x for x in entregables if x.estado == E.HECHO)):
            estado_acta = actas[n % len(actas)]
            fecha = {Entrega.ActaEstado.PENDIENTE: hoy - datetime.timedelta(days=6),
                     Entrega.ActaEstado.OBSERVADA: hoy - datetime.timedelta(days=8)}.get(
                estado_acta, e.plazo - datetime.timedelta(days=n % 3))
            cargo = self._entrega_ficticia(e, "CARGO_RECEPCION", e.senior_revisor, "Cargo de recepción del cliente (ficticio)")
            acta = None
            if estado_acta != Entrega.ActaEstado.PENDIENTE:
                acta = self._entrega_ficticia(e, "ACTA_CONFORMIDAD", e.senior_revisor, "Acta de conformidad (ficticia)")
            cierre = e.historial.filter(estado_anterior=E.LISTO_PARA_ENTREGA, estado_nuevo=E.HECHO).first()
            version = adjuntos.vigente(e, "VERSION_FINAL")
            Adjunto.objects.filter(pk=version.pk).update(bloqueado=True)
            Entrega.objects.create(
                entregable=e, numero=1, fecha_entrega=fecha, medio=medios[n % len(medios)], cargo=cargo,
                version_enviada=version, acta_estado=estado_acta, acta=acta,
                acta_actualizada_en=timezone.now() if acta else None, registrada_por=e.senior_revisor, cierre=cierre,
            )

    @staticmethod
    def _personal_y_apoyos(u, entregables, hoy):
        """Ausencia próxima y responsables de apoyo (§12.1, RF-31)."""
        Ausencia.objects.create(
            usuario=u["junior2"],
            desde=hoy + datetime.timedelta(days=1),
            hasta=hoy + datetime.timedelta(days=5),
            motivo="Licencia programada (ficticia)",
        )
        en_curso = [e for e in entregables if e.estado == E.EN_PROCESO]
        if len(en_curso) >= 2:
            ResponsableApoyo.objects.create(
                entregable=en_curso[0],
                usuario=u["senior2"],
                funcion=ResponsableApoyo.Funcion.REVISION,
                fecha_limite=en_curso[0].plazo,
                asignado_por=u["gerente_demo"],
                activo=True,
            )
            ResponsableApoyo.objects.create(
                entregable=en_curso[1],
                usuario=u["senior1"],
                funcion=ResponsableApoyo.Funcion.APOYO,
                fecha_limite=en_curso[1].plazo,
                asignado_por=u["gerente_demo"],
                activo=True,
            )
            ResponsableApoyo.objects.create(
                entregable=en_curso[0],
                usuario=u["junior3"],
                funcion=ResponsableApoyo.Funcion.ELABORACION,
                fecha_limite=en_curso[0].plazo,
                asignado_por=u["gerente_demo"],
                activo=False,
            )

    @staticmethod
    def _tiempos(entregables, hoy):
        """Registros de tiempo de las tres etapas, incluidos ajustes manuales justificados (§12.1, RF-32)."""
        base_dt = timezone.make_aware(datetime.datetime.combine(hoy - datetime.timedelta(days=3), datetime.time(9, 0)))
        candidatos = [e for e in entregables if e.estado in (E.EN_PROCESO, E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA, E.HECHO)][:6]
        etapas = [
            RegistroTiempo.Etapa.RECOPILACION,
            RegistroTiempo.Etapa.CONSOLIDACION,
            RegistroTiempo.Etapa.REVISION,
        ]
        for idx, e in enumerate(candidatos):
            etapa = etapas[idx % len(etapas)]
            es_manual = idx in (1, 4)
            usuario = e.senior_revisor if etapa == RegistroTiempo.Etapa.REVISION else e.junior_asignado
            inicio = base_dt + datetime.timedelta(hours=idx * 3)
            fin = inicio + datetime.timedelta(hours=2, minutes=30)
            RegistroTiempo.objects.create(
                entregable=e,
                usuario=usuario,
                etapa=etapa,
                inicio=inicio,
                fin=fin,
                cierra_etapa=(idx % 2 == 0),
                manual=es_manual,
                motivo="Trabajo de revisión de anexos realizado en reunión con el equipo." if es_manual else "",
            )

    @staticmethod
    def _fichas(contratos, plantillas, entregables, u, hoy):
        """Dos fichas de levantamiento: una confirmada con foto inicial congelada y entregables vinculados, y otra en borrador (§12.1, RF-30)."""
        c0 = contratos[0]
        pdf_c0 = contenido_demo("pdf", f"TDR {c0.numero_contrato}", f"Cliente: {c0.cliente.nombre}")
        foto_inicial = {
            "contrato": c0.numero_contrato,
            "cliente": c0.cliente.nombre,
            "id_tdr": "TDR-BAF-2026-001",
            "nombre_archivo_tdr": "tdr_demo_2026_001.pdf",
            "requerimientos": REQUERIMIENTOS_FICHA,
            "formatos": "PDF con firma digital; anexos en hoja de cálculo",
            "frecuencia_reportes": "Mensual",
            "penalidades": "1 UIT por cada día útil de retraso injustificado",
            "responsable": c0.senior_responsable.nombre,
            "documentos_disponibles": DOCUMENTOS_FICHA,
            "documentos_faltantes": "Matriz de escalamiento actualizada del cliente",
            "formato_esperado": "Informe PDF (máx. 10 MB)",
            "fecha_limite": (hoy + datetime.timedelta(days=30)).isoformat(),
            "estado_documental": FichaLevantamiento.EstadoDocumental.ABIERTO,
        }
        ficha_conf = FichaLevantamiento.objects.create(
            contrato=c0,
            id_tdr="TDR-BAF-2026-001",
            archivo_tdr=ContentFile(pdf_c0, name="tdr_demo_2026_001.pdf"),
            nombre_archivo_tdr="tdr_demo_2026_001.pdf",
            requerimientos=REQUERIMIENTOS_FICHA,
            formatos=foto_inicial["formatos"],
            frecuencia_reportes="Mensual",
            penalidades=foto_inicial["penalidades"],
            responsable=c0.senior_responsable,
            documentos_disponibles=DOCUMENTOS_FICHA + "\nMatriz de escalamiento recibida",
            documentos_faltantes="",
            formato_esperado=foto_inicial["formato_esperado"],
            fecha_limite=hoy + datetime.timedelta(days=30),
            estado=FichaLevantamiento.Estado.CONFIRMADA,
            estado_inicial=foto_inicial,
            estado_documental=FichaLevantamiento.EstadoDocumental.COMPLETO,
            creada_por=c0.juniors.first() or u["junior1"],
            confirmada_por=c0.senior_responsable,
            confirmada_en=timezone.now(),
        )
        item_conf = ItemFicha.objects.create(
            ficha=ficha_conf,
            nombre="Informe técnico mensual",
            plantilla=plantillas[0],
            frecuencia=ItemFicha.Frecuencia.MENSUAL,
            primera_fecha=hoy + datetime.timedelta(days=15),
            hasta=hoy + datetime.timedelta(days=75),
            junior=c0.juniors.first() or u["junior1"],
            senior=c0.senior_responsable,
            datos={"c_periodo_reportado": "2026-11", "c_responsable_del_cliente": "Coordinador Ficticio"},
        )
        item_conf.entregables_generados.set([e for e in entregables if e.contrato_id == c0.pk])

        c1 = contratos[1]
        pdf_c1 = contenido_demo("pdf", f"TDR {c1.numero_contrato}", f"Cliente: {c1.cliente.nombre}")
        ficha_borrador = FichaLevantamiento.objects.create(
            contrato=c1,
            id_tdr="TDR-FCS-2026-002",
            archivo_tdr=ContentFile(pdf_c1, name="tdr_demo_2026_002.pdf"),
            nombre_archivo_tdr="tdr_demo_2026_002.pdf",
            requerimientos="Elaboración trimestral de matriz de riesgos operacionales y actas de comité.",
            formatos="Hoja de cálculo (.xlsx) y acta en PDF",
            frecuencia_reportes="Trimestral",
            penalidades="0,5 % del monto mensual por observación reiterada",
            responsable=c1.senior_responsable,
            documentos_disponibles="TDR preliminar y catálogo de procesos",
            documentos_faltantes="Anexo de umbrales de impacto validado por el cliente",
            formato_esperado="Hoja de cálculo oficial",
            fecha_limite=hoy + datetime.timedelta(days=20),
            estado=FichaLevantamiento.Estado.BORRADOR,
            estado_documental=FichaLevantamiento.EstadoDocumental.EN_CURSO,
            creada_por=c1.juniors.first() or u["junior2"],
        )
        ItemFicha.objects.create(
            ficha=ficha_borrador,
            nombre="Matriz de riesgos trimestral",
            plantilla=plantillas[2],
            frecuencia=ItemFicha.Frecuencia.MENSUAL,
            primera_fecha=hoy + datetime.timedelta(days=10),
            hasta=hoy + datetime.timedelta(days=70),
            junior=c1.juniors.first() or u["junior2"],
            senior=c1.senior_responsable,
            datos={
                "c_nivel_de_riesgo": "2",
                "c_impacto": "Medio",
                "c_descripci_n_del_riesgo": "Riesgo operativo simulado para demostración.",
            },
        )

    @staticmethod
    def _repositorio(clientes, lineas, plantillas, u):
        """Ocho documentos en el repositorio: plantillas de cliente (dos con v1 y v2), genéricas y ejemplos anonimizados (§12.1)."""
        gerente = u["gerente_demo"]
        senior1 = u["senior1"]
        senior2 = u["senior2"]
        linea_por_nombre = {l.nombre: l for l in lineas}

        def _pdf_repo(nombre_archivo, titulo, subtitulo):
            return ContentFile(contenido_demo("pdf", titulo, subtitulo), name=nombre_archivo)

        # 1. Plantilla de Banco Andino con 2 versiones (v1 histórico, v2 vigente)
        doc_baf, _ = repo_srv.cargar_plantilla(
            senior1,
            titulo="Formato de reporte mensual Banco Andino",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_pdf_repo("formato_reporte_baf_v1.pdf", "Formato Reporte BAF v1", "Plantilla inicial (ficticia)"),
            cliente=clientes[0],
            linea_servicio=linea_por_nombre.get("Banca"),
            comentario="Versión inicial del formato del cliente",
        )
        repo_srv.subir_nueva_version(
            doc_baf,
            senior1,
            archivo=_pdf_repo("formato_reporte_baf_v2.pdf", "Formato Reporte BAF v2", "Incluye código de riesgo operacional"),
            comentario="Suma cuadro de código de riesgo operacional según adenda",
        )

        # 2. Plantilla de Telecom Pacífico con 2 versiones (v1 histórico, v2 vigente)
        doc_tel, _ = repo_srv.cargar_plantilla(
            senior1,
            titulo="Plantilla de matriz de riesgos Telecom Pacífico",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_pdf_repo("plantilla_matriz_telecom_v1.pdf", "Matriz Telecom v1", "Versión original (ficticia)"),
            cliente=clientes[2],
            linea_servicio=linea_por_nombre.get("BPO"),
            comentario="Versión original del contrato",
        )
        repo_srv.subir_nueva_version(
            doc_tel,
            senior1,
            archivo=_pdf_repo("plantilla_matriz_telecom_v2.pdf", "Matriz Telecom v2", "Estilos de título actualizados"),
            comentario="Ajusta estilos de título exigidos por el TDR",
        )

        # 3 y 4. Otras dos plantillas específicas de clientes
        doc_carta_baf, _ = repo_srv.cargar_plantilla(
            gerente,
            titulo="Carta de presentación de entregables (Banco Andino)",
            tipo_documento=DocumentoRepositorio.TipoDocumento.CARTA,
            archivo=_pdf_repo("carta_presentacion_baf.pdf", "Carta BAF", "Modelo de carta de entrega (ficticio)"),
            cliente=clientes[0],
            linea_servicio=linea_por_nombre.get("Digitalización"),
            comentario="Modelo validado con mesa de partes",
        )
        doc_muni, _ = repo_srv.cargar_plantilla(
            senior2,
            titulo="Formato de acta de conformidad sector público",
            tipo_documento=DocumentoRepositorio.TipoDocumento.OTRO,
            archivo=_pdf_repo("acta_municipalidad.pdf", "Acta Sector Público", "Plantilla para entidades públicas (ficticia)"),
            cliente=clientes[5],
            linea_servicio=linea_por_nombre.get("Estado"),
            comentario="Incluye bloque de firmas y sello de recepción",
        )

        # 5 y 6. Dos plantillas genéricas (visibles para todos los roles)
        doc_gen_informe, _ = repo_srv.cargar_plantilla(
            gerente,
            titulo="Plantilla general de informe técnico mensual",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_pdf_repo("plantilla_general_informe.pdf", "Informe Técnico Estándar", "Plantilla genérica CERTICOM (ficticia)"),
            cliente=None,
            linea_servicio=linea_por_nombre.get("BPO"),
            comentario="Formato estándar del área de Proyectos",
        )
        doc_gen_cot, _ = repo_srv.cargar_plantilla(
            gerente,
            titulo="Cotización estándar de servicios documentales",
            tipo_documento=DocumentoRepositorio.TipoDocumento.COTIZACION,
            archivo=_pdf_repo("cotizacion_estandar.pdf", "Cotización Estándar", "Formato genérico de cotización (ficticio)"),
            cliente=None,
            linea_servicio=linea_por_nombre.get("Custodia"),
            comentario="Plantilla base para propuestas técnicas",
        )

        # 7 y 8. Dos ejemplos anonimizados con verificación NDA completa
        confirmaciones_nda = {clave: True for clave in repo_srv.CLAVES_NDA}
        doc_anon_inf, _ = repo_srv.publicar_anonimizado(
            senior1,
            titulo="Ejemplo de informe técnico mensual aprobado (anonimizado)",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_pdf_repo("ejemplo_informe_anonimizado.pdf", "Ejemplo Anonimizado de Informe", "Sin datos de clientes reales"),
            confirmaciones=confirmaciones_nda,
            linea_servicio=linea_por_nombre.get("BPO"),
            comentario="Ejemplo de referencia para nuevos ingresos",
        )
        doc_anon_mat, _ = repo_srv.publicar_anonimizado(
            gerente,
            titulo="Ejemplo de matriz de riesgos operacionales (anonimizado)",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_pdf_repo("ejemplo_matriz_anonimizada.pdf", "Ejemplo Anonimizado de Matriz", "Sin montos ni contratos reales"),
            confirmaciones=confirmaciones_nda,
            linea_servicio=linea_por_nombre.get("Custodia"),
            comentario="Referencia de redacción de causas e impactos",
        )

        # Enlaza las plantillas de TDR con sus formatos del repositorio (§7.9)
        PlantillaTDR.objects.filter(pk=plantillas[0].pk).update(documento_formato=doc_gen_informe)
        PlantillaTDR.objects.filter(pk=plantillas[3].pk).update(documento_formato=doc_baf)

        return {
            "plantilla_cliente": doc_baf,
            "plantilla_generica": doc_gen_informe,
            "ejemplo_anonimizado": doc_anon_inf,
            "todos": [doc_baf, doc_tel, doc_carta_baf, doc_muni, doc_gen_informe, doc_gen_cot, doc_anon_inf, doc_anon_mat],
        }

    @staticmethod
    def _procedimientos_e_incorporacion(lineas, docs_repo, u, hoy):
        """Cinco procedimientos aprobados y los dos planes de incorporación con una incorporación en curso (§7.12, §12.1)."""
        gerente = u["gerente_demo"]
        linea_por_nombre = {l.nombre: l for l in lineas}
        for titulo, nombre_linea, contenido in PROCEDIMIENTOS_DEMO:
            Procedimiento.objects.create(
                titulo=titulo,
                contenido=contenido,
                linea_servicio=linea_por_nombre.get(nombre_linea) if nombre_linea else None,
                documento=docs_repo["plantilla_generica"] if "Flujo" in titulo else None,
                aprobado_por=gerente,
                vigente=True,
            )

        plan_junior, _ = equipo_srv.crear_planes_iniciales(
            autor=gerente,
            plantilla_doc=docs_repo["plantilla_generica"],
            ejemplo_anon_doc=docs_repo["ejemplo_anonimizado"],
        )
        # Incorporación en curso para junior3 (Jimena), con 5 actividades completadas y 1 en curso (wireframe s2-incorporacion)
        inc = equipo_srv.asignar_plan(
            plan_junior,
            ingresante=u["junior3"],
            responsable=u["senior1"],
            fecha_inicio=hoy - datetime.timedelta(days=5),
            autor=gerente,
            emitir_notificaciones=False,
        )
        ahora = timezone.now()
        for av in inc.avances.select_related("actividad").order_by("actividad__orden"):
            if av.actividad.orden <= 5:
                av.estado = AvanceActividad.Estado.COMPLETADA
                av.completada_en = ahora
                av.save(update_fields=["estado", "completada_en", "actualizado_en"])
            elif av.actividad.orden == 6:
                av.estado = AvanceActividad.Estado.EN_CURSO
                av.save(update_fields=["estado", "actualizado_en"])

    @staticmethod
    def _notificaciones(entregables):
        for e in entregables:  # los mismos textos (con el código del entregable) que generan los servicios
            Notificacion.objects.create(
                usuario=e.junior_asignado, entregable=e, tipo=Notificacion.Tipo.ASIGNACION,
                mensaje=servicios.texto_asignacion(e), leida=e.estado != E.A_REALIZAR,
            )
            if e.estado == E.VERIFICACION_SENIOR:
                Notificacion.objects.create(
                    usuario=e.senior_revisor, entregable=e, tipo=Notificacion.Tipo.VERIFICACION,
                    mensaje=servicios.texto_en_revision(e),
                )
        for o in Observacion.objects.filter(resuelta=False).select_related("entregable__junior_asignado"):
            Notificacion.objects.create(
                usuario=o.entregable.junior_asignado, entregable=o.entregable, tipo=Notificacion.Tipo.OBSERVACION,
                mensaje=servicios.texto_observacion(o.entregable),
            )

    # ------------------------------------------------------------------ Sprint 3 (SDD del Sprint 3, §12.1)

    def _sprint_3(self, u, clientes, contratos, entregables, hoy):
        """Deja demostrable todo el Sprint 3 usando los servicios de cada app (no filas a mano, salvo la base de
        facturación simulada, que es un dato de entrada). Devuelve las líneas de orientación que imprime el comando."""
        en_proceso = [e for e in entregables if e.estado == E.EN_PROCESO]
        listos = [e for e in en_proceso if not adjuntos.faltantes_requeridos(e)]  # con todos sus adjuntos requeridos
        en_revision = [e for e in entregables if e.estado == E.VERIFICACION_SENIOR]
        aprobados = [e for e in entregables if e.estado == E.LISTO_PARA_ENTREGA]
        notas = [self._etiquetas(u, contratos, entregables)]
        notas.append(self._urgencias(u, en_proceso))
        notas.append(self._checklists_tdr(entregables, contratos, listos))
        notas.append(self._calidad_y_facturas(u, clientes, en_revision, listos, hoy))
        notas.append(self._exportaciones(aprobados[0]))
        notas.append(self._extraccion(listos[1]))
        notas.append(self._reportes(u))
        return "\n".join(notas)

    @staticmethod
    def _etiquetas(u, contratos, entregables):
        """Etiquetas de las cinco líneas (una por contrato) y dos personalizadas, en contratos y en entregables (RF-41)."""
        gerente, senior1 = u["gerente_demo"], u["senior1"]
        for linea in LineaServicio.objects.filter(activa=True):
            crear_etiqueta_de_linea(linea)  # si la migración ya la creó, no hace nada
        auditoria = etiquetas_srv.crear(gerente, "Auditoría externa", Etiqueta.Color.AMBAR)
        observado = etiquetas_srv.crear(senior1, "Cliente en observación", Etiqueta.Color.ROJO)
        for n, c in enumerate(contratos):
            propias = [t for t in (etiquetas_srv.etiqueta_de_linea(c),) if t is not None]
            if n % 4 == 0:
                propias.append(auditoria)
            etiquetas_srv.asignar_a_contrato(gerente, c, propias)
        for n, e in enumerate(x for x in entregables if x.estado != E.HECHO):
            elegidas = {0: [auditoria], 1: [observado], 2: [auditoria, observado]}.get(n % 6, [])
            if elegidas:
                etiquetas_srv.asignar(e.senior_revisor, e, elegidas)
        return "Etiquetas: «Auditoría externa» y «Cliente en observación» en contratos y entregables; filtre por etiqueta en Tablero y Entregables."

    @staticmethod
    def _urgencias(u, en_proceso):
        """Una persona de guardia, una alerta urgente abierta (con una lectura) y otra aceptada fuera de horario (RF-43)."""
        guardia = u["senior2"]
        urgencias_srv.marcar_guardia(u["gerente_demo"], guardia, True)
        # La abierta la activa el gerente sobre un entregable que no es de la persona de guardia: así avisa a tres personas.
        abierta_e = next(e for e in en_proceso[2:] if e.senior_revisor_id != guardia.pk)
        aceptada_e = next(e for e in en_proceso[2:] if e.pk != abierta_e.pk)
        ahora = timezone.now()
        abierta = urgencias_srv.activar(
            u["gerente_demo"], abierta_e,
            "El cliente pide el informe de cierre fuera de horario por una auditoría del regulador.",
            ahora + datetime.timedelta(hours=20),
        )
        urgencias_srv.confirmar_lectura(abierta_e.junior_asignado, abierta)  # los demás destinatarios siguen sin leerla
        # La aceptada se activó el último sábado por la noche (fuera de horario) y la aceptó la persona de guardia.
        local = timezone.localtime(ahora)
        sabado = (local - datetime.timedelta(days=(local.weekday() - 5) % 7 or 7)).replace(hour=21, minute=30, second=0, microsecond=0)
        aceptada = urgencias_srv.activar(
            aceptada_e.senior_revisor, aceptada_e, "Caída del enlace del cliente: necesita el acta firmada el domingo.",
            sabado + datetime.timedelta(hours=14), ahora=sabado,
        )
        urgencias_srv.aceptar(guardia, aceptada, ahora=sabado + datetime.timedelta(minutes=40))
        AlertaUrgente.objects.filter(pk=aceptada.pk).update(activada_en=sabado)
        Notificacion.objects.filter(entregable=aceptada_e, tipo=Notificacion.Tipo.URGENTE).update(leida=True)
        return (
            f"Alerta urgente abierta: {abierta_e.codigo} («{abierta_e.titulo}», junior {abierta_e.junior_asignado.username}); "
            f"aceptada fuera de horario: {aceptada_e.codigo}. De guardia: {guardia.username}."
        )

    @staticmethod
    def _checklists_tdr(entregables, contratos, listos):
        """Checklist por TDR con avances distintos: desde la ficha confirmada en el primer contrato, a mano en los demás (RF-44)."""
        con_lista = [e for e in entregables if e.estado != E.HECHO]
        de_ficha = [e for e in con_lista if e.contrato_id == contratos[0].pk]
        manuales = [e for e in con_lista if e.contrato_id != contratos[0].pk][:9]
        for e in de_ficha:
            tdr_srv.generar(e, e.senior_revisor)
        for e in manuales:
            for texto, tipo, obligatorio in ITEMS_TDR_MANUALES:
                tdr_srv.agregar(e, e.junior_asignado, texto, tipo, obligatorio)
        pendiente = listos[0]  # En proceso, con obligatorios sin cumplir: el envío a revisión pide confirmación
        for n, e in enumerate(de_ficha + manuales):
            if e.estado == E.LISTO_PARA_ENTREGA:
                objetivo = 1.0
            elif e.pk == pendiente.pk:
                objetivo = AVANCES_TDR[0]
            else:
                objetivo = AVANCES_TDR[n % len(AVANCES_TDR)]
            items = list(e.checklist_tdr.all())
            cumplir = len(items) if objetivo >= 1 else round(objetivo * len(items))
            sustento = e.adjuntos.order_by("id").first()
            for item in items[:cumplir]:
                tdr_srv.marcar(item, e.junior_asignado, ItemChecklistTDR.Estado.CUMPLIDO,
                               sustento if item.tipo == ItemChecklistTDR.Tipo.DOCUMENTO else None)
            if cumplir < len(items) and n % 2 == 0:
                tdr_srv.marcar(items[cumplir], e.junior_asignado, ItemChecklistTDR.Estado.EN_REVISION)
        return (
            f"Checklists por TDR en {len(de_ficha) + len(manuales)} entregables, con 0 % a 100 % de cumplimiento; "
            f"{pendiente.codigo} tiene obligatorios pendientes (al enviarlo a «{E.VERIFICACION_SENIOR.label}» pide confirmación)."
        )

    def _calidad_y_facturas(self, u, clientes, en_revision, listos, hoy):
        """Ítems de calidad por cliente, revisiones conformes y no conforme (RF-45) y facturas simuladas (RF-46)."""
        gerente, senior1 = u["gerente_demo"], u["senior1"]
        C = ItemCalidad.Categoria
        calidad_srv.guardar_item(gerente, cliente=clientes[0], categoria=C.FORMATO,
                                 texto="El informe lleva el código de riesgo operacional exigido por Banco Andino.")
        calidad_srv.guardar_item(senior1, cliente=clientes[2], categoria=C.CONSISTENCIA, obligatorio=False,
                                 texto="Los indicadores de disponibilidad coinciden con el reporte del cliente.")
        v0, v1, v2, v3, v4 = en_revision[:5]
        R = RevisionCalidad.Resultado
        for v in (v0, v2, v3):
            calidad_srv.registrar_conforme(v, v.senior_revisor)
        # v4: un ítem no conforme registra su observación y lo devuelve a En proceso (RF-26).
        items = calidad_srv.items_aplicables(v4)
        respuestas = {i.pk: (R.CONFORME, "") for i in items}
        respuestas[items[0].pk] = (R.NO_CONFORME, "Faltan los anexos de datos que pide el TDR.")
        calidad_srv.registrar(v4, v4.senior_revisor, respuestas)
        Notificacion.objects.filter(entregable=v4, tipo=Notificacion.Tipo.VERIFICACION).delete()  # ya no está en revisión

        # Base de facturación simulada y verificaciones por los servicios (el conector es de solo lectura).
        def factura(numero, e, estado=FacturaSimulada.Estado.EMITIDA, otro_cliente=False, monto="1180.00"):
            contrato = e.contrato
            if otro_cliente:
                contrato = Contrato.objects.exclude(cliente=e.contrato.cliente_id).order_by("pk").first()
            return FacturaSimulada.objects.create(
                numero=numero, cliente_nombre=contrato.cliente.nombre, contrato_numero=contrato.numero_contrato,
                estado=estado, fecha_emision=hoy - datetime.timedelta(days=12), monto=Decimal(monto),
            )

        factura("F001-00101", v0)
        factura_srv.verificar(v0, v0.junior_asignado, "F001-00101")  # correcta
        factura("F001-00102", v2, otro_cliente=True, monto="2360.00")
        factura_srv.verificar(v2, v2.junior_asignado, "F001-00102")  # de otro cliente...
        factura_srv.justificar(
            v2, v2.senior_revisor, "El cliente confirmó por correo que la factura se emitió a su casa matriz; el número es correcto."
        )
        factura("F001-00103", v3, estado=FacturaSimulada.Estado.ANULADA, monto="590.00")
        factura_srv.verificar(v3, v3.junior_asignado, "F001-00103")  # anulada y sin justificar: impide aprobar
        libre = listos[0]
        factura("F001-00104", libre, monto="1475.00")
        factura("F001-00105", libre, otro_cliente=True, monto="3100.00")
        factura("F001-00106", libre, estado=FacturaSimulada.Estado.PAGADA, monto="885.00")
        return (
            f"Calidad: {v0.codigo}, {v2.codigo} y {v3.codigo} con revisión conforme; {v1.codigo} sin revisión (no se puede aprobar); "
            f"{v4.codigo} con revisión no conforme (devuelto a En proceso).\n"
            f"Facturas: {v0.codigo} correcta (F001-00101); {v2.codigo} de otro cliente y justificada (F001-00102); "
            f"{v3.codigo} anulada sin justificar (F001-00103). Para verificar en vivo en {libre.codigo} "
            f"(junior {libre.junior_asignado.username}): F001-00104 (correcta), F001-00105 (otro cliente), F001-00106 (pagada) o un número inexistente."
        )

    @staticmethod
    def _exportaciones(e):
        """Dos exportaciones del mismo entregable aprobado, guardadas como versiones 1 y 2 (RF-47)."""
        exportacion_srv.exportar(e, e.senior_revisor, exportacion_srv.PDF)
        exportacion_srv.exportar(e, e.senior_revisor, exportacion_srv.EXCEL)
        return f"Exportaciones: {e.codigo} tiene un PDF y un Excel guardados como versiones 1 y 2 (tipo Exportación)."

    @staticmethod
    def _valor_extraido(campo):
        tipo = campo["tipo"]
        if tipo == "fecha":
            return "05/11/2026"
        if tipo == "numero":
            return "3"
        if tipo == "opcion":
            return campo["opciones"][0]
        if tipo == "texto_largo":
            return "Revisión de anexos pendiente"
        return "Octubre 2026"

    def _extraccion(self, e):
        """Una extracción pendiente de confirmar, leída de un PDF con texto: el último campo queda sin encontrar (RF-48)."""
        lineas = [f"{c['etiqueta']}: {self._valor_extraido(c)}" for c in e.plantilla.campos_requeridos[:-1]]
        archivo = SimpleUploadedFile(
            "solicitud_cliente_demo.pdf", pdf_minimo("Solicitud del cliente (documento ficticio)", lineas),
            content_type="application/pdf",
        )
        extraccion = extraccion_srv.extraer(e.junior_asignado, archivo, entregable=e)
        return (
            f"Extracción pendiente: {e.junior_asignado.username} tiene «{extraccion.nombre_original}» sobre {e.codigo}; "
            f"en la vista previa falta «{e.plantilla.campos_requeridos[-1]['etiqueta']}»."
        )

    @staticmethod
    def _reportes(u):
        """Un reporte de avance automático y otro a pedido, con su PDF y aviso al gerente (RF-50)."""
        ConfiguracionReporte.cargar()
        reportes_srv.generar(ReporteAvance.Origen.AUTOMATICO)
        reportes_srv.generar(ReporteAvance.Origen.MANUAL, u["gerente_demo"])
        return "Reportes: dos reportes de avance generados (uno automático y otro a pedido); abra «Reportes» como gerente_demo."

    # ------------------------------------------------------------------ limpieza

    @staticmethod
    def _borrar():
        PlantillaTDR.objects.update(documento_formato=None)
        for extraccion in Extraccion.objects.all():
            extraccion.archivo.delete(save=False)  # el archivo de una extracción no tiene señal que lo borre
        Extraccion.objects.all().delete()
        for modelo in (
            ReporteAvance,  # su PDF se borra del disco al confirmar la transacción (ver reportes/signals)
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
            modelo.objects.all().delete()  # los archivos en disco se borran al confirmar la transacción (ver signals)
        Etiqueta.objects.filter(linea_servicio__isnull=True).delete()  # las de línea de servicio las crea la migración
        Usuario.objects.filter(username__in=[x[0] for x in USUARIOS]).delete()
