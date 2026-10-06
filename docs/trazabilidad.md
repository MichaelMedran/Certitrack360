# Trazabilidad frente al SDD v1.0

Estado de cada requisito, su hito y lo que lo prueba. Las pruebas se corren con `python manage.py test` (445 hoy).

**Leyenda.** *Hecho*: implementado y probado. *Parcial*: lo esencial está hecho y se indica lo que falta. *Sin probar*: escrito, pero no se pudo ejecutar en este entorno.

**Cómo se verificó la interfaz.** Los wireframes se aprobaron el 2026-10-05 (`docs/wireframes/index.html`) y la interfaz se construyó sobre ellos. Además de las pruebas del
repositorio (que comprueban lo que responde el servidor, incluidos los fragmentos HTMX), se recorrió en Chrome real con un arnés de Playwright que **vive fuera del repositorio**
(no se agregó como dependencia): filtros sin recargar y con la dirección actualizada, «Atrás» y «Adelante», arrastrar tarjetas, diálogo de devolución, subida y versiones de adjuntos,
editor de plantillas, consolidado, notificaciones, calendario y que ninguna página se desborde a 820 y a 390 píxeles de ancho.

## Requisitos funcionales

| Id | Hito | Estado | Dónde se prueba |
|---|---|---|---|
| RF-01 Ingreso y cierre de sesión | H1 | Hecho | `apps/cuentas/tests.py` (SesionTests) |
| RF-02 Roles y visibilidad en el servidor | H1 | Hecho | `apps/entregables/tests.py` (PermisosTests), `test_filtros.py` (VisibilidadTests), `apps/cuentas/tests.py` (RutasProtegidasTests) |
| RF-03 Clientes: alta, edición y baja lógica | H2 | Hecho (pestaña «Clientes» de Gestión) | `apps/clientes/tests.py` (GestionTests), `test_reglas.py` (ContratosDadosDeBajaTests) |
| RF-04 Contratos con senior responsable, juniors y baja lógica | H2 | Hecho (pestaña «Contratos») | `apps/clientes/tests.py` (GestionTests), `test_reglas.py` (ContratosDadosDeBajaTests) |
| RF-05 Plantillas: campos (incl. opción), adjuntos requeridos y plazo | H2 | Hecho: editor por lista de campos con «Agregar», «Quitar» y reordenar; al renombrar un campo conserva su clave interna, así que los entregables ya creados no pierden datos | `apps/clientes/tests.py` (EditorDePlantillasTests), `test_adjuntos.py` (PlantillaConAdjuntosTests), `test_reglas.py` (CamposDeOpcionTests) |
| RF-06 Creación con Poka-Yoke | H3 | Hecho | `apps/entregables/tests.py` (PokaYokeTests), `test_interfaz.py` (NuevoEntregableTests) |
| RF-07 Asignar junior y senior revisor | H3 | Hecho: ambos se eligen al crear; el revisor, por omisión, es el responsable del contrato | `test_interfaz.py` (NuevoEntregableTests) |
| RF-08 Kanban con transiciones validadas en el servidor | H4 | Hecho: arrastrar y soltar (SortableJS) y respuesta parcial por HTMX; cada movimiento lo valida el servidor y, si se rechaza, la tarjeta vuelve a su columna con el motivo. El detalle ofrece el equivalente con botones | `test_interfaz.py` (MoverConHtmxTests, TableroTests), `apps/entregables/tests.py` (FlujoTests) |
| RF-09 Observaciones (tipo, descripción, solución, resolución) | H4 | Hecho | `test_reglas.py` (ObservacionesTests, HistorialTests) |
| RF-10 Historial de estados y acciones sobre adjuntos | H4 | Hecho (el detalle muestra ambos) | `test_adjuntos.py` (HistorialDeAdjuntosTests), `test_reglas.py` (HistorialTests), `test_interfaz.py` (DetalleTests) |
| RF-11 Adjuntos: versiones, tipos, descarga con permisos, requeridos por plantilla | H3b | Hecho: sección «Adjuntos» del detalle con requeridos, versiones anteriores, descarga y eliminación (solo gerente y admin, con confirmación) | `test_adjuntos.py` (todo el módulo), `test_interfaz.py` (DetalleTests) |
| RF-12 Calendario según el rol | H5 | Hecho: el estado y la urgencia van en el texto del evento; en pantallas angostas se parte de la vista de lista | `apps/calendario/tests.py` |
| RF-13 Alertas con umbrales configurables | H5 | Hecho (APScheduler: `manage.py programador`) | `apps/alertas/tests.py` |
| RF-14 Notificaciones y no leídas | H5 | Hecho: marcar de una en una y todas, avisos recientes en el inicio, aviso al senior cuando algo llega a verificación | `apps/alertas/tests.py`, `apps/cuentas/test_interfaz.py` (InicioTests, NotificacionesPantallaTests), `test_adjuntos.py` (AvisoDeVerificacionTests) |
| RF-15 Urgencia calculada y filtros/orden | H4 | Hecho: panel «Filtros» plegable en tablero y lista (por HTMX, con la dirección actualizada), chips para quitar cada filtro y urgencia siempre en texto | `test_filtros.py`, `test_interfaz.py` (TableroTests, ListaTests) |
| RF-16 Consolidado del gerente | H5b | Hecho: `/consolidado/`, solo lectura, solo gerente y admin | `apps/consolidado/tests.py` (AccesoTests, CifrasTests, FiltrosDelConsolidadoTests, PantallaTests) |
| RF-17 `seed_demo` | H6 | Hecho | `test_seed.py`, `test_demo_archivos.py` |
| RF-18 Panel técnico | H1 | Hecho (`/admin/`, solo rol admin) | `apps/cuentas/tests.py`, `apps/cuentas/test_admin.py` |
| RF-19 Asistente de lecciones aprendidas | H7 | Hecho; probado con un Ollama simulado, **no contra un Ollama real** | `apps/conocimiento/tests.py` |
| RF-F3-01 / RF-F3-02 | H8 | Solo visión (no se implementan) | `docs/hoja-de-ruta.md` |

## Requisitos no funcionales

| Id | Estado | Cómo se cumple / se prueba |
|---|---|---|
| RNF-01 Localidad y privacidad | Hecho | Sin CDNs ni fuentes externas; Ollama solo por `OLLAMA_URL` (`certitrack/tests.py`, `apps/conocimiento/tests.py`; `apps/cuentas/test_interfaz.py` revisa que ninguna página pida recursos externos) |
| RNF-02 Simplicidad de uso | Parcial | Wireframes aprobados e interfaz construida sobre ellos. Falta la prueba de uso con personas del equipo |
| RNF-03 Accesibilidad | Parcial | La urgencia va siempre en texto (tablero, lista, detalle y calendario; el consolidado separa «Vencidos» y «Próximos a vencer» con su propio título); etiquetas en todos los campos; foco visible; «Saltar al contenido»; la barra marca la página actual; los mensajes se anuncian con `role` según su gravedad; cada acción del tablero tiene su equivalente con botones en el detalle (se usa con teclado). Falta revisarlo con un lector de pantalla y recorrerlo entero solo con el teclado |
| RNF-04 Seguridad | Hecho | Permisos en el servidor, CSRF (también en las peticiones HTMX), hash PBKDF2, validadores, descarga solo por vista, archivos validados, y las páginas con sesión no se guardan en la caché del navegador (`Cache-Control: no-store`) (`apps/cuentas/tests.py`, `apps/cuentas/test_interfaz.py`, `test_adjuntos.py`) |
| RNF-05 Rendimiento | Hecho para el volumen del prototipo | Las tarjetas traen sus adjuntos y observaciones con dos consultas en total, no una por tarjeta |
| RNF-06 Mantenibilidad | Hecho | Una app por módulo, migraciones versionadas, 445 pruebas |
| RNF-07 Portabilidad | Sin probar | `Dockerfile` y `docker-compose.yml` escritos y validados como YAML; no había Docker disponible |
| RNF-08 Localización | Hecho | `es-pe`, `America/Lima`, fechas en formato local |
| RNF-09 Degradación controlada | Hecho | `apps/conocimiento/tests.py` (ConsultaTests) |
| RNF-10 Trazabilidad | Hecho | Historial de estados y de adjuntos con usuario y fecha |

## Casos clave (SDD §17.2)

| # | Caso | Prueba |
|---|---|---|
| 1 | Un junior no accede a gestión ni al consolidado | `apps/entregables/tests.py` (PermisosTests), `apps/consolidado/tests.py` (AccesoTests, PantallaTests), `apps/clientes/tests.py` (GestionTests) |
| 2 | Cada rol ve solo lo suyo (entregables y calendario) | PermisosTests, `test_interfaz.py` (TableroTests), `apps/calendario/tests.py` |
| 3 | No se crea con datos faltantes y el mensaje los nombra | PokaYokeTests, CamposDeOpcionTests, `test_interfaz.py` (NuevoEntregableTests) |
| 4 | Transición no permitida rechazada; las válidas, en el historial | FlujoTests, HistorialTests, `test_interfaz.py` (MoverConHtmxTests) |
| 5 | Devolver sin observación falla | FlujoTests, HistorialTests, MoverConHtmxTests |
| 6 | Sin adjuntos requeridos no pasa a verificación | `test_adjuntos.py` (AdjuntosRequeridosTests), `test_reglas.py` (DatosObligatoriosParaVerificarTests), MoverConHtmxTests |
| 7 | Nueva subida = nueva versión; extensión no permitida rechazada | VersionadoTests, ValidacionDeArchivosTests |
| 8 | Descarga de quien no tiene acceso denegada | DescargaTests |
| 9 | Una notificación por umbral | `apps/alertas/tests.py` (AlertasDeVencimientoTests) |
| 10 | Filtros sin ampliar la visibilidad; tipo de observación solo abiertas | `test_filtros.py` (VisibilidadTests, FiltrosTests), `test_interfaz.py` (TableroTests) |
| 11 | Contadores del consolidado coinciden | `apps/consolidado/tests.py` (CifrasTests, PantallaTests) |
| 12 | Asistente cita un caso ficticio; sin Ollama avisa | `apps/conocimiento/tests.py` (ConsultaTests), `test_seed.py` |

## Hitos (SDD §20)

| Hito | Estado |
|---|---|
| H0 Preparación | Hecho |
| H0.5 Wireframes | Hechos (12 pantallas) y **aprobados el 2026-10-05** |
| H1 Usuarios y roles | Hecho |
| H2 Clientes, contratos y plantillas | Hecho (con el editor de plantillas por lista de campos) |
| H3 Entregables y Poka-Yoke | Hecho |
| H3b Adjuntos | Hecho (incluida la sección del detalle) |
| H4 Kanban y filtros | Hecho (Kanban con HTMX, filtros plegables, urgencia en texto) |
| H5 Calendario y alertas | Hecho |
| H5b Consolidado | Hecho |
| H6 Datos simulados y pruebas | Hecho |
| H7 Asistente (fase 2) | Hecho (sin probar contra un Ollama real) |
| H8 Fase 3 (solo visión) | Hecho (`docs/hoja-de-ruta.md`) |

## Pendiente para cerrar el SDD

1. **Probar Docker Compose** y el asistente contra un Ollama real (elegir modelos y ajustar `ASSISTANT_MIN_SIMILARITY`).
2. **Confirmar** gunicorn y WhiteNoise (decisión n.º 8) y el índice vectorial propio en lugar de ChromaDB.
3. **Prueba de uso con personas del equipo** y revisión con lector de pantalla (RNF-02 y RNF-03).
4. **Pruebas de navegador dentro del repositorio.** Hoy se hicieron con Playwright desde fuera; incorporarlas exigiría sumar una dependencia de desarrollo, que no está en la lista aprobada.
5. **Decisiones de interfaz con valor por defecto** (las siete preguntas de `docs/wireframes/index.html`): siguen vigentes porque el equipo no pidió cambios al aprobar; confirmarlas por escrito.
