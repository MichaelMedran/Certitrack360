"""Datos simulados para la demostración. Nada de esto corresponde a empresas o personas reales."""
import datetime
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas
from apps.clientes.models import Cliente, Contrato, PlantillaTDR
from apps.conocimiento.models import LeccionAprendida
from apps.conocimiento.servicios import indexar_lecciones
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable, HistorialEstado, Observacion, TipoError

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

PLANTILLAS = [
    ("Informe técnico mensual", "Informe en PDF", 10, [("Periodo reportado", "texto"), ("Responsable del cliente", "texto")]),
    ("Acta de conformidad", "Acta firmada", 7, [("Fecha de reunión", "fecha"), ("Participantes", "texto_largo"), ("Número de acta", "texto")]),
    ("Matriz de riesgos", "Hoja de cálculo", 15, [("Nivel de riesgo", "numero"), ("Descripción del riesgo", "texto_largo")]),
]

TITULOS = ["Informe técnico", "Acta de conformidad", "Matriz de riesgos", "Informe de avance", "Entregable de cierre"]

LECCIONES = [
    ("DATO_FALTANTE", "El informe mensual se devolvió porque faltaba el periodo reportado en la carátula.", "Verificar la carátula contra la plantilla antes de enviar a revisión; el periodo va con formato mes-año."),
    ("DATO_FALTANTE", "El acta de conformidad no tenía la lista completa de participantes del cliente.", "Pedir el listado de asistentes al terminar la reunión y adjuntarlo al acta el mismo día."),
    ("FORMATO", "El cliente bancario rechazó el informe por usar una plantilla con numeración de páginas distinta.", "Usar la plantilla vigente del TDR; la numeración debe ser «Página X de Y» en el pie."),
    ("FORMATO", "La matriz de riesgos se entregó en un formato que el cliente de telecomunicaciones no pudo abrir.", "Exportar la matriz en el formato exigido por el TDR y probar la apertura antes de entregar."),
    ("PLAZO", "El informe de cierre llegó fuera de plazo por una revisión tardía del senior.", "Enviar a verificación senior al menos tres días antes del vencimiento."),
    ("PLAZO", "Se confundió el plazo del TDR con el plazo interno y se entregó un día después.", "Registrar siempre el plazo contractual en el sistema y usar la alerta de cinco días."),
    ("CONTENIDO", "El informe técnico no incluía las conclusiones que pide el TDR del sector público.", "Revisar la lista de secciones obligatorias del TDR; las conclusiones van antes de los anexos."),
    ("CONTENIDO", "Cifras inconsistentes entre el resumen ejecutivo y el anexo de datos.", "Actualizar el resumen al final, copiando las cifras del anexo ya validado."),
    ("DATO_FALTANTE", "No se consignó el número de contrato en el acta del instituto regional.", "El número de contrato debe copiarse desde la ficha del contrato en CertiTrack, no escribirse a mano."),
    ("FORMATO", "El archivo superó el tamaño máximo que acepta la mesa de partes del cliente público.", "Comprimir las imágenes y entregar un PDF menor a 10 MB; adjuntar anexos aparte."),
    ("OTRO", "El cliente pidió una versión firmada digitalmente y se entregó solo la versión escaneada.", "Confirmar al inicio si el TDR exige firma digital y coordinar con el firmante autorizado."),
    ("CONTENIDO", "La descripción del riesgo era demasiado genérica para el cliente bancario.", "Incluir causa, impacto y responsable en cada riesgo, con un ejemplo concreto."),
    ("PLAZO", "La prórroga acordada por teléfono no quedó registrada y el entregable figuró como vencido.", "Registrar toda prórroga por escrito y actualizar el plazo en el sistema."),
    ("DATO_FALTANTE", "Faltaba el nombre del responsable del cliente en el informe técnico mensual.", "Mantener el responsable del cliente en la ficha del contrato y revisarlo cada trimestre."),
    ("OTRO", "Se usó una versión antigua del anexo técnico.", "Descargar siempre el anexo desde la carpeta vigente del contrato y verificar la fecha de versión."),
    ("FORMATO", "Los títulos del informe no seguían el estilo exigido por el TDR de telecomunicaciones.", "Aplicar los estilos de título de la plantilla; no formatear manualmente."),
]


class Command(BaseCommand):
    help = "Carga datos simulados de demostración (idempotente). Use --reset para empezar de cero."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra los datos de demostración antes de crearlos.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            self._borrar()
        if Entregable.objects.exists() and Usuario.objects.filter(username="gerente_demo").exists():
            self.stdout.write("Ya existen datos de demostración. Use --reset para recrearlos.")
            return
        rnd = random.Random(2026)
        fake = Faker("es_ES")
        fake.seed_instance(2026)
        hoy = timezone.localdate()

        u = {}
        for username, rol, nombre, apellido in USUARIOS:
            obj = Usuario(username=username, rol=rol, first_name=nombre, last_name=apellido,
                          email=f"{username}@demo.invalid", is_staff=rol == "ADMIN", is_superuser=rol == "ADMIN")
            obj.set_password(CLAVE)
            obj.save()
            u[username] = obj
        seniors, juniors = [u["senior1"], u["senior2"]], [u["junior1"], u["junior2"], u["junior3"]]

        clientes = [Cliente.objects.create(nombre=n, sector=s) for n, s in CLIENTES]

        plantillas = []
        for nombre, formato, dias, campos in PLANTILLAS:
            lista = [{"nombre": "c_" + "".join(ch if ch.isalnum() else "_" for ch in et.lower()), "etiqueta": et, "tipo": t} for et, t in campos]
            plantillas.append(PlantillaTDR.objects.create(
                nombre=nombre, formato=formato, plazo_dias_por_defecto=dias, campos_requeridos=lista,
                cliente=clientes[0] if nombre == "Acta de conformidad" else None,
            ))

        contratos = []
        for i in range(10):
            c = Contrato.objects.create(
                cliente=clientes[i % len(clientes)], numero_contrato=f"DEMO-2026-{i + 1:03d}",
                descripcion=f"Servicio de consultoría simulado {i + 1}", fecha_inicio=hoy - datetime.timedelta(days=120),
                fecha_fin=hoy + datetime.timedelta(days=240), senior_responsable=seniors[i % 2],
            )
            c.juniors.set(rnd.sample(juniors, 2))
            contratos.append(c)

        # 30 entregables repartidos en todos los estados
        estados = [E.A_REALIZAR] * 7 + [E.EN_PROCESO] * 7 + [E.VERIFICACION_SENIOR] * 5 + [E.LISTO_PARA_ENTREGA] * 4 + [E.HECHO] * 7
        plazos = [-6, -2, 0, 1, 2, 4, 5, 8, 12, 20]
        n_obs = 0
        for i, estado in enumerate(estados):
            contrato = contratos[i % len(contratos)]
            plantilla = plantillas[i % len(plantillas)]
            datos = {}
            for c in plantilla.campos_requeridos:
                datos[c["nombre"]] = {"fecha": (hoy - datetime.timedelta(days=3)).isoformat(), "numero": str(rnd.randint(1, 5))}.get(
                    c["tipo"], fake.sentence(nb_words=4) if c["tipo"] == "texto_largo" else fake.word().capitalize())
            plazo = hoy - datetime.timedelta(days=30) if estado == E.HECHO else hoy + datetime.timedelta(days=plazos[i % len(plazos)])
            e = Entregable.objects.create(
                contrato=contrato, plantilla=plantilla, titulo=f"{TITULOS[i % len(TITULOS)]} {i + 1:02d}", datos=datos,
                plazo=plazo, estado=estado, junior_asignado=rnd.choice(list(contrato.juniors.all())),
                senior_revisor=contrato.senior_responsable, creado_por=contrato.senior_responsable,
            )
            HistorialEstado.objects.create(entregable=e, estado_nuevo=E.A_REALIZAR, usuario=e.creado_por)
            # historial coherente con el estado alcanzado
            ruta = [E.A_REALIZAR, E.EN_PROCESO, E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA, E.HECHO]
            for ant, nuevo in zip(ruta, ruta[1:ruta.index(estado) + 1]):
                HistorialEstado.objects.create(
                    entregable=e, estado_anterior=ant, estado_nuevo=nuevo,
                    usuario=e.junior_asignado if nuevo in (E.EN_PROCESO, E.VERIFICACION_SENIOR) else e.senior_revisor)
            # observaciones resueltas en entregables avanzados
            if estado in (E.EN_PROCESO, E.LISTO_PARA_ENTREGA, E.HECHO) and i % 2 == 0:
                tipo, problema, solucion = LECCIONES[n_obs % len(LECCIONES)]
                Observacion.objects.create(entregable=e, autor=e.senior_revisor, tipo_error=tipo,
                                           descripcion=problema, solucion=solucion, resuelta=True)
                n_obs += 1
            if estado == E.EN_PROCESO and i % 3 == 0:
                Observacion.objects.create(entregable=e, autor=e.senior_revisor, tipo_error=TipoError.FORMATO,
                                           descripcion="Ajustar los títulos al estilo de la plantilla.")

        indexar_lecciones()  # observaciones resueltas de entregables HECHO
        # Completar hasta 16 lecciones ficticias históricas (proyectos anteriores)
        existentes = set(LeccionAprendida.objects.values_list("problema", flat=True))
        for j, (tipo, problema, solucion) in enumerate(LECCIONES):
            if problema not in existentes:
                LeccionAprendida.objects.create(cliente=clientes[j % len(clientes)], tipo_error=tipo, problema=problema, solucion=solucion)

        generar_alertas(hoy)
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {Usuario.objects.count()} usuarios, {Cliente.objects.count()} clientes, {Contrato.objects.count()} contratos, "
            f"{Entregable.objects.count()} entregables, {LeccionAprendida.objects.count()} lecciones. Contraseña de prueba: {CLAVE}"))

    def _borrar(self):
        for modelo in (Notificacion, LeccionAprendida, HistorialEstado, Observacion, Entregable, PlantillaTDR, Contrato, Cliente):
            modelo.objects.all().delete()
        Usuario.objects.filter(username__in=[x[0] for x in USUARIOS]).delete()
