# CertiTrack 360 (prototipo MVP)

Plataforma web local para el seguimiento de entregables del área de Proyectos de CERTICOM. Todo corre en el servidor
local: sin APIs externas, sin CDNs, sin telemetría. **Solo usar datos simulados.**

## Puesta en marcha (desarrollo)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo --reset
.\.venv\Scripts\python manage.py runserver
```

Abrir http://127.0.0.1:8000/. Pruebas: `python manage.py test`.

## Usuarios de prueba (contraseña `demo1234`, solo para este prototipo)

| Usuario | Rol |
|---|---|
| `admin_demo` | Administrador |
| `gerente_demo` | Gerente de Proyectos (consolidado general) |
| `senior1`, `senior2` | Senior (contratos a su cargo) |
| `junior1`, `junior2`, `junior3` | Junior (solo lo asignado) |

## Guía de la demostración

1. **junior1**: Inicio → Tablero. Arrastrar una tarjeta de «A realizar» a «En proceso». Intentar saltar a «Hecho»: el servidor lo rechaza. Ver Calendario (solo sus tareas) y Avisos.
2. **senior1**: Entregables → *Nuevo entregable*. Elegir plantilla y dejar un campo vacío: el mensaje dice exactamente cuál falta. Completar y crear (el junior recibe un aviso).
3. **senior1**: en el Tablero, arrastrar una tarjeta de «Verificación senior» a «En proceso»: pide una observación obligatoria. Aprobarla a «Listo para entrega» y luego a «Hecho».
4. **gerente_demo**: ve todos los proyectos; en Administración gestiona clientes, contratos y plantillas.
5. **Asistente** (cualquier usuario): preguntar «falta el periodo reportado en el informe» y ver los casos citados.

## Alertas

`python manage.py generar_alertas` crea las notificaciones de vencimiento (umbrales en `UMBRALES_ALERTA`, por defecto 5, 2 y 0 días), una por entregable/destinatario/umbral. En Docker corre cada hora (servicio `alertas`); en Windows se puede programar con el Programador de tareas.

## Asistente (fase 2)

Los casos salen de `LeccionAprendida` (se generan de observaciones resueltas de entregables cerrados con `python manage.py indexar_lecciones`; `seed_demo` carga 16 ficticias). Si Ollama está disponible en `OLLAMA_URL`, redacta una respuesta citando los casos; si no, la pantalla avisa y muestra igualmente los casos.

## Despliegue

`docker-compose up --build` (servicios `web`, `db`, `alertas`, `ollama`). Copiar `.env.example` a `.env` y cambiar las claves. Con Ollama: `docker compose exec ollama ollama pull llama3.2:3b`.

## Decisiones y notas

- Dependencias: solo Django, Faker y (producción) psycopg. HTMX, SortableJS y FullCalendar están en `static/js/`.
- **Alertas** con comando de gestión + bucle en Docker en lugar de django-q2 (evita una dependencia más).
- **Búsqueda del asistente** léxica local (TF-IDF) en lugar de ChromaDB, que no está aprobado aún; el cambio se limita a `apps/conocimiento/servicios.buscar`.
- SQLite por defecto; PostgreSQL con `DB_ENGINE=postgres`.
- Fase 3: ver `docs/hoja-de-ruta.md`.
