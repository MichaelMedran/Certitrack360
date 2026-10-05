# Trazabilidad frente al SDD v1.0

Estado de cada requisito, su hito y lo que lo prueba. Las pruebas se corren con `python manage.py test` (279 hoy).

**Leyenda.** *Hecho*: implementado y probado. *Lógica hecha*: la regla y sus endpoints están listos y probados, falta la pantalla, que espera la aprobación de los
wireframes (H0.5, `docs/wireframes/index.html`). *Sin probar*: escrito, pero no se pudo ejecutar en este entorno.

## Requisitos funcionales

| Id | Hito | Estado | Dónde se prueba |
|---|---|---|---|
| RF-01 Ingreso y cierre de sesión | H1 | Hecho | `apps/cuentas/tests.py` (SesionTests) |
| RF-02 Roles y visibilidad en el servidor | H1 | Hecho | `apps/entregables/tests.py` (PermisosTests), `test_filtros.py` (VisibilidadTests), `apps/cuentas/tests.py` (RutasProtegidasTests) |
| RF-03 Clientes: alta, edición y baja lógica | H2 | Hecho | `apps/entregables/tests.py` (PermisosTests), `test_reglas.py` (ContratosDadosDeBajaTests) |
| RF-04 Contratos con senior responsable, juniors y baja lógica | H2 | Hecho | `test_reglas.py` (ContratosDadosDeBajaTests) |
| RF-05 Plantillas: campos (incl. opción), adjuntos requeridos y plazo | H2 | Hecho (editor por cuadro de texto; el editor por lista de campos espera aprobación) | `test_adjuntos.py` (PlantillaConAdjuntosTests), `test_reglas.py` (CamposDeOpcionTests) |
| RF-06 Creación con Poka-Yoke | H3 | Hecho | `apps/entregables/tests.py` (PokaYokeTests) |
| RF-07 Asignar junior y senior revisor | H3 | Parcial: el junior se elige; el senior revisor se asigna solo (responsable del contrato). Elegirlo espera la pantalla | `apps/entregables/tests.py` |
| RF-08 Kanban con transiciones validadas en el servidor | H4 | Hecho (arrastrar y soltar con JavaScript propio; el SDD pide HTMX parcial, se cambia con la interfaz aprobada) | `apps/entregables/tests.py` (FlujoTests) |
| RF-09 Observaciones (tipo, descripción, solución, resolución) | H4 | Hecho | `test_reglas.py` (ObservacionesTests, HistorialTests) |
| RF-10 Historial de estados y acciones sobre adjuntos | H4 | Hecho (el detalle ya muestra ambos) | `test_adjuntos.py` (HistorialDeAdjuntosTests), `test_reglas.py` (HistorialTests) |
| RF-11 Adjuntos: versiones, tipos, descarga con permisos, requeridos por plantilla | H3b | Lógica hecha; falta la sección en el detalle | `test_adjuntos.py` (todo el módulo) |
| RF-12 Calendario según el rol | H5 | Hecho | `apps/calendario/tests.py` |
| RF-13 Alertas con umbrales configurables | H5 | Hecho (APScheduler: `manage.py programador`) | `apps/alertas/tests.py` |
| RF-14 Notificaciones y no leídas | H5 | Hecho; marcar de una en una tiene endpoint, falta el botón | `apps/alertas/tests.py`, `test_adjuntos.py` (AvisoDeVerificacionTests) |
| RF-15 Urgencia calculada y filtros/orden | H4 | Lógica hecha (los filtros ya funcionan por parámetros de la URL); faltan los controles y la etiqueta de urgencia en tablero y lista | `test_filtros.py` |
| RF-16 Consolidado del gerente | H5b | Datos y control de acceso hechos; falta la pantalla y su ruta `/consolidado/` | `apps/consolidado/tests.py` |
| RF-17 `seed_demo` | H6 | Hecho | `test_seed.py`, `test_demo_archivos.py` |
| RF-18 Panel técnico | H1 | Hecho (`/admin/`, solo rol admin) | `apps/cuentas/tests.py`, `apps/cuentas/test_admin.py` |
| RF-19 Asistente de lecciones aprendidas | H7 | Hecho; probado con un Ollama simulado, **no contra un Ollama real** | `apps/conocimiento/tests.py` |
| RF-F3-01 / RF-F3-02 | H8 | Solo visión (no se implementan) | `docs/hoja-de-ruta.md` |

## Requisitos no funcionales

| Id | Estado | Cómo se cumple / se prueba |
|---|---|---|
| RNF-01 Localidad y privacidad | Hecho | Sin CDNs ni fuentes externas; Ollama solo por `OLLAMA_URL` (`certitrack/tests.py`, `apps/conocimiento/tests.py`) |
| RNF-02 Simplicidad de uso | Pendiente de revisión | Depende de la aprobación de los wireframes |
| RNF-03 Accesibilidad | Parcial | La urgencia ya va en texto en el calendario; falta en tablero y lista. Cada acción del tablero tiene su equivalente con botones en el detalle (se usa con teclado) |
| RNF-04 Seguridad | Hecho | Permisos en el servidor, CSRF, hash PBKDF2, validadores, descarga solo por vista, archivos validados (`apps/cuentas/tests.py`, `test_adjuntos.py`) |
| RNF-05 Rendimiento | Hecho para el volumen del prototipo | — |
| RNF-06 Mantenibilidad | Hecho | Una app por módulo, migraciones versionadas, 279 pruebas |
| RNF-07 Portabilidad | Sin probar | `Dockerfile` y `docker-compose.yml` escritos y validados como YAML; no había Docker disponible |
| RNF-08 Localización | Hecho | `es-pe`, `America/Lima`, fechas en formato local |
| RNF-09 Degradación controlada | Hecho | `apps/conocimiento/tests.py` (ConsultaTests) |
| RNF-10 Trazabilidad | Hecho | Historial de estados y de adjuntos con usuario y fecha |

## Casos clave (SDD §17.2)

| # | Caso | Prueba |
|---|---|---|
| 1 | Un junior no accede a gestión ni al consolidado | `apps/entregables/tests.py` (PermisosTests); consolidado a nivel de servicio en `apps/consolidado/tests.py` (la prueba HTTP llega con la pantalla) |
| 2 | Cada rol ve solo lo suyo (entregables y calendario) | PermisosTests, `apps/calendario/tests.py` |
| 3 | No se crea con datos faltantes y el mensaje los nombra | PokaYokeTests, CamposDeOpcionTests |
| 4 | Transición no permitida rechazada; las válidas, en el historial | FlujoTests, HistorialTests |
| 5 | Devolver sin observación falla | FlujoTests, HistorialTests |
| 6 | Sin adjuntos requeridos no pasa a verificación | `test_adjuntos.py` (AdjuntosRequeridosTests), `test_reglas.py` (DatosObligatoriosParaVerificarTests) |
| 7 | Nueva subida = nueva versión; extensión no permitida rechazada | VersionadoTests, ValidacionDeArchivosTests |
| 8 | Descarga de quien no tiene acceso denegada | DescargaTests |
| 9 | Una notificación por umbral | `apps/alertas/tests.py` (AlertasDeVencimientoTests) |
| 10 | Filtros sin ampliar la visibilidad; tipo de observación solo abiertas | `test_filtros.py` (VisibilidadTests, FiltrosTests) |
| 11 | Contadores del consolidado coinciden | `apps/consolidado/tests.py` (CifrasTests) |
| 12 | Asistente cita un caso ficticio; sin Ollama avisa | `apps/conocimiento/tests.py` (ConsultaTests), `test_seed.py` |

## Hitos (SDD §20)

| Hito | Estado |
|---|---|
| H0 Preparación | Hecho |
| **H0.5 Wireframes** | Hechos (12 pantallas). **Falta la aprobación del equipo** |
| H1 Usuarios y roles | Hecho |
| H2 Clientes, contratos y plantillas | Hecho |
| H3 Entregables y Poka-Yoke | Hecho |
| H3b Adjuntos | Lógica y endpoints hechos; falta la sección en el detalle |
| H4 Kanban y filtros | Kanban hecho; filtros y urgencia con lógica hecha, falta su interfaz |
| H5 Calendario y alertas | Hecho |
| H5b Consolidado | Datos y acceso hechos; falta la pantalla |
| H6 Datos simulados y pruebas | Hecho |
| H7 Asistente (fase 2) | Hecho (sin probar contra un Ollama real) |
| H8 Fase 3 (solo visión) | Hecho (`docs/hoja-de-ruta.md`) |

## Pendiente para cerrar el SDD

1. **Aprobación de los wireframes** y, con ella, construir: sección de adjuntos en el detalle, filtros plegables con HTMX y etiqueta de urgencia en tablero y lista,
   pantalla de Consolidado, elegir el senior revisor al crear, notificaciones recientes en el inicio, marcar avisos de uno en uno, editor de plantillas por lista de campos,
   Kanban con HTMX y la navegación «Gestión» / «Administración».
2. **Probar en un navegador** el tablero (SortableJS) y el calendario (FullCalendar): su JavaScript solo se comprobó del lado del servidor.
3. **Probar Docker Compose** y el asistente contra un Ollama real (elegir modelos y ajustar `ASSISTANT_MIN_SIMILARITY`).
4. **Confirmar** gunicorn y WhiteNoise (decisión n.º 8) y el índice vectorial propio en lugar de ChromaDB.
