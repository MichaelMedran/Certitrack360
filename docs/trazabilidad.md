# Trazabilidad frente al SDD v1.0 y al SDD del Sprint 2

Estado de cada requisito, su hito y lo que lo prueba. Las pruebas se corren con `python manage.py test` (553 hoy: las 445 del
Sprint 1 y 108 del Sprint 2). El Sprint 2 (`docs/sdd-sprint-2.md`) está más abajo, en [Sprint 2](#sprint-2-docssdd-sprint-2md).

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
| RNF-06 Mantenibilidad | Hecho | Una app por módulo, migraciones versionadas, 553 pruebas (445 del Sprint 1) |
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

## Sprint 2 (`docs/sdd-sprint-2.md`)

Se construye hito por hito (SDD del Sprint 2, §12). Las pruebas nuevas viven en archivos propios; las del Sprint 1 solo
cambian donde lo autoriza la §11.3 (ver «Ajustes a pruebas del Sprint 1»).

### Requisitos

| Id | Hito | Estado | Dónde se prueba |
|---|---|---|---|
| RF-20 Código único `CT-AAAA-NNNNN`, ID-TDR, línea de servicio y fecha de recepción | S2-H1 | Hecho: el código se asigna al crear, en la misma transacción, por cualquier camino (formulario, panel técnico, `seed_demo` y, más adelante, la ficha), con prefijo `CODIGO_PREFIJO` y año local de Lima; los existentes se rellenan en la migración `entregables/0003` (con reversa). ID-TDR y fecha de recepción son obligatorios en «Nuevo entregable» (no futura, no posterior al plazo; el mensaje nombra cada dato) y la línea se toma del contrato, de solo lectura. Se ve en tarjeta, lista (columnas Código e ID-TDR), detalle, calendario y avisos | `apps/entregables/test_recepcion.py` (CodigoTests, NuevoEntregableConRecepcionTests, DetalleYListaConRecepcionTests, MigracionDeRellenoTests, SeedConRecepcionTests) |
| RF-21 Calendario con responsable y filtros por cliente, estado y responsable | S2-H1 | Hecho: cada evento dice estado, código, cliente, responsable (junior asignado), entregable y urgencia; panel «Filtros» que se aplica sin recargar y conserva el mes; los filtros parten de `entregables_visibles` y nunca amplían | `apps/calendario/test_filtros_y_responsable.py` |
| RF-22 Alertas a 48 y 24 h y aviso con código | S2-H1 / S2-H3 | Parcial: el umbral de 24 h funciona y sale una sola vez (restricción «una alerta por umbral»); «Crítico» = segundo umbral mayor (2 días con 5,2,1,0 y con 5,2,0); los avisos llevan el código. **El valor por defecto sigue en 5,2,0** (decisión pendiente, abajo). El estado «Con correcciones pendientes» es del S2-H3 | `apps/alertas/test_aviso_24h.py` |
| RF-23 Columnas del Kanban según HU-04 | S2-H1 | Hecho: Por hacer, En proceso, Revisión senior, Aprobado, Entregado; los códigos guardados no cambian | `apps/entregables/test_etiquetas.py` |
| RF-24 Catálogo de líneas de servicio | S2-H1 | Hecho: las cinco líneas se crean en la migración `clientes/0005` (con reversa); pestaña «Líneas de servicio» de Gestión (`/lineas-servicio/`, gerente y admin; junior y senior: 403) para crear, renombrar y activar o desactivar, sin borrado (baja lógica y `PROTECT`); obligatoria en el formulario de contrato; filtro por línea en tablero y lista | `apps/clientes/test_lineas.py` |
| RF-25 a RF-38 | S2-H2 a S2-H12 | Pendiente | — |

### Casos clave (§13)

| # | Caso | Prueba |
|---|---|---|
| 13 | Todo entregable nuevo tiene código único; el formulario rechaza la falta de ID-TDR o una recepción futura | `test_recepcion.py` (CodigoTests, NuevoEntregableConRecepcionTests) |
| 14 | El calendario filtra por cliente y estado sin ampliar la visibilidad y muestra al responsable | `test_filtros_y_responsable.py` (FiltrosDeEventosTests, EventoConResponsableTests, PaginaConFiltrosTests) |
| 15 | Con 5,2,1,0 el aviso de 24 h sale una sola vez y «Crítico» sigue empezando a 2 días | `test_aviso_24h.py` (AvisoDe24HorasTests, SegundoUmbralMayorTests) |
| 16 | Las columnas muestran las etiquetas de HU-04 y los códigos guardados no cambian | `test_etiquetas.py`, `test_recepcion.py` (MigracionDeRellenoTests) |
| 29 | Regresión: pasan las pruebas del Sprint 1 y `migrate` funciona sobre una base del Sprint 1 | Suite completa; `migrate` (y su reversa) probado sobre una copia de la base del `seed_demo` del Sprint 1 y sobre una base vacía |

### Hitos (§12)

| Hito | Estado |
|---|---|
| S2-H0 Wireframes y decisiones | Hecho: wireframes y decisiones aprobados el 2026-11-02 |
| S2-H1 Cierre del Sprint 1 | Hecho, con las decisiones de compatibilidad de abajo y una decisión pendiente (umbral por defecto) |
| S2-H2 a S2-H13 | Pendientes |

### Ajustes a pruebas del Sprint 1 (§11.3)

| Prueba | Fila de la §11.3 |
|---|---|
| `apps/calendario/tests.py` (test_el_estado_va_en_el_titulo), `apps/consolidado/tests.py` (test_los_contadores_por_estado_se_muestran_en_el_orden_del_tablero, test_resumenes_por_cliente_y_por_contrato), `apps/cuentas/test_interfaz.py` (test_las_cuatro_cifras_van_con_su_rotulo), `apps/entregables/test_adjuntos.py` (test_un_cambio_de_estado_sigue_mostrando_el_estado), `apps/entregables/test_interfaz.py` (test_pagina_completa_con_panel_de_filtros_columnas_y_tarjetas), `apps/entregables/test_reglas.py` (test_devolver_deja_el_motivo_en_el_historial, test_la_creacion_queda_en_el_historial_y_avisa_al_junior) | «Etiquetas de estados (RF-23)»: comparan contra `Entregable.Estado.X.label` |
| `apps/clientes/tests.py` (test_las_tres_pestanas_marcan_la_activa) | «Navegación nueva»: la lista esperada de pestañas de Gestión suma «Líneas de servicio» |

### Decisiones del S2-H1 (compatibilidad con el Sprint 1)

1. **Datos de recepción y línea del contrato en peticiones anteriores al Sprint 2.** Varias pruebas del Sprint 1 (que la §11.3 no
   permite cambiar) envían «Nuevo entregable» sin ID-TDR ni fecha de recepción, y el formulario de contrato sin línea de servicio. La
   pantalla siempre envía esos campos y en ella son obligatorios; una petición que **no los trae en absoluto** se acepta como antes:
   el entregable queda sin ID-TDR y con la fecha de creación como recepción (igual que los existentes), y el contrato conserva la línea
   que tenga. La base de datos los admite vacíos, como pide el SDD.
2. **«Crítico» con el segundo umbral mayor de los positivos.** Con un solo umbral positivo se usa ese (así lo fija una prueba del
   Sprint 1 con `10,0`); con dos o más, el segundo mayor, como pide el SDD.
3. **Textos «verificación» que se conservan.** «No se puede enviar a verificación: …» y «… antes de pasar a verificación» no son la
   etiqueta del estado y los comparan pruebas del Sprint 1 que la §11.3 no cubre; el resto de textos fijos ya usa las etiquetas nuevas.

### Decisión pendiente del equipo

- **Umbrales por defecto `5,2,1,0` (RF-22, §10.1).** Cambiar el valor por defecto hace fallar
  `apps/alertas/tests.py` · `test_una_notificacion_por_umbral_a_lo_largo_de_los_dias`, que espera `[0, 2, 5]` con los umbrales por
  defecto y no figura en la §11.3. Por la regla de no regresión se dejó `5,2,0` en `settings.py` y en `.env.example` (que lo explica).
  El aviso de 24 h ya funciona con `ALERT_THRESHOLDS_DAYS=5,2,1,0`. Para cerrarlo: autorizar que esa prueba espere `[0, 1, 2, 5]` y
  cambiar el valor por defecto en `certitrack/settings.py` y en `.env.example`.

## Pendiente para cerrar el SDD

1. **Probar Docker Compose** y el asistente contra un Ollama real (elegir modelos y ajustar `ASSISTANT_MIN_SIMILARITY`).
2. **Confirmar** gunicorn y WhiteNoise (decisión n.º 8) y el índice vectorial propio en lugar de ChromaDB.
3. **Prueba de uso con personas del equipo** y revisión con lector de pantalla (RNF-02 y RNF-03).
4. **Pruebas de navegador dentro del repositorio.** Hoy se hicieron con Playwright desde fuera; incorporarlas exigiría sumar una dependencia de desarrollo, que no está en la lista aprobada.
5. **Decisiones de interfaz con valor por defecto** (las siete preguntas de `docs/wireframes/index.html`): siguen vigentes porque el equipo no pidió cambios al aprobar; confirmarlas por escrito.
