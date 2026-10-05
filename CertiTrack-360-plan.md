# CertiTrack 360 — Plan de implementación (prototipo MVP)

> Documento para Claude Code. Léelo completo antes de escribir código. Trabaja por hitos (sección 12), uno a la vez, y no avances al siguiente hasta cumplir los criterios de aceptación del actual.

## 1. Contexto y problema

CERTICOM S.A.C. atiende a más de 50 clientes de banca, telecomunicaciones y sector público. Su área de Proyectos gestiona entregables documentales (cada Término de Referencia, TDR, exige formato, datos y plazos propios) de forma manual: hojas de cálculo, procesadores de texto, correo, WhatsApp y una nube local.

Consecuencias que la plataforma debe atacar:
- Retrabajo: la información entra incompleta y el entregable rebota entre junior, senior, jefe y auditoría.
- Plazos difíciles de seguir: no hay un lugar único donde ver qué vence y cuándo.
- Dependencia de los seniors: el conocimiento para resolver dudas no queda registrado.
- Sobrecarga operativa por el control manual.

**Reto:** ¿cómo organizar la información y el seguimiento de los proyectos para reducir el retrabajo y agilizar las entregas?

**Solución:** una sola aplicación web, CertiTrack 360, que centraliza el seguimiento de entregables, valida la información antes de que llegue al junior, muestra los plazos en un calendario con alertas y, en una segunda fase, ofrece un chatbot que consulta las lecciones aprendidas de proyectos anteriores.

## 2. Requisitos del cliente (no negociables)

Provienen de la reunión de validación con el asesor de Gerencia General de CERTICOM.

1. Es una **plataforma web independiente** (no un módulo de FileDoc).
2. **Todo corre en servidor local.** Ningún dato ni la solución pueden alojarse en servidores externos ni depender de servicios en la nube. Sin APIs externas, sin telemetría, sin CDNs en tiempo de ejecución (los archivos estáticos se incluyen en el proyecto).
3. El prototipo se prueba **solo con datos simulados**. Nunca cargar datos reales de la empresa o de clientes.
4. **MVP acotado y simple.** Evitar sobrecarga visual: interfaz orientada a la operación diaria, con pocas funciones por pantalla. Si la interfaz fatiga, los colaboradores abandonan la herramienta.
5. **Control de accesos estricto por proyecto y nivel:**
   - Junior: ve solo las tareas y el calendario de lo que tiene asignado.
   - Senior: ve los proyectos que tiene a su cargo.
   - Gerente de Proyectos: único con acceso al consolidado general.
6. El **chatbot** no es un bot de respuestas fijas: es un repositorio de lecciones aprendidas de toda la historia de proyectos.

### Fuera de alcance (el cliente los descartó; no implementar)
- Botón "pedir ayuda al senior" (trabajan juntos en oficina o por WhatsApp).
- Migración o reemplazo de la nube privada local.
- Manual estático de casos atípicos (lo cubre el chatbot).
- Módulo de capacitaciones o programas formativos.
- Gamificación, videojuegos o puntajes.

## 3. Stack tecnológico

| Capa | Elección | Notas |
|---|---|---|
| Lenguaje y framework | Python + Django (versión LTS vigente) | Auth, permisos, admin, ORM, formularios y migraciones ya incluidos |
| Base de datos | SQLite en desarrollo; PostgreSQL en producción | Configurable por variable de entorno |
| Interfaz | Plantillas Django + HTMX + CSS ligero (Tailwind compilado o CSS propio) | Sin SPA; mantener simple |
| Kanban | SortableJS (incluido localmente en `static/`) | Arrastrar y soltar con validación en servidor |
| Calendario | FullCalendar (incluido localmente en `static/`) | Lee eventos desde un endpoint JSON |
| Tareas programadas | django-q2 o APScheduler | Para alertas de vencimiento |
| Chatbot (fase 2) | Ollama local + ChromaDB (o pgvector) | Modelo de código abierto en el servidor local |
| Datos de prueba | Faker (locale `es_PE` o `es_ES`) | Comando de gestión `seed_demo` |
| Pruebas | pytest-django o el runner de Django | |
| Despliegue | Docker Compose (web, db, ollama) | Todo en la red local |

Reglas:
- Pide confirmación antes de añadir dependencias fuera de esta lista.
- No usar CDNs ni fuentes externas: descargar y servir los assets desde `static/`.
- Zona horaria `America/Lima`, idioma `es-pe`. La interfaz y los mensajes van en español.

## 4. Estructura del proyecto

```
certitrack/                 # proyecto Django (settings, urls)
apps/
  cuentas/                  # usuarios, roles, permisos
  clientes/                 # Cliente, Contrato, PlantillaTDR
  entregables/              # Entregable, Observacion, historial de estados
  calendario/               # endpoint de eventos y vista de calendario
  alertas/                  # Notificacion y tareas programadas
  conocimiento/             # LeccionAprendida y chatbot (fase 2)
  reportes/                 # solo placeholder (fase 3)
templates/  static/  docs/
docker-compose.yml  .env.example  README.md
```

## 5. Modelo de datos

**Usuario** (extiende el de Django): nombre, rol (`JUNIOR`, `SENIOR`, `GERENTE`, `ADMIN`).

**Cliente**: nombre, sector (`BANCA`, `TELECOM`, `PUBLICO`), activo.

**Contrato**: cliente, numero_contrato, descripcion, fecha_inicio, fecha_fin, senior_responsable (FK Usuario), juniors (M2M Usuario).

**PlantillaTDR**: cliente (o genérica), nombre, formato (texto), `campos_requeridos` (JSON: lista de campos con nombre, tipo y etiqueta), plazo_dias_por_defecto.

**Entregable**: contrato, plantilla, titulo, datos (JSON con los campos de la plantilla), plazo (fecha), estado, junior_asignado, senior_revisor, creado_por, creado_en, actualizado_en.

**Observacion**: entregable, autor, tipo_error (catálogo: `DATO_FALTANTE`, `FORMATO`, `PLAZO`, `CONTENIDO`, `OTRO`), descripcion, solucion (texto, se completa al resolverse), resuelta (bool), creada_en.

**HistorialEstado**: entregable, estado_anterior, estado_nuevo, usuario, fecha.

**Notificacion**: usuario, entregable, mensaje, tipo (`VENCIMIENTO`, `OBSERVACION`, `ASIGNACION`), leida, creada_en.

**LeccionAprendida** (fase 2): entregable_origen, cliente, tipo_error, problema, solucion, creada_en. Se genera a partir de observaciones resueltas de entregables cerrados.

Importante: guarda las observaciones con `tipo_error` y `solucion` estructurados desde la fase 1; son la materia prima del chatbot.

## 6. Roles y permisos

| Acción | Junior | Senior | Gerente | Admin |
|---|---|---|---|---|
| Ver sus entregables asignados | Sí | Sí | Sí | Sí |
| Ver entregables de contratos a su cargo | No | Sí | Sí | Sí |
| Ver consolidado de todos los proyectos | No | No | Sí | Sí |
| Crear entregable (con validación Poka-Yoke) | No | Sí | Sí | Sí |
| Mover tarjeta hacia adelante hasta Verificación Senior | Sí | Sí | Sí | Sí |
| Aprobar o devolver desde Verificación Senior | No | Sí | Sí | Sí |
| Registrar observaciones | No | Sí | Sí | Sí |
| Gestionar clientes, contratos y plantillas | No | No | Sí | Sí |

Aplica los filtros de visibilidad en el queryset base de cada vista y en el endpoint del calendario, no solo en la interfaz. Cubre esto con pruebas.

## 7. Poka-Yoke (validación al ingreso)

- Al crear un Entregable se elige una PlantillaTDR; el formulario se genera con sus `campos_requeridos`.
- No se puede guardar ni asignar al junior si falta algún campo obligatorio, si el plazo es anterior a hoy o si no hay contrato.
- Los mensajes de error deben decir exactamente qué falta.
- Empieza con pocos campos obligatorios por plantilla (decisión de diseño, ajustable) para no frenar el trabajo; el administrador puede ampliarlos.

## 8. Kanban y flujo de estados

Columnas: `A_REALIZAR` → `EN_PROCESO` → `VERIFICACION_SENIOR` → `LISTO_PARA_ENTREGA` → `HECHO`.

Transiciones permitidas (decisión de diseño, ajustable):
- A_REALIZAR → EN_PROCESO: junior asignado.
- EN_PROCESO → VERIFICACION_SENIOR: junior asignado.
- VERIFICACION_SENIOR → LISTO_PARA_ENTREGA: senior revisor (aprueba).
- VERIFICACION_SENIOR → EN_PROCESO: senior revisor; **exige** crear una observación.
- LISTO_PARA_ENTREGA → HECHO: senior o gerente.

Cada transición se valida en el servidor y se registra en `HistorialEstado`. Cada tarjeta muestra cliente, número de contrato, plazo y responsable, y sus observaciones quedan en la misma tarjeta.

## 9. Calendario unificado y alertas

- Vista de calendario con los plazos de los entregables visibles para el usuario según su rol.
- Alertas internas (notificaciones dentro de la app) cuando un plazo se acerca. Umbrales por defecto: 5 días, 2 días y el día del vencimiento (configurables).
- Una tarea programada genera las `Notificacion` evitando duplicados. Indicador de notificaciones no leídas en la barra superior.
- Canales externos (correo, WhatsApp) quedan fuera del MVP.

## 10. Chatbot de lecciones aprendidas (fase 2)

- Ollama corriendo en el servidor local con un modelo de código abierto; ChromaDB (o pgvector) para la búsqueda sobre `LeccionAprendida`.
- Comando para indexar lecciones nuevas; se ejecuta al cerrar entregables o de forma programada.
- La respuesta cita el caso de origen (cliente, contrato, entregable) y enlaza a él respetando los permisos del usuario.
- Si Ollama no está disponible, la pantalla muestra un aviso claro y el resto de la app sigue funcionando.
- Para el prototipo: base de 15 a 20 lecciones ficticias.
- Ningún dato sale del servidor local.

## 11. Datos simulados

Comando `python manage.py seed_demo`:
- 1 admin, 1 gerente, 2 seniors, 3 juniors, con contraseñas de prueba documentadas solo en el README del prototipo.
- 6 clientes ficticios (banca, telecom, sector público) con nombres inventados que no correspondan a empresas reales.
- Unos 10 contratos y 30 entregables repartidos en todos los estados, con plazos variados (algunos vencidos y otros por vencer) y varios con observaciones resueltas.
- Algunas plantillas con campos requeridos distintos para demostrar el Poka-Yoke.
- Debe poder ejecutarse varias veces sin duplicar datos (opción `--reset`).

## 12. Hitos (ejecuta en orden)

**H0 — Preparación.** Proyecto Django, apps vacías, `.env.example`, configuración de zona horaria e idioma, assets estáticos locales, README inicial.
*Aceptación:* `runserver` levanta y muestra una página de inicio en español.

**H1 — Usuarios y roles.** Login, logout, modelo de usuario con rol, redirección según rol, plantilla base simple.
*Aceptación:* los cuatro roles inician sesión y ven la navegación que les corresponde.

**H2 — Clientes, contratos y plantillas.** CRUD para gerente y admin; asignación de senior responsable y juniors al contrato.
*Aceptación:* un junior no puede acceder a estas pantallas (prueba automatizada).

**H3 — Entregables y Poka-Yoke.** Modelo, formulario dinámico por plantilla, validaciones, lista filtrada por rol.
*Aceptación:* no se puede crear un entregable con datos obligatorios faltantes y el mensaje indica cuáles; cada rol solo ve lo suyo.

**H4 — Kanban.** Tablero con arrastrar y soltar, máquina de estados, historial, observaciones obligatorias al devolver.
*Aceptación:* las transiciones no permitidas se rechazan en el servidor; el historial registra cada cambio.

**H5 — Calendario y alertas.** Calendario por rol, tarea programada de alertas, notificaciones.
*Aceptación:* un entregable próximo a vencer genera una sola notificación por umbral; el calendario de un junior muestra solo sus tareas.

**H6 — Datos simulados y pruebas.** Comando `seed_demo`, pruebas de permisos, estados y Poka-Yoke, README con guía de la demo.
*Aceptación:* con la base vacía, `seed_demo` deja el sistema listo para una demostración completa; las pruebas pasan.

**H7 — Chatbot (fase 2).** Modelo `LeccionAprendida`, indexación, pantalla de consulta con citas.
*Aceptación:* una pregunta sobre un error frecuente devuelve una respuesta que cita un caso ficticio existente.

**H8 — Fase 3 (solo visión).** No implementar. Dejar en `docs/hoja-de-ruta.md` la descripción de asignación automática por carga y capacitación y de reportes para el gerente.

## 13. Interfaz

- Pocas pantallas: Inicio (resumen según rol), Tablero Kanban, Calendario, Entregable (detalle y observaciones), Notificaciones, Administración, Asistente (fase 2).
- Una acción principal por pantalla, paleta sobria, buen contraste, tipografía legible, sin adornos ni elementos de juego.
- Usable en pantalla de escritorio; que no se rompa en tablet.
- Etiquetas y mensajes en español claro, sin jerga técnica.

## 14. Despliegue

- `docker-compose.yml` con servicios `web`, `db` (PostgreSQL) y `ollama` (este último solo para la fase 2).
- Variables en `.env`; sin secretos en el repositorio.
- Sin llamadas de red a internet en tiempo de ejecución.

## 15. Instrucciones de trabajo para Claude Code

1. Trabaja un hito a la vez; al terminar, ejecuta las pruebas y haz un commit con un mensaje claro.
2. Antes de añadir una dependencia nueva, pregunta.
3. No inventes datos reales ni uses nombres de empresas reales en los datos de prueba.
4. Si un requisito del cliente (sección 2) choca con una decisión de diseño, gana el requisito del cliente; avisa del conflicto.
5. Las decisiones marcadas como "ajustables" pueden cambiar si el equipo lo pide.
6. Mantén el código y los comentarios claros; los textos de interfaz, en español.

## 16. Decisiones abiertas para el equipo

- ¿SQLite o PostgreSQL desde el inicio del prototipo?
- ¿Los umbrales de alerta (5, 2 y 0 días) son los adecuados para el área?
- ¿Qué campos obligatorios mínimos deben tener las plantillas de ejemplo?
- ¿Se prefiere mostrar el chatbot como pantalla aparte o como panel dentro del entregable?
- ¿Qué modelo de Ollama usarán según la capacidad del equipo de demostración?
