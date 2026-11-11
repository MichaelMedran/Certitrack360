# CertiTrack 360 (prototipo MVP)

Plataforma web local para el seguimiento de los entregables documentales del área de Proyectos. Todo corre en el servidor
local: sin APIs externas, sin CDNs, sin telemetría. **Solo se usan datos simulados.**

- **Estado frente al SDD v1.0 y al SDD del Sprint 2:** [`docs/trazabilidad.md`](docs/trazabilidad.md) (requisito por requisito, con sus pruebas).
- **Wireframes (H0.5):** [`docs/wireframes/index.html`](docs/wireframes/index.html), aprobados por el equipo el 2026-10-05. La interfaz se construyó sobre ellos:
  adjuntos en el detalle, filtros y urgencia en tablero y lista, Kanban con HTMX, Consolidado, editor de plantillas y notificaciones.
- **Sprint 2:** especificación en [`docs/sdd-sprint-2.md`](docs/sdd-sprint-2.md) y wireframes en [`docs/wireframes/sprint-2.html`](docs/wireframes/sprint-2.html)
  (aprobados el 2026-11-02). Completado en los hitos S2-H1 a S2-H13; la trazabilidad completa está en [`docs/trazabilidad.md`](docs/trazabilidad.md).

## Puesta en marcha (desarrollo)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env                                  # opcional: los valores por defecto sirven para desarrollo
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo --reset      # datos simulados (Sprint 1 + Sprint 2)
.\.venv\Scripts\python manage.py runserver
```

Abrir http://127.0.0.1:8000/. Pruebas: `.\.venv\Scripts\python manage.py test` (menos de un minuto).

Si ya tenía datos de una versión anterior, `migrate` los conserva; `seed_demo --reset` los reemplaza por los de demostración
(**borra todos los clientes, contratos, plantillas, fichas, entregables, adjuntos, entregas, tiempos, documentos del repositorio, procedimientos, planes de incorporación y lecciones**, más los usuarios de demostración).

### Servidor de producción (RF-51)

`python manage.py servir` reemplaza a `runserver` fuera del desarrollo: arranca waitress (`--host`, `--puerto`, `--hilos`; por defecto `SERVIDOR_PUERTO` y `SERVIDOR_HILOS`)
y recopila los estáticos que sirve WhiteNoise. Toda respuesta lleva `Content-Security-Policy` (solo el propio servidor y, si se configura, `FILEDOC_URL`) y el ingreso se
bloquea tras `LOGIN_MAX_INTENTOS` fallos. Guía completa de instalación, respaldos y programador: [`docs/despliegue.md`](docs/despliegue.md).

### Tareas programadas

`python manage.py programador` deja corriendo (en otra terminal) las alertas de vencimiento y de actas pendientes, cada hora, y la indexación de lecciones y procedimientos vigentes del
asistente, a diario a las 02:00 (hora de Lima). Se pueden lanzar a mano: `generar_alertas` e `indexar_lecciones`. En Docker es el servicio `programador`.

## Usuarios de prueba (contraseña `demo1234`, solo para este prototipo)

| Usuario | Rol | Ve |
|---|---|---|
| `admin_demo` | Administrador | Todo, más el panel técnico en `/admin/` |
| `gerente_demo` | Gerente de Proyectos | Todos los proyectos; gestiona clientes, contratos, plantillas, personal, procedimientos y planes de incorporación |
| `senior1`, `senior2` | Senior | Los contratos a su cargo |
| `junior1`, `junior2`, `junior3` | Junior | Solo lo que tienen asignado |

## Guion de demostración

Recorre el flujo con el seed. Cada paso dice con qué usuario hacerlo.

1. **Ingreso y roles.** Entrar como `junior1`: el inicio muestra solo sus cifras, sus próximos plazos y sus notificaciones recientes, y la barra no tiene «Consolidado», «Gestión» ni «Administración». Cerrar sesión y entrar como `gerente_demo`: aparecen «Consolidado» y «Gestión» y ve todos los proyectos. `admin_demo` ve además «Administración» (el panel técnico).
2. **Poka-Yoke al crear.** Como `senior1`: *Entregables → Nuevo entregable*. Elegir «Matriz de riesgos» (el panel informa que esa plantilla no exige adjuntos; la de «Informe técnico mensual» exige «Borrador»). Al elegir el contrato se ven, de solo lectura, su cliente y su línea de servicio. Dejar vacíos el ID-TDR y «Nivel de riesgo», poner una fecha de recepción futura o posterior al plazo, una fecha de plazo pasada y probar sin elegir «Impacto» (campo de opción): los mensajes dicen exactamente qué falta y el formulario conserva lo escrito. Elegir el *senior revisor* (por omisión, el responsable del contrato). Completar y crear: el entregable recibe su código (`CT-AAAA-NNNNN`) y el junior elegido, un aviso de asignación con ese código.
3. **Kanban.** Entrar como ese junior (o cualquiera con tarjetas en «Por hacer»): *Tablero*. Las columnas son las de HU-04: Por hacer, En proceso, Revisión senior, Aprobado y Entregado. Cada tarjeta lleva su código, su urgencia en texto («Vencido», «Crítico», «Próximo», «Normal»), los adjuntos y las observaciones abiertas. Arrastrar una tarjeta de «Por hacer» a «En proceso». Intentar saltar a «Entregado»: el servidor lo rechaza y la tarjeta vuelve a su columna con el motivo. Sin ratón, se abre la tarjeta y se usa «Mover entregable».
4. **Adjuntos requeridos.** El comando `seed_demo` imprime al terminar qué dos tarjetas «En proceso» quedaron sin sus adjuntos y a qué junior pertenecen. Entrar como ese junior y arrastrar una a «Revisión senior»: aparece un único mensaje con los adjuntos que faltan. Abrir la tarjeta: en «Adjuntos» se ve qué falta («Borrador — falta»). Subir un archivo (pdf, docx, xlsx, pptx, png, jpg o txt; máximo 10 MB); una segunda subida del mismo tipo crea la versión 2 y deja la anterior en «Ver versiones anteriores». Con el adjunto subido, la tarjeta ya pasa a revisión. Solo el gerente y el admin pueden eliminar un adjunto, y se les pide confirmación.
5. **Revisión y devolución.** Como un senior con tarjetas en «Revisión senior»: arrastrar una a «En proceso» abre el diálogo «Devolver al junior», que pide el tipo de error y la descripción. Aprobar otra a «Aprobado» y luego pasarla a «Entregado» (al cerrarla, sus observaciones resueltas pasan a ser lecciones aprendidas).
6. **Notificaciones.** Como ese senior, *Avisos*: hay avisos de entregables en revisión senior. Como un junior: asignaciones, observaciones y vencimientos. Cada aviso lleva el código del entregable y se marca como leído con su propio botón (o todos a la vez), y el indicador de la barra baja. Cada persona ve solo los suyos.
7. **Calendario.** Cada evento dice su estado, su código, el cliente, el responsable («a cargo de …»), el entregable y su urgencia en texto («— Crítico», «— Vencido»); un junior ve solo sus plazos. «Filtros» por cliente, estado y responsable se aplican sin recargar y sin salir del mes que se mira, y nunca muestran plazos ajenos. En pantallas angostas se muestra como lista.
8. **Filtros y urgencia.** En *Tablero* y *Entregables*, abrir «Filtros»: cliente, contrato, responsable, urgencia, tipo de observación abierta (solo cuenta las no resueltas), estado, línea de servicio y orden. La lista suma las columnas Código e ID-TDR. Se aplican al cambiar cada control, sin recargar la página; los chips «Activos» permiten quitar uno a uno y «Limpiar» los quita todos. La dirección queda con los filtros (se puede copiar o volver con «Atrás»). Un filtro nunca muestra más de lo que el rol puede ver.
9. **Asistente (fase 2).** Preguntar «falta el periodo reportado en el informe»: devuelve el caso de origen citado (cliente, contrato, entregable). Sin Ollama lo avisa y busca por palabras.
10. **Consolidado.** Como `gerente_demo`: *Consolidado* (o «Ver consolidado» en el inicio). Cifras por estado, vencidos, próximos a vencer, resumen por cliente y por contrato, y carga por persona; se puede filtrar por cliente, contrato, estado y rango de plazo. Un junior o un senior reciben «sin permiso». Es de solo lectura.
11. **Gestión.** Como `gerente_demo`: *Gestión* con las pestañas Clientes, Contratos, Plantillas y Líneas de servicio. En *Plantillas*, crear una con el editor de campos: «Agregar campo», subir o bajar, tipo «Opción» con sus opciones separadas por comas, y los adjuntos obligatorios. Renombrar un campo de una plantilla existente no hace perder los datos de los entregables ya creados. Un cliente o contrato no se borra: se desmarca «Activo». En *Líneas de servicio* (BPO, Custodia, Digitalización, Banca y Estado) se crean, renombran y activan o desactivan líneas; el contrato exige la suya. Un junior o un senior reciben «sin permiso».
12. **«Atrás» del navegador.** Las páginas con sesión no se guardan en la caché del navegador: al volver con «Atrás» se ve el estado real del tablero, no una copia vieja.

## Guion de demostración del Sprint 2

Recorre las pantallas y reglas nuevas del Sprint 2 sobre los datos de `seed_demo --reset`:

1. **Fichas de levantamiento (`/fichas/`, RF-30).** Entrar como `senior1` o `gerente_demo` y abrir *Fichas*: hay una ficha confirmada («TDR-BAF-LEV-001») con su estado documental inicial congelado y otra en borrador («TDR-FCS-LEV-002») con ítems mensual y quincenal listos para revisar en la vista previa y confirmar. Al confirmar una ficha se crean sus entregables recurrentes con código `CT-AAAA-NNNNN`, ID-TDR heredado y aviso al junior; al actualizar después el estado documental actual, la fotografía inicial congelada no cambia.
2. **Observaciones por estado y subestado (`/observaciones/`, RF-25, RF-26, RF-27).** En *Entregables → Observaciones*, filtrar por estado (`Pendiente`, `En corrección`, `Resuelta`) y abrir el detalle de un entregable con correcciones: el junior asignado registra su acción correctiva y evidencia (pasa a «En corrección» y avisa al senior); el senior confirma la resolución o la rechaza (si estaba en revisión, lo devuelve a «En proceso · Con correcciones pendientes»). Ningún entregable pasa a «Revisión senior» con observaciones pendientes ni se aprueba con observaciones abiertas.
3. **Versiones vigentes, entregas con cargo y actas (`/entregas/`, RF-28, RF-29).** En el detalle de un entregable con varias versiones de «Borrador», ver la fila marcada «Vigente · v2» y «Ver versiones anteriores», desde donde el senior puede restaurar la v1 como una nueva v3. En un entregable «Aprobado», usar «Marcar como entregado» (`/entregables/<id>/entregar/`): exige subir el cargo de recepción, bloquea la versión enviada para que nadie pueda eliminarla y registra la entrega en `/entregas/`. En `/entregas/` hay entregas con acta Recibida, Observada y una con acta Pendiente de hace 6 días (al correr `python manage.py generar_alertas` emite el aviso de acta pendiente). Un entregable con acta Observada ofrece «Reabrir para corrección».
4. **Personal, responsables de apoyo y avisos de conflicto (`/personal/`, RF-31).** Como `gerente_demo`, abrir *Gestión → Personal* (`/personal/`): muestra el puesto, la carga activa, los apoyos y las ausencias registradas (hay una ausencia próxima para `junior2`). En el detalle de un entregable, sección «Responsables», sumar un responsable de apoyo o reasignar el responsable principal: si el candidato tiene ausencia, sobrecarga o un plazo cercano, el sistema muestra la advertencia de conflictos antes de pedir confirmación y deja constancia en el historial.
5. **Registro de tiempo por etapa (`/tiempos/`, RF-32).** En el detalle de un entregable, sección «Tiempo por etapa», iniciar el cronómetro en Recopilación, Consolidación o Revisión (si el usuario tenía otro cronómetro abierto, se pausa automáticamente) o registrar un bloque manual indicando el motivo obligatorio. En *Entregables → Tiempos* (`/tiempos/`), filtrar por cliente, etapa, responsable y fechas; cada junior ve únicamente sus propios registros.
6. **Panel de indicadores (`/indicadores/`, RF-33).** Abrir *Indicadores* como `gerente_demo`, `senior1` o `junior1`: las cuatro tarjetas (% entregados a tiempo, % con reproceso, tiempo promedio de elaboración y observaciones por tipo de error) muestran su fórmula exacta al desplegar «¿Cómo se calcula?», junto con las tablas por tipo de entregable, por tipo de error y (para senior, gerente y admin) por responsable.
7. **Repositorio documental y publicación anonimizada (`/repositorio/`, RF-34, RF-35).** Abrir *Repositorio*: pestañas «Plantillas de clientes», «Plantillas generales», «Ejemplos anonimizados» y «Procedimientos». Entrar como `junior1` y verificar que solo ve las plantillas de los clientes de sus contratos activos, más las genéricas y los ejemplos anonimizados. Como `senior1`, publicar un ejemplo anonimizado en `/repositorio/publicar-anonimizado/`: si falta cualquiera de las 4 confirmaciones de la lista de verificación NDA, el servidor rechaza la publicación indicando cuántas faltan. Como `gerente_demo`, abrir el detalle de un documento para ver el historial de versiones y el registro de cargas y descargas.
8. **Buscador global (`/buscar/`, RF-36).** Escribir en la caja de búsqueda de la barra superior (por ejemplo `informe`, `banco` o `matriz`, con o sin tildes): muestra resultados agrupados en Entregables, Contratos, Clientes, Adjuntos y Repositorio respetando siempre la visibilidad del rol, con filtros por fechas, tipo de documento, estado y cliente.
9. **Asistente ampliado con procedimientos y valoración (`/asistente/`, RF-37).** En *Asistente*, preguntar por ejemplo «cómo presentar el cargo de entrega en mesa de partes» o «falta el periodo reportado en el informe»: responde citando tanto `[Procedimiento N]` (procedimientos vigentes aprobados) como `[Caso N]` (lecciones aprendidas; si provienen de un entregable no visible para el usuario, muestran el cliente pero sin enlace). Valorar la respuesta con «¿Le sirvió esta respuesta? Sí / No» y revisar la tabla «Mis consultas anteriores» (exclusiva de cada usuario). Como `gerente_demo`, gestionar el catálogo en `/procedimientos/`.
10. **Plan de incorporación (`/incorporacion/`, RF-38).** Entrar como `junior3`: en *Inicio* aparece la tarjeta «Mi incorporación» con su barra de progreso (5 de 11 actividades completadas) y enlace a `/incorporacion/`. En `/incorporacion/`, marcar las actividades pendientes como «Completada» y comprobar que los materiales enlazan siempre a la versión vigente del repositorio o al procedimiento aprobado. Entrar luego como `senior1` (su responsable asignado): una vez que todas las actividades están completadas, el botón «Confirmar finalización del plan» cierra la incorporación. Como `gerente_demo`, administrar los planes y asignaciones en `/incorporacion/planes/`.

## Configuración (`.env`, ver `.env.example`)

| Variable | Uso | Por defecto |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta | valor de desarrollo (**cambiar en producción**) |
| `DJANGO_DEBUG` | Modo de depuración (`0` en producción) | `1` |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos (para entrar desde otro equipo de la red, agregar su nombre o IP) | `localhost,127.0.0.1` |
| `DJANGO_COOKIE_SECURE` | Cookies solo por HTTPS | activas si `DJANGO_DEBUG=0` (poner `0` en una red sin HTTPS) |
| `DATABASE_URL` | `sqlite:///db.sqlite3` o `postgres://usuario:clave@host:5432/nombre` | SQLite |
| `MEDIA_ROOT` | Carpeta de los adjuntos (fuera del código, sin URL pública) | `media/` |
| `MEDIA_MAX_UPLOAD_MB` | Tamaño máximo de un adjunto | `10` |
| `ALLOWED_UPLOAD_EXTENSIONS` | Extensiones permitidas | `pdf,docx,xlsx,pptx,png,jpg,txt` |
| `ALERT_THRESHOLDS_DAYS` | Alertas (una por umbral) y urgencia: mayor = «próximo», segundo mayor = «crítico». Avisos a 5 días, 48 h, 24 h y el mismo día; «crítico» empieza a 2 días (SDD del Sprint 2, RF-22) | `5,2,1,0` |
| `CODIGO_PREFIJO` | Prefijo del código de los entregables (`CT-2026-00031`); de 1 a 10 letras o números | `CT` |
| `ACTA_DIAS_PENDIENTE` | Días tras la entrega para emitir la alerta de acta de conformidad pendiente (RF-29) | `5` |
| `CARGA_MAXIMA_ACTIVOS` | Umbral de entregables activos a partir del cual se avisa sobrecarga al asignar (RF-31) | `8` |
| `FICHA_MAX_ENTREGABLES` | Tope de entregables generados al confirmar una ficha de levantamiento (RF-30) | `60` |
| `BUSCADOR_LIMITE` | Máximo de resultados por categoría en el buscador global `/buscar/` (RF-36) | `20` |
| `CONSOLIDADO_WINDOW_DAYS` | Ventana de «próximos a vencer» | `7` |
| `SESSION_IDLE_MINUTES` | Cierre de sesión por inactividad | `60` |
| `OLLAMA_URL`, `OLLAMA_MODEL`, `EMBED_MODEL` | Asistente (fase 2) | `http://localhost:11434`, `llama3.2:3b`, `nomic-embed-text` |
| `ASSISTANT_MIN_SIMILARITY` | Similitud mínima (0 a 1) para dar por relevante una lección o procedimiento | `0.5` |

## Asistente de lecciones aprendidas y procedimientos (fase 2 y Sprint 2)

1. Al cerrar un entregable (`HECHO`), cada observación resuelta con solución genera una lección. Además, el gerente y el administrador mantienen el catálogo de procedimientos aprobados en `/procedimientos/`. `indexar_lecciones` (y la tarea programada) indexa tanto las lecciones como los procedimientos vigentes.
2. Con Ollama en el servidor local: `ollama pull llama3.2:3b` y `ollama pull nomic-embed-text`, luego `python manage.py indexar_lecciones`. Los embeddings se guardan en las tablas de lecciones y procedimientos, en la propia base de datos.
3. La consulta busca por significado en ambas fuentes, arma el prompt solo con esos procedimientos y casos y cita su origen (`[Procedimiento N]` y `[Caso N]`, con enlace al entregable solo si el usuario puede verlo). Si no hay fuentes relacionadas, lo indica sin inventar y orienta a escalar al senior del contrato.
4. Cada usuario puede valorar si la respuesta le fue útil («Sí / No») y consultar su historial propio en «Mis consultas anteriores».
5. Sin Ollama, o antes de indexar, busca por coincidencia de palabras y la pantalla lo avisa; el resto de la plataforma no se ve afectado.

**Decisión a confirmar:** el SDD menciona «ChromaDB (o pgvector)». Se implementó un índice propio en la base de datos (similitud coseno en Python) porque
ChromaDB arrastra unas 80 dependencias (telemetría, clientes de red) para un corpus de decenas de lecciones, lo contrario de RNF-01. La interfaz es pequeña
(`buscar_semantico` y `indexar_embeddings` en `apps/conocimiento/servicios.py`), así que cambiarlo después es acotado.

## Docker Compose

```powershell
copy .env.example .env      # cambiar POSTGRES_PASSWORD y DJANGO_SECRET_KEY
docker compose up --build
docker compose exec web python manage.py seed_demo
```

Servicios: `db` (PostgreSQL), `web`, `programador` y `ollama` (sin puertos publicados: solo la web lo alcanza). Volúmenes: base de datos, `media` y modelos de Ollama.
**Escrito pero sin probar** (no había Docker disponible al prepararlo). Desde el Sprint 3 (RF-51) el contenedor arranca con `python manage.py servir`
(waitress y WhiteNoise), no con el servidor de desarrollo. La instalación en un servidor propio está en [`docs/despliegue.md`](docs/despliegue.md).

## Demostración remota (temporal)

Para que el cliente use la aplicación desde internet durante una reunión, sin servidor ni abrir puertos del router:

```powershell
winget install --id Cloudflare.cloudflared      # una sola vez
powershell -ExecutionPolicy Bypass -File scripts\demo_remota.ps1            # -Reiniciar: datos desde cero · -Clave "...": clave fija
```

El script usa una base y adjuntos aparte (`demo_remota/`, sin tocar `db.sqlite3`), corre con `DJANGO_DEBUG=0`, reemplaza la clave pública
`demo1234` por una nueva en cada arranque y abre un túnel rápido de Cloudflare (HTTPS). Imprime la dirección `https://….trycloudflare.com`
y la clave; ambas dejan de servir al cerrar la ventana (Ctrl+C). El equipo debe seguir encendido y sin suspenderse durante la reunión.
Solo con datos simulados.

## Seguridad y privacidad

- Todo permiso se verifica en el servidor (vistas, filtros, calendario, buscador, indicadores, repositorio y descargas); la interfaz solo oculta lo no permitido. Lo que un usuario no puede ver responde 404; lo que ve pero no puede hacer, 403.
- Los archivos subidos se validan (extensión y tamaño), llevan el nombre saneado, se guardan fuera del código y **no tienen URL pública**: se descargan solo por una vista que comprueba el acceso al entregable, a la ficha o al documento del repositorio.
- CSRF activo, contraseñas con hash y validadores de Django, sesión que se cierra por inactividad y cookies seguras fuera de `DEBUG`.
- Las páginas de quien inició sesión no se guardan en la caché del navegador (`Cache-Control: no-store`), y las peticiones HTMX llevan el token CSRF.
- Sin llamadas a internet en ejecución: bibliotecas JavaScript copiadas en `static/js/`, sin fuentes ni analíticas externas (una prueba lo verifica).
- Los logs no incluyen contenido de documentos.
- **Copias de seguridad:** respaldar con frecuencia la base de datos **y** la carpeta de adjuntos (`media/` o el volumen `media`), por ejemplo `pg_dump` más una copia de esa carpeta. Fuera del alcance del prototipo, pero necesario antes de usar datos reales (hoy prohibido).

## Rutas principales

`/login/`, `/logout/` · `/` · `/tablero/` · `/entregables/` · `/entregables/nuevo/` · `/entregables/<id>/` · `/entregables/<id>/mover/` · `/entregables/<id>/observaciones/` ·
`/observaciones/` · `/observaciones/<id>/corregir/` · `/observaciones/<id>/revisar/` · `/observaciones/<id>/resolver/` ·
`/entregables/<id>/adjuntos/` · `/adjuntos/<id>/descargar/` · `/adjuntos/<id>/restaurar/` · `/adjuntos/<id>/eliminar/` ·
`/entregables/<id>/entregar/` · `/entregas/` · `/entregas/<id>/acta/` ·
`/entregables/<id>/responsables/` · `/entregables/<id>/tiempo/` · `/tiempos/` ·
`/fichas/` · `/fichas/nueva/` · `/fichas/<id>/` · `/fichas/<id>/archivo/` ·
`/calendario/` · `/api/calendario/eventos/` · `/notificaciones/` · `/notificaciones/<id>/leer/` ·
`/indicadores/` · `/repositorio/` · `/repositorio/cargar-plantilla/` · `/repositorio/publicar-anonimizado/` · `/repositorio/<id>/` · `/repositorio/version/<id>/descargar/` · `/repositorio/version/<id>/restaurar/` ·
`/buscar/` · `/asistente/` · `/asistente/valorar/<id>/` · `/procedimientos/` (gerente y admin) ·
`/incorporacion/` · `/incorporacion/planes/` (gerente y admin) ·
`/consolidado/` (gerente y admin) · `/gestion/` · `/clientes/` · `/contratos/` · `/plantillas/` · `/lineas-servicio/` · `/personal/` (gerente y admin) ·
`/admin/` (panel técnico, solo admin).

## Estructura

```
certitrack/         proyecto Django (settings, urls)
apps/cuentas/       usuarios, roles, permisos, ausencias, ingreso   apps/clientes/      clientes, contratos, plantillas, líneas
apps/entregables/   entregables, observaciones, entregas, apoyos, tiempos, historial, adjuntos, urgencia y filtros
apps/levantamiento/ fichas de levantamiento e ítems recurrentes     apps/indicadores/   panel de indicadores calculados
apps/repositorio/   plantillas, ejemplos anonimizados (NDA), accesos apps/busqueda/      buscador global transversal
apps/conocimiento/  lecciones, procedimientos y asistente            apps/equipo/        planes y seguimiento de incorporación
apps/calendario/    apps/alertas/ (notificaciones y programador)    apps/consolidado/   consolidado del gerente
apps/reportes/      solo placeholder (fase 3)
templates/ static/ docs/ (wireframes, hoja de ruta, trazabilidad)   media/ (adjuntos; no se versiona)
```

## Decisiones abiertas del SDD (§23) y el valor usado

SQLite en desarrollo y PostgreSQL con `DATABASE_URL` · umbrales 5, 2, 1 y 0 días (el de 1 día lo sumó el Sprint 2) · plantillas de ejemplo con 2 o 3 campos y adjuntos distintos ·
10 MB y los siete formatos del SDD · crean entregables el senior (solo sus contratos), el gerente y el admin · asistente como pantalla aparte ·
`llama3.2:3b` y `nomic-embed-text` · servidor de producción `manage.py servir` (waitress y WhiteNoise, Sprint 3) · sesión de 60 minutos.
Todo es configurable o fácil de cambiar.

## Dependencias

Django, Faker, APScheduler y `psycopg` (solo con PostgreSQL). HTMX, SortableJS y FullCalendar están en `static/js/`. Para pruebas se usa el ejecutor de Django.
Fase 3 (asignación automática y reportes): solo visión, ver [`docs/hoja-de-ruta.md`](docs/hoja-de-ruta.md).
