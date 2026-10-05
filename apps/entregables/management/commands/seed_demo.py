"""Datos simulados para la demostración (SDD §16). Nada de esto corresponde a empresas o personas reales."""
import datetime
import random

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from faker import Faker

from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas
from apps.clientes.models import Cliente, Contrato, PlantillaTDR
from apps.conocimiento.models import LeccionAprendida
from apps.conocimiento.servicios import generar_lecciones, indexar_embeddings
from apps.cuentas.models import Usuario
from apps.entregables import adjuntos
from apps.entregables.demo_archivos import contenido_demo
from apps.entregables.models import Adjunto, Entregable, HistorialEstado, Observacion

CLAVE = "demo1234"
E = Entregable.Estado

USUARIOS = [
    ("admin_demo", "ADMIN", "Alicia", "Administradora"),
    ("gerente_demo", "GERENTE", "Gabriel", "Gerente"),
    ("senior1", "SENIOR", "Sofía", "Sánchez"),
    ("senior2", "SENIOR", "Sergio", "Salazar"),
    ("junior1", "JUNIOR", "Julia", "Jiménez"),
    ("junior2", "JUNIOR", "Javier", "Juárez"),
    ("junior3", "JUNIOR", "Jimena", "Jara"),
]

CLIENTES = [
    ("Banco Andino Ficticio", "BANCA"), ("Financiera Costa Sur (demo)", "BANCA"),
    ("Telecom Pacífico Demo", "TELECOM"), ("Redes Altiplano (demo)", "TELECOM"),
    ("Municipalidad Provincial Ficticia", "PUBLICO"), ("Instituto Regional de Prueba", "PUBLICO"),
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
    ("PLAZO", None, "El informe de cierre llegó fuera de plazo por una revisión tardía del senior.", "Enviar a verificación senior al menos tres días antes del vencimiento."),
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


class Command(BaseCommand):
    help = (
        "Carga datos simulados de demostración (idempotente: si ya existen, no duplica). "
        "Con --reset BORRA todos los clientes, contratos, plantillas, entregables, adjuntos y lecciones, "
        "más los usuarios de demostración, y los vuelve a crear."
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
        for username, rol, nombre, apellido in USUARIOS:
            obj = Usuario(username=username, rol=rol, first_name=nombre, last_name=apellido, email=f"{username}@demo.invalid")
            obj.set_password(CLAVE)
            obj.save()
            u[username] = obj
        seniors, juniors = [u["senior1"], u["senior2"]], [u["junior1"], u["junior2"], u["junior3"]]

        clientes = [Cliente.objects.create(nombre=n, sector=s) for n, s in CLIENTES]
        plantillas = [self._plantilla(p, clientes) for p in PLANTILLAS]

        contratos = []
        for i in range(10):
            c = Contrato.objects.create(
                cliente=clientes[i % len(clientes)], numero_contrato=f"DEMO-2026-{i + 1:03d}",
                descripcion=f"Servicio de consultoría simulado {i + 1}", fecha_inicio=hoy - datetime.timedelta(days=120),
                fecha_fin=hoy + datetime.timedelta(days=240), senior_responsable=seniors[i % 2],
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
            plazo = hoy - datetime.timedelta(days=30) if estado == E.HECHO else hoy + datetime.timedelta(days=PLAZOS[i % len(PLAZOS)])
            e = Entregable.objects.create(
                contrato=contrato, plantilla=plantilla, titulo=f"{TITULO_BASE[plantilla.nombre]} {i + 1:02d}",
                datos={c["nombre"]: self._valor(c, fake, rnd, hoy) for c in plantilla.campos_requeridos},
                plazo=plazo, estado=estado, junior_asignado=rnd.choice(list(contrato.juniors.all())),
                senior_revisor=contrato.senior_responsable, creado_por=contrato.senior_responsable,
            )
            self._historial(e)
            entregables.append(e)

        self._observaciones(entregables)
        sin_adjuntos = self._adjuntos(entregables)
        self._notificaciones(entregables)
        generar_alertas(hoy)

        bloqueados = ", ".join(f"«{e.titulo}» ({e.junior_asignado.username})" for e in sin_adjuntos)
        return (
            f"Listo: {Usuario.objects.count()} usuarios, {Cliente.objects.count()} clientes, {Contrato.objects.count()} contratos, "
            f"{PlantillaTDR.objects.count()} plantillas, {Entregable.objects.count()} entregables, "
            f"{Adjunto.objects.count()} archivos ficticios, {Observacion.objects.count()} observaciones, "
            f"{Notificacion.objects.count()} notificaciones y {LeccionAprendida.objects.count()} lecciones. "
            f"Contraseña de prueba: {CLAVE}\n"
            f"Para ver el bloqueo por adjuntos faltantes, mueva a «Verificación senior»: {bloqueados}."
        )

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
        for n, e in enumerate(en_proceso):  # abiertas: cubren los cinco tipos
            tipo = list(OBSERVACIONES_ABIERTAS)[n % len(OBSERVACIONES_ABIERTAS)]
            Observacion.objects.create(entregable=e, autor=e.senior_revisor, tipo_error=tipo, descripcion=OBSERVACIONES_ABIERTAS[tipo])
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
    def _notificaciones(entregables):
        for e in entregables:
            Notificacion.objects.create(
                usuario=e.junior_asignado, entregable=e, tipo=Notificacion.Tipo.ASIGNACION,
                mensaje=f"Se le asignó «{e.titulo}» (vence el {e.plazo:%d/%m/%Y}).", leida=e.estado != E.A_REALIZAR,
            )
            if e.estado == E.VERIFICACION_SENIOR:
                Notificacion.objects.create(
                    usuario=e.senior_revisor, entregable=e, tipo=Notificacion.Tipo.VERIFICACION,
                    mensaje=f"«{e.titulo}» está en verificación y espera su revisión.",
                )
        for o in Observacion.objects.filter(resuelta=False).select_related("entregable__junior_asignado"):
            Notificacion.objects.create(
                usuario=o.entregable.junior_asignado, entregable=o.entregable, tipo=Notificacion.Tipo.OBSERVACION,
                mensaje=f"Nueva observación en «{o.entregable.titulo}».",
            )

    # ------------------------------------------------------------------ limpieza

    @staticmethod
    def _borrar():
        for modelo in (Notificacion, LeccionAprendida, HistorialEstado, Adjunto, Observacion, Entregable, PlantillaTDR, Contrato, Cliente):
            modelo.objects.all().delete()  # los archivos de los adjuntos se borran del disco al confirmar (ver signals)
        Usuario.objects.filter(username__in=[x[0] for x in USUARIOS]).delete()
