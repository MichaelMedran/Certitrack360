# CertiTrack 360 (prototipo MVP)

Plataforma web local para el seguimiento de los entregables documentales del área de Proyectos. Todo corre en el servidor
local: sin APIs externas, sin CDNs, sin telemetría. **Solo se usan datos simulados.**

- **Estado frente al SDD v1.0:** [`docs/trazabilidad.md`](docs/trazabilidad.md) (requisito por requisito, con sus pruebas).
- **Wireframes (H0.5):** [`docs/wireframes/index.html`](docs/wireframes/index.html), aprobados por el equipo el 2026-10-05. La interfaz se construyó sobre ellos:
  adjuntos en el detalle, filtros y urgencia en tablero y lista, Kanban con HTMX, Consolidado, editor de plantillas y notificaciones.

## Puesta en marcha (desarrollo)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env                                  # opcional: los valores por defecto sirven para desarrollo
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo --reset      # datos simulados
.\.venv\Scripts\python manage.py runserver
```

Abrir http://127.0.0.1:8000/. Pruebas: `.\.venv\Scripts\python manage.py test` (menos de un minuto).

Si ya tenía datos de una versión anterior, `migrate` los conserva; `seed_demo --reset` los reemplaza por los de demostración
(**borra todos los clientes, contratos, plantillas, entregables, adjuntos y lecciones**, más los usuarios de demostración).

### Tareas programadas

`python manage.py programador` deja corriendo (en otra terminal) las alertas de vencimiento, cada hora, y la indexación de lecciones del
asistente, a diario a las 02:00 (hora de Lima). Se pueden lanzar a mano: `generar_alertas` e `indexar_lecciones`. En Docker es el servicio `programador`.

## Usuarios de prueba (contraseña `demo1234`, solo para este prototipo)

| Usuario | Rol | Ve |
|---|---|---|
| `admin_demo` | Administrador | Todo, más el panel técnico en `/admin/` |
| `gerente_demo` | Gerente de Proyectos | Todos los proyectos; gestiona clientes, contratos y plantillas |
| `senior1`, `senior2` | Senior | Los contratos a su cargo |
| `junior1`, `junior2`, `junior3` | Junior | Solo lo que tienen asignado |

## Guion de demostración

Recorre el flujo con el seed. Cada paso dice con qué usuario hacerlo.

1. **Ingreso y roles.** Entrar como `junior1`: el inicio muestra solo sus cifras, sus próximos plazos y sus notificaciones recientes, y la barra no tiene «Consolidado», «Gestión» ni «Administración». Cerrar sesión y entrar como `gerente_demo`: aparecen «Consolidado» y «Gestión» y ve todos los proyectos. `admin_demo` ve además «Administración» (el panel técnico).
2. **Poka-Yoke al crear.** Como `senior1`: *Entregables → Nuevo entregable*. Elegir «Matriz de riesgos» (el panel informa que esa plantilla no exige adjuntos; la de «Informe técnico mensual» exige «Borrador»). Dejar vacío «Nivel de riesgo», elegir una fecha pasada y probar sin elegir «Impacto» (campo de opción): los mensajes dicen exactamente qué falta y el formulario conserva lo escrito. Elegir el *senior revisor* (por omisión, el responsable del contrato). Completar y crear: el junior elegido recibe un aviso de asignación.
3. **Kanban.** Entrar como ese junior (o cualquiera con tarjetas en «A realizar»): *Tablero*. Cada tarjeta lleva su urgencia en texto («Vencido», «Crítico», «Próximo», «Normal»), los adjuntos y las observaciones abiertas. Arrastrar una tarjeta de «A realizar» a «En proceso». Intentar saltar a «Hecho»: el servidor lo rechaza y la tarjeta vuelve a su columna con el motivo. Sin ratón, se abre la tarjeta y se usa «Mover entregable».
4. **Adjuntos requeridos.** El comando `seed_demo` imprime al terminar qué dos tarjetas «En proceso» quedaron sin sus adjuntos y a qué junior pertenecen. Entrar como ese junior y arrastrar una a «Verificación senior»: aparece un único mensaje con los adjuntos que faltan. Abrir la tarjeta: en «Adjuntos» se ve qué falta («Borrador — falta»). Subir un archivo (pdf, docx, xlsx, pptx, png, jpg o txt; máximo 10 MB); una segunda subida del mismo tipo crea la versión 2 y deja la anterior en «Ver versiones anteriores». Con el adjunto subido, la tarjeta ya pasa a verificación. Solo el gerente y el admin pueden eliminar un adjunto, y se les pide confirmación.
5. **Verificación y devolución.** Como un senior con tarjetas en «Verificación senior»: arrastrar una a «En proceso» abre el diálogo «Devolver al junior», que pide el tipo de error y la descripción. Aprobar otra a «Listo para entrega» y luego a «Hecho» (al cerrarla, sus observaciones resueltas pasan a ser lecciones aprendidas).
6. **Notificaciones.** Como ese senior, *Avisos*: hay avisos de entregables en verificación. Como un junior: asignaciones, observaciones y vencimientos. Cada aviso se marca como leído con su propio botón (o todos a la vez), y el indicador de la barra baja. Cada persona ve solo los suyos.
7. **Calendario.** Cada evento dice su estado y su urgencia en texto («— Crítico», «— Vencido»); un junior ve solo sus plazos. En pantallas angostas se muestra como lista.
8. **Filtros y urgencia.** En *Tablero* y *Entregables*, abrir «Filtros»: cliente, contrato, responsable, urgencia, tipo de observación abierta (solo cuenta las no resueltas), estado y orden. Se aplican al cambiar cada control, sin recargar la página; los chips «Activos» permiten quitar uno a uno y «Limpiar» los quita todos. La dirección queda con los filtros (se puede copiar o volver con «Atrás»). Un filtro nunca muestra más de lo que el rol puede ver.
9. **Asistente (fase 2).** Preguntar «falta el periodo reportado en el informe»: devuelve el caso de origen citado (cliente, contrato, entregable). Sin Ollama lo avisa y busca por palabras.
10. **Consolidado.** Como `gerente_demo`: *Consolidado* (o «Ver consolidado» en el inicio). Cifras por estado, vencidos, próximos a vencer, resumen por cliente y por contrato, y carga por persona; se puede filtrar por cliente, contrato, estado y rango de plazo. Un junior o un senior reciben «sin permiso». Es de solo lectura.
11. **Gestión.** Como `gerente_demo`: *Gestión* con las pestañas Clientes, Contratos y Plantillas. En *Plantillas*, crear una con el editor de campos: «Agregar campo», subir o bajar, tipo «Opción» con sus opciones separadas por comas, y los adjuntos obligatorios. Renombrar un campo de una plantilla existente no hace perder los datos de los entregables ya creados. Un cliente o contrato no se borra: se desmarca «Activo».
12. **«Atrás» del navegador.** Las páginas con sesión no se guardan en la caché del navegador: al volver con «Atrás» se ve el estado real del tablero, no una copia vieja.

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
| `ALERT_THRESHOLDS_DAYS` | Alertas y urgencia: menor umbral positivo = «crítico», mayor = «próximo» | `5,2,0` |
| `CONSOLIDADO_WINDOW_DAYS` | Ventana de «próximos a vencer» | `7` |
| `SESSION_IDLE_MINUTES` | Cierre de sesión por inactividad | `60` |
| `OLLAMA_URL`, `OLLAMA_MODEL`, `EMBED_MODEL` | Asistente (fase 2) | `http://localhost:11434`, `llama3.2:3b`, `nomic-embed-text` |
| `ASSISTANT_MIN_SIMILARITY` | Similitud mínima (0 a 1) para dar por relevante una lección | `0.5` |

## Asistente de lecciones aprendidas (fase 2)

1. Al cerrar un entregable (`HECHO`), cada observación resuelta con solución genera una lección. `indexar_lecciones` (y la tarea programada) recoge además las que se resuelvan después.
2. Con Ollama en el servidor local: `ollama pull llama3.2:3b` y `ollama pull nomic-embed-text`, luego `python manage.py indexar_lecciones`. Los embeddings se guardan en la tabla de lecciones, en la propia base de datos.
3. La consulta busca por significado, arma el prompt solo con esos casos y cita su origen (con enlace solo si el usuario puede ver ese entregable). Si ninguna lección se parece, lo dice sin inventar.
4. Sin Ollama, o antes de indexar, busca por coincidencia de palabras y la pantalla lo avisa; el resto de la plataforma no se ve afectado.

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
**Escrito pero sin probar** (no había Docker disponible al prepararlo). El contenedor usa el servidor de desarrollo de Django, adecuado para una demostración en red local;
servir en producción con gunicorn y WhiteNoise es la decisión abierta n.º 8 del SDD y está pendiente de confirmar.

## Seguridad y privacidad

- Todo permiso se verifica en el servidor (vistas, filtros, calendario y descargas); la interfaz solo oculta lo no permitido. Lo que un usuario no puede ver responde 404; lo que ve pero no puede hacer, 403.
- Los archivos subidos se validan (extensión y tamaño), llevan el nombre saneado, se guardan fuera del código y **no tienen URL pública**: se descargan solo por una vista que comprueba el acceso al entregable.
- CSRF activo, contraseñas con hash y validadores de Django, sesión que se cierra por inactividad y cookies seguras fuera de `DEBUG`.
- Las páginas de quien inició sesión no se guardan en la caché del navegador (`Cache-Control: no-store`), y las peticiones HTMX llevan el token CSRF.
- Sin llamadas a internet en ejecución: bibliotecas JavaScript copiadas en `static/js/`, sin fuentes ni analíticas externas (una prueba lo verifica).
- Los logs no incluyen contenido de documentos.
- **Copias de seguridad:** respaldar con frecuencia la base de datos **y** la carpeta de adjuntos (`media/` o el volumen `media`), por ejemplo `pg_dump` más una copia de esa carpeta. Fuera del alcance del prototipo, pero necesario antes de usar datos reales (hoy prohibido).

## Rutas principales

`/login/`, `/logout/` · `/` · `/tablero/` · `/entregables/` · `/entregables/nuevo/` · `/entregables/<id>/` · `/entregables/<id>/mover/` · `/entregables/<id>/observaciones/` ·
`/observaciones/<id>/resolver/` · `/entregables/<id>/adjuntos/` · `/adjuntos/<id>/descargar/` · `/adjuntos/<id>/eliminar/` · `/calendario/` · `/api/calendario/eventos/` ·
`/notificaciones/` · `/notificaciones/<id>/leer/` · `/consolidado/` (gerente y admin) · `/gestion/` · `/clientes/` · `/contratos/` · `/plantillas/` · `/asistente/` · `/admin/` (panel técnico, solo admin).

## Estructura

```
certitrack/      proyecto Django (settings, urls)
apps/cuentas/    usuarios, roles, permisos, ingreso        apps/clientes/     clientes, contratos, plantillas
apps/entregables/ entregables, observaciones, historial, adjuntos, urgencia y filtros
apps/calendario/ apps/alertas/ (notificaciones y tareas programadas)  apps/consolidado/ (consolidado del gerente)
apps/conocimiento/ lecciones y asistente (fase 2)           apps/reportes/    solo placeholder (fase 3)
templates/ static/ docs/ (wireframes, hoja de ruta, trazabilidad)  media/ (adjuntos; no se versiona)
```

## Decisiones abiertas del SDD (§23) y el valor usado

SQLite en desarrollo y PostgreSQL con `DATABASE_URL` · umbrales 5, 2 y 0 días · plantillas de ejemplo con 2 o 3 campos y adjuntos distintos ·
10 MB y los siete formatos del SDD · crean entregables el senior (solo sus contratos), el gerente y el admin · asistente como pantalla aparte ·
`llama3.2:3b` y `nomic-embed-text` · servidor de desarrollo en Docker hasta confirmar gunicorn y WhiteNoise · sesión de 60 minutos.
Todo es configurable o fácil de cambiar.

## Dependencias

Django, Faker, APScheduler y `psycopg` (solo con PostgreSQL). HTMX, SortableJS y FullCalendar están en `static/js/`. Para pruebas se usa el ejecutor de Django.
Fase 3 (asignación automática y reportes): solo visión, ver [`docs/hoja-de-ruta.md`](docs/hoja-de-ruta.md).
