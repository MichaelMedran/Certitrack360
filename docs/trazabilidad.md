# Trazabilidad frente al SDD v1.0 y al SDD del Sprint 2

Estado de cada requisito, su hito y lo que lo prueba. Las pruebas se corren con `python manage.py test` (805 hoy: las 445 del
Sprint 1 y 360 del Sprint 2). El Sprint 2 (`docs/sdd-sprint-2.md`) está más abajo, en [Sprint 2](#sprint-2-docssdd-sprint-2md).

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
| RNF-06 Mantenibilidad | Hecho | Una app por módulo, migraciones versionadas, 805 pruebas (445 del Sprint 1) |
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
| RF-20 Código único `CT-AAAA-NNNNN`, ID-TDR, línea de servicio y fecha de recepción | S2-H1 | Hecho: el código se asigna al crear, en la misma transacción, por cualquier camino (formulario, panel técnico, `seed_demo` y, más adelante, la ficha), con prefijo `CODIGO_PREFIJO` y año local de Lima; los existentes se rellenan en la migración `entregables/0003` (con reversa). ID-TDR y fecha de recepción son obligatorios siempre en «Nuevo entregable», también si la petición no trae las claves (no futura, no posterior al plazo; el mensaje nombra cada dato; la base de datos los sigue admitiendo vacíos para los anteriores) y la línea se toma del contrato, de solo lectura. Se ve en tarjeta, lista (columnas Código e ID-TDR), detalle, calendario y avisos | `apps/entregables/test_recepcion.py` (CodigoTests, NuevoEntregableConRecepcionTests, DetalleYListaConRecepcionTests, MigracionDeRellenoTests, SeedConRecepcionTests) |
| RF-21 Calendario con responsable y filtros por cliente, estado y responsable | S2-H1 | Hecho: cada evento dice estado, código, cliente, responsable (junior asignado), entregable y urgencia; panel «Filtros» que se aplica sin recargar y conserva el mes; los filtros parten de `entregables_visibles` y nunca amplían; ids fuera de rango y fechas del rango mal escritas se ignoran (sin error 500); sin consultas por evento | `apps/calendario/test_filtros_y_responsable.py` (incluye DatosLimiteTests) |
| RF-22 Alertas a 48 y 24 h y aviso con código | S2-H1 / S2-H3 | Hecho. S2-H1: valor por defecto `5,2,1,0` (`settings.py` y `.env.example`); el aviso de 24 h sale una sola vez (restricción «una alerta por umbral»); «Crítico» = segundo umbral mayor (sigue en 2 días); los avisos llevan el código. S2-H3: aviso inmediato al junior asignado (tipo Observación, con el código y enlace a la sección Observaciones) al registrar observaciones, en la misma transacción; si el entregable estaba en revisión, el aviso es el de la devolución | `apps/alertas/test_aviso_24h.py` (AvisoDe24HorasTests, SegundoUmbralMayorTests, ConfiguracionDeUmbralesTests, ValorPorDefectoTests); `apps/entregables/test_observaciones.py` (RegistrarTests, CondicionesDeMoverTests) |
| RF-23 Columnas del Kanban según HU-04 | S2-H1 | Hecho: Por hacer, En proceso, Revisión senior, Aprobado, Entregado; los códigos guardados no cambian | `apps/entregables/test_etiquetas.py` |
| RF-24 Catálogo de líneas de servicio | S2-H1 | Hecho: las cinco líneas se crean en la migración `clientes/0005` (con reversa); pestaña «Líneas de servicio» de Gestión (`/lineas-servicio/`, gerente y admin; junior y senior: 403) para crear, renombrar y activar o desactivar, sin borrado (baja lógica y `PROTECT`); un id de edición mal escrito o inexistente es 404; obligatoria siempre en el formulario de contrato (también si la petición no trae el campo; la base de datos la admite vacía); filtro por línea en tablero y lista | `apps/clientes/test_lineas.py` |
| RF-25 Observaciones con estados, responsable, acción correctiva, fecha de atención y evidencia | S2-H3 | Hecho: `Observacion` suma `estado` (Pendiente, En corrección, Resuelta), `responsable` (por defecto el junior asignado), `corregida_por`/`corregida_en` (fecha de atención), `revisada_por`/`resuelta_en` y `evidencia` (versión de un adjunto del mismo entregable); la acción correctiva es el campo `solucion` existente (propiedad `accion_correctiva`, sin columna duplicada). `resuelta` se conserva y se sincroniza en `save()` (Resuelta ⇔ `resuelta=True`), así lecciones, filtros y consolidado no cambian. Máquina de estados en `apps/entregables/observaciones.py`: corregir (responsable o senior del entregable; exige texto; avisa al senior revisor, tipo Corrección), confirmar o rechazar (senior del entregable, gerente o admin; el rechazo vuelve a Pendiente y avisa al responsable) y resolver directo del Sprint 1 (`/observaciones/<id>/resolver/`, ahora también registra quién y cuándo). Resuelta exige acción correctiva. Cada paso queda en el historial. Migración `entregables/0004` aditiva, con relleno y reversa. Rutas POST `/observaciones/<id>/corregir/` y `/observaciones/<id>/revisar/`, con CSRF (también desde HTMX, que recibe `HX-Redirect`) | `apps/entregables/test_observaciones.py` (ModeloTests, MigracionTests, CorregirTests, RevisarTests, HtmxYCsrfTests, DetalleTests) |
| RF-26 Sección «Observaciones»: varias a la vez, devolución y subestado «Con correcciones pendientes» | S2-H3 | Hecho: el formulario del detalle registra varias observaciones en un envío (botón «+ Otra observación»; senior del entregable, gerente o admin), cada una con su responsable. En Revisión senior las devuelve a En proceso en la misma transacción con `servicios.mover`, que crea las observaciones una sola vez (la devolución del Sprint 1 por el tablero y el detalle sigue igual). Condiciones nuevas dentro de `mover`: a Revisión senior no se pasa con observaciones Pendiente (las En corrección sí) y a Aprobado no se pasa con observaciones abiertas; el mensaje dice cuántas y de qué tipo, y el detalle lo avisa antes de intentarlo. Subestado calculado (EN_PROCESO con observaciones abiertas, `apps/entregables/subestado.py`, con EXISTS y sin una consulta por fila) como texto en tarjeta, lista, detalle y calendario, y como opción del filtro de estado (tablero, lista, calendario) que no amplía la visibilidad | `test_observaciones.py` (RegistrarTests, CondicionesDeMoverTests, SubestadoTests, DetalleTests) |
| RF-27 Historial de observaciones filtrable | S2-H3 | Hecho: `/observaciones/`, pestaña «Observaciones» de Entregables; parte de las observaciones de `entregables_visibles` y filtra por cliente, contrato, entregable (código o título), responsable, estado y tipo de error, con chips, HTMX y páginas de 50; las opciones solo muestran lo visible y los valores no válidos se ignoran (sin error 500); cada fila lleva a la sección Observaciones del detalle | `test_observaciones.py` (HistorialDeObservacionesTests) |
| RF-28 Versiones: vigente visible, comentario obligatorio, restaurar y versión enviada bloqueada | S2-H4 | Hecho. Vigente = la de número más alto no eliminada (`adjuntos.vigente`): el detalle la marca «Vigente · vN» en la tabla «Adjuntos y versiones» y agrupa el resto en «Ver versiones anteriores de …». El **comentario del cambio es obligatorio en el formulario** (mensaje del servidor «Escriba el comentario del cambio…»); `adjuntos.subir()` lo sigue aceptando vacío (seed y pruebas). **Restaurar** (`POST /adjuntos/<id>/restaurar/`, con CSRF; senior del entregable, gerente o admin; el junior 403, ajenos 404) crea una versión NUEVA que copia el archivo, con `restaurado_desde` y el comentario «Restaurada desde la vN»; nunca reescribe ninguna versión; solo tipos versionables y solo una que ya no es la vigente; queda en el historial («Restauró … como vigente (nueva vN …)»). `Adjunto.bloqueado`: la versión enviada, el cargo y el acta quedan bloqueados; la vista de eliminación responde **403 con el motivo** incluso al gerente y al admin (la página 403 muestra el mensaje), el servicio también, y el panel técnico tampoco permite eliminarlas (además la base las protege con `PROTECT`). Los tipos `CARGO_RECEPCION` y `ACTA_CONFORMIDAD` no se ofrecen en el formulario de subida ni como adjuntos requeridos de la plantilla (`tipos.TIPOS_DE_SUBIDA`) y no alteran `faltantes_requeridos` ni la numeración de las versiones. Migración `entregables/0005` aditiva (campo `tipo` pasa a 20 caracteres), con reversa | `apps/entregables/test_entregas.py` (VersionVigenteTests, TiposNuevosNoSonRequeridosTests, RestaurarTests, VersionBloqueadaTests) |
| RF-29 Entregas: cargo obligatorio, acta, alerta de acta, historial filtrable y reentregas | S2-H4 | Hecho. Modelo `Entrega` (§6.2; más `cierre` y `alerta_acta_en`, ver decisiones). `servicios.mover` exige, para pasar a Entregado, una entrega del ciclo actual (con su cargo, fecha y medio) y la consume (`cierre`), bloqueando la versión enviada: no hay otro camino. El servicio `entregas.registrar` (una transacción) valida la fecha (no futura) y el medio, crea el cargo con `validar_archivo`, la entrega (número siguiente, acta Pendiente), y llama a `mover`; todo o nada, sin archivos huérfanos. Formulario `/entregables/<id>/entregar/` («Marcar como entregado»; senior del entregable, gerente y admin: junior 403, ajenos 404). **Tablero:** soltar una tarjeta de Aprobado en Entregado no la mueve (`tablero.js` la devuelve a su columna y la vista responde con `HX-Redirect` al formulario; quien no puede entregar recibe el 403 en el tablero); el botón «Marcar como entregado» del detalle lo abre. **Acta:** `POST /entregas/<id>/acta/`, Recibida u Observada con archivo obligatorio (`validar_archivo`), cada archivo es una versión nueva bloqueada, aviso tipo Acta al junior y al senior revisor (salvo a quien la registra). **Reapertura** `HECHO → EN_PROCESO` en `TRANSICIONES`: solo senior del entregable, gerente o admin, solo si la última entrega tiene el acta Observada, exigiendo observación como una devolución (se crea dentro de `mover`; aviso al junior con el código); las versiones bloqueadas siguen bloqueadas y la siguiente entrega es la n.º 2. **Alerta de acta:** `alertas.generar_alertas_acta`, dentro de la tarea programada existente (`tarea_alertas`) y del comando `generar_alertas`: acta Pendiente más de `ACTA_DIAS_PENDIENTE` (5) días → aviso al junior y al senior revisor UNA sola vez por entrega (marca `alerta_acta_en` con UPDATE condicional). **Historial** `/entregas/` (pestaña «Entregas» de Entregables): filtros por cliente, contrato, periodo (fecha de entrega) y estado del acta sobre `entregables_visibles`; el cargo y el acta se descargan solo por `adjunto_descargar` | `test_entregas.py` (ServicioDeEntregaTests, EntregaDelCicloActualTests, FormularioDeEntregaTests, SoltarEnEntregadoTests, ActaTests, ReaperturaTests, AlertaDeActaTests, HistorialDeEntregasTests, DetalleDeEntregasTests); `test_seed.py` |
| RF-30 Ficha de levantamiento del contrato: datos del TDR, estado documental inicial congelado y generación revisable de entregables recurrentes | S2-H5 | Hecho. Nueva app `apps/levantamiento` con `FichaLevantamiento` e `ItemFicha` (§6.2). Validación Poka-Yoke de obligatorios de la ficha (contrato vigente, ID-TDR, archivo del TDR con `validar_archivo`, requerimientos, responsable, al menos un ítem) y de cada ítem (nombre, plantilla, frecuencia, primera fecha, hasta ≥ primera fecha, junior asignado al contrato, senior y todos los `campos_requeridos` de la plantilla, nombrando el ítem y el campo que falta). Cronograma para frecuencias Única, Semanal, Quincenal, Mensual (ajustada al fin de mes) y Trimestral; descarta plazos pasados con aviso y permite quitar entregas en la vista previa antes de confirmar. El junior asignado redacta y pide confirmación (notificación tipo Ficha sin entregable, con enlace a la ficha, para el senior del contrato); solo el senior responsable del contrato, el gerente y el admin confirman (el junior recibe 403). `confirmar` corre en una transacción, respeta `FICHA_MAX_ENTREGABLES` (60 por defecto, en `settings.py` y `.env.example`), crea cada entregable con `EntregableForm` y `registrar_creacion` (código único, ID-TDR heredado, historial y aviso al junior) y congela `estado_inicial`, que no se sobrescribe jamás al actualizar el estado documental actual (HU-06, protegido también en `save()`). Listado `/fichas/` con filtros por cliente, contrato y estado, y descarga controlada `/fichas/<id>/archivo/` | `apps/levantamiento/tests.py` (ConfiguracionFichaTests, Caso21GeneracionDeEntregablesTests, Caso21ValidacionPokaYokeTests, Caso21EstadoInicialCongeladoTests, PermisosYVisibilidadTests) |
| RF-31 Gestión de personal, responsables de apoyo, reasignación con historial y aviso de conflictos | S2-H6 | Hecho. `Usuario.puesto` y `Ausencia` (`cuentas/0003`) y `ResponsableApoyo` con restricción de unicidad activa por entregable, usuario y función (`entregables/0006`). `entregables_visibles` suma los apoyos activos; un apoyo activo sube adjuntos y envía a revisión, pero no aprueba ni devuelve un entregable salvo que sea su senior (`servicios.mover`). Servicio `apps/entregables/personal.py`: `detectar_conflictos` (sobrecarga sobre `CARGA_MAXIMA_ACTIVOS=8`, plazo cercano ±2 días y ausencia registrada), `reasignar_principal`, `sumar_apoyo` y `quitar_apoyo` (baja lógica `activo=False`), dejando constancia en `HistorialEstado` («Reasignado de X a Y») y enviando `Notificacion` de tipo `REASIGNACION` a quien entra y a quien sale. Pantalla `/personal/` (pestaña «Personal» de Gestión, `@solo_gestion`) y sección «Responsables» en el detalle (`POST /entregables/<id>/responsables/`) con aviso de conflictos y confirmación explícita | `apps/entregables/test_personal.py` (ConfiguracionCargaMaximaTests, ModelosPersonalTests, Caso22ApoyoYReasignacionTests, ConflictosAsignacionTests, VistasPersonalYResponsablesTests) |
| RF-32 a RF-38 | S2-H7 a S2-H12 | Pendiente | — |

### Base común (S2-H2)

No agrega requisitos funcionales: prepara los hitos S2-H3 a S2-H12 (SDD del Sprint 2, §5, §6.1 y §11.3). Criterio del hito:
las notificaciones sin entregable se muestran y enlazan bien, y ninguna prueba del Sprint 1 cambia.

| Elemento | Estado | Dónde se prueba |
|---|---|---|
| Avisos sin entregable (§6.1) | Hecho: `Notificacion.entregable` es opcional y se agrega `enlace`, una ruta interna. «Ver» lleva al enlace, si lo tiene; si no, al detalle del entregable (los avisos del Sprint 1 siguen igual); si no tiene ninguno, el aviso se muestra sin «Ver». La lista de avisos, los avisos recientes del inicio, la insignia de no leídos y el marcado (de uno y de todos) funcionan con ellos; cada persona ve y marca solo los suyos (404 si no). Tipos nuevos con etiqueta: Corrección, Acta, Reasignación, Incorporación y Ficha (los generarán los hitos que construyan cada pantalla). Migración `alertas/0004` aditiva y con reversa | `apps/alertas/test_avisos_sin_entregable.py` (ModeloTests, PantallaDeAvisosTests, CuatroRolesTests, PantallasConAvisosSinEntregableTests, MigracionDeAvisosTests) |
| Enlace solo interno (sin redirecciones abiertas) | Hecho: empieza con una sola «/», sin esquema ni anfitrión, sin «://», barras invertidas, espacios ni caracteres de control. Se valida al guardar (`ValidationError`), en la base de datos (restricción `enlace_es_ruta_interna`, que cubre `bulk_create` y `update`) y otra vez al mostrarlo | `test_avisos_sin_entregable.py` (EnlaceInternoTests, ModeloTests, PantallaDeAvisosTests) |
| «Una alerta por umbral» conserva su sentido | Hecho: la restricción no cambia y la nueva `vencimiento_con_entregable` impide un aviso de vencimiento sin entregable (con el entregable vacío la base de datos no compararía la fila) | `test_avisos_sin_entregable.py` (UnaAlertaPorUmbralTests); `apps/alertas/tests.py` y `test_aviso_24h.py` sin cambios |
| Validación común de archivos (§5) | Hecho: `validar_archivo`, `sanear_nombre`, `extensiones_permitidas` y `tamano_maximo_bytes` pasan a `apps/entregables/archivos.py` sin cambiar su comportamiento ni sus mensajes. Como `tipos.py`, no importa modelos ni otras apps, así que la ficha (S2-H5) y el repositorio (S2-H9) pueden usarla sin importaciones circulares. Los adjuntos la usan y `adjuntos.py` sigue ofreciendo esos nombres | `apps/entregables/test_base_comun.py` (ValidarArchivoComunTests, LosAdjuntosUsanLaFuncionComunTests); `test_adjuntos.py` (ValidacionDeArchivosTests) sin cambios |
| Ayudante de pruebas `entregar(entregable, usuario)` (§11.3) | Hecho en `apps/entregables/testing.py`. En el S2-H2 solo llamaba a `servicios.mover`; **desde el S2-H4 crea un cargo ficticio (y una versión final ficticia si no hay) y usa el servicio de entrega `entregas.registrar`**; lo usan las pruebas que cierran entregables | `test_base_comun.py` (AyudanteEntregarTests) |

### Casos clave (§13)

| # | Caso | Prueba |
|---|---|---|
| 13 | Todo entregable nuevo tiene código único; el formulario rechaza la falta de ID-TDR o una recepción futura | `test_recepcion.py` (CodigoTests, NuevoEntregableConRecepcionTests) |
| 14 | El calendario filtra por cliente y estado sin ampliar la visibilidad y muestra al responsable | `test_filtros_y_responsable.py` (FiltrosDeEventosTests, EventoConResponsableTests, PaginaConFiltrosTests) |
| 15 | Con 5,2,1,0 el aviso de 24 h sale una sola vez y «Crítico» sigue empezando a 2 días | `test_aviso_24h.py` (AvisoDe24HorasTests, SegundoUmbralMayorTests y, con el valor por defecto de `settings.py`, ConfiguracionDeUmbralesTests y ValorPorDefectoTests) |
| 16 | Las columnas muestran las etiquetas de HU-04 y los códigos guardados no cambian | `test_etiquetas.py`, `test_recepcion.py` (MigracionDeRellenoTests) |
| 17 | Observar en revisión devuelve a En proceso, muestra «Con correcciones pendientes» y avisa al junior | `test_observaciones.py` (RegistrarTests.test_caso_17_observar_en_revision_devuelve_marca_el_subestado_y_avisa_al_junior, test_una_sola_en_revision_usa_los_textos_del_sprint_1) |
| 18 | No se resuelve una observación sin acción correctiva; no se aprueba con observaciones abiertas | `test_observaciones.py` (RevisarTests.test_caso_18_no_se_resuelve_sin_accion_correctiva, CorregirTests.test_exige_texto, CondicionesDeMoverTests) |
| 19 | No se pasa a Entregado sin cargo; la versión enviada queda bloqueada; restaurar crea versión nueva | `test_entregas.py` (ServicioDeEntregaTests.test_no_se_pasa_a_entregado_sin_cargo_por_ningun_camino, test_registrar_hace_todo_en_una_transaccion; VersionBloqueadaTests; RestaurarTests; SoltarEnEntregadoTests) |
| 20 | El acta pendiente más allá del plazo genera un solo aviso al junior y al senior | `test_entregas.py` (AlertaDeActaTests.test_pasado_el_plazo_avisa_al_junior_y_al_senior_una_sola_vez, test_el_plazo_es_mas_de_acta_dias_pendiente_dias, test_la_tarea_programada_diaria_y_el_comando_la_incluyen) |
| 21 | Una ficha mensual de 3 meses confirmada genera 3 entregables con código e ID-TDR; los plazos pasados se descartan con aviso; el estado documental inicial no cambia al actualizar el actual; un junior no puede confirmar | `apps/levantamiento/tests.py` (Caso21GeneracionDeEntregablesTests, Caso21ValidacionPokaYokeTests, Caso21EstadoInicialCongeladoTests, PermisosYVisibilidadTests) |
| 22 | Un responsable de apoyo ve el entregable pero no puede aprobar; reasignar deja historial y avisos | `test_personal.py` (Caso22ApoyoYReasignacionTests, ConflictosAsignacionTests, VistasPersonalYResponsablesTests) |
| 21b | Reabrir un entregado solo es posible con el acta observada, por senior, gerente o admin, y exige observación | `test_entregas.py` (ReaperturaTests) |
| 29 | Regresión: pasan las pruebas del Sprint 1 y `migrate` funciona sobre una base del Sprint 1 | Suite completa; `migrate` (y su reversa) probado sobre una copia de la base del `seed_demo` del Sprint 1 y sobre una base vacía (en el S2-H1 y otra vez en el S2-H2, con `alertas/0004`: los 64 avisos de esa base quedan idénticos, y la reversa solo quita los avisos que el esquema del Sprint 1 no admite) |

### Hitos (§12)

| Hito | Estado |
|---|---|
| S2-H0 Wireframes y decisiones | Hecho: wireframes y decisiones aprobados el 2026-11-02 |
| S2-H1 Cierre del Sprint 1 | Hecho; corregido y revisado en S2-H1-H2-ajustes (umbral por defecto 5,2,1,0 y datos de recepción y línea obligatorios siempre) |
| S2-H2 Base común | Hecho, sin cambiar ninguna prueba del Sprint 1 (decisiones abajo); revisado en S2-H1-H2-ajustes |
| S2-H3 Observaciones y revisiones | Hecho: una observación no queda resuelta sin acción correctiva; observar en revisión devuelve el entregable y avisa al junior con el código. Ninguna prueba del Sprint 1 cambió (decisiones abajo) |
| S2-H4 Versiones y entregas | Hecho: no se pasa a Entregado sin cargo; la versión enviada no se puede eliminar; restaurar crea una versión nueva; una sola alerta por acta pendiente. Pruebas del Sprint 1 ajustadas según la §11.3 y tres conteos derivados (ver «Ajustes del S2-H4») |
| S2-H5 Ficha de levantamiento | Hecho: los entregables generados desde una ficha confirmada aparecen en tablero y calendario con código e ID-TDR; los plazos pasados se descartan con aviso; el estado documental inicial no cambia al actualizar el actual; un junior no puede confirmar (403) |
| S2-H6 Personal y asignación | Hecho: un responsable de apoyo ve el entregable y no puede aprobarlo; la reasignación queda en el historial y avisa a quien entra y a quien sale; los conflictos (sobrecarga, plazo cercano y ausencia) se avisan antes de confirmar |
| S2-H7 a S2-H13 | Pendientes |

### Ajustes a pruebas del Sprint 1 (§11.3)

| Prueba | Fila de la §11.3 |
|---|---|
| `apps/calendario/tests.py` (test_el_estado_va_en_el_titulo), `apps/consolidado/tests.py` (test_los_contadores_por_estado_se_muestran_en_el_orden_del_tablero, test_resumenes_por_cliente_y_por_contrato), `apps/cuentas/test_interfaz.py` (test_las_cuatro_cifras_van_con_su_rotulo), `apps/entregables/test_adjuntos.py` (test_un_cambio_de_estado_sigue_mostrando_el_estado), `apps/entregables/test_interfaz.py` (test_pagina_completa_con_panel_de_filtros_columnas_y_tarjetas), `apps/entregables/test_reglas.py` (test_devolver_deja_el_motivo_en_el_historial, test_la_creacion_queda_en_el_historial_y_avisa_al_junior) | «Etiquetas de estados (RF-23)»: comparan contra `Entregable.Estado.X.label` |
| `apps/clientes/tests.py` (test_las_tres_pestanas_marcan_la_activa) | «Navegación nueva»: la lista esperada de pestañas de Gestión suma «Fichas» (S2-H5) y «Líneas de servicio» (S2-H1) |

El S2-H2 no cambió ninguna prueba del Sprint 1.

**Ajustes derivados de requisitos explícitos del SDD no previstos en la §11.3** (S2-H1-H2-ajustes; cada uno conserva lo que la
prueba verifica y lo indica con un comentario en el código):

| Prueba | Requisito | Ajuste |
|---|---|---|
| `apps/alertas/tests.py` (test_una_notificacion_por_umbral_a_lo_largo_de_los_dias) | RF-22 y §10.1: valor por defecto `5,2,1,0` | Fija con `override_settings` los umbrales `5,2,0` que verifica (sigue esperando `[0, 2, 5]`); el caso `5,2,1,0` está en `test_aviso_24h.py` |
| `apps/entregables/tests.py` (PokaYokeTests.datos), `apps/entregables/test_interfaz.py` (NuevoEntregableTests.datos), `apps/entregables/test_reglas.py` (test_la_creacion_queda_en_el_historial_y_avisa_al_junior, CamposDeOpcionTests.crear, ContratosDadosDeBajaTests.datos) | RF-20: ID-TDR y fecha de recepción obligatorios en el formulario | Envían `id_tdr` y `fecha_recepcion` |
| `apps/clientes/tests.py` (GestionTests.datos_contrato), `apps/entregables/test_reglas.py` (test_se_da_de_baja_desde_el_formulario_de_gestion) | RF-24: línea de servicio obligatoria en el formulario de contrato | Envían `linea_servicio` |

### Ajustes del S2-H4 (pruebas existentes)

Filas de la §11.3 aplicadas:

| Prueba | Fila de la §11.3 | Ajuste |
|---|---|---|
| `apps/conocimiento/tests.py` (GeneracionTests, IndexacionTests: `setUp` y casos que cierran el entregable), `apps/entregables/test_etiquetas.py` (test_el_detalle_ofrece_los_movimientos_con_las_etiquetas_nuevas), `apps/entregables/tests.py` (FlujoTests.test_camino_feliz_registra_historial), `apps/entregables/test_reglas.py` (AdjuntosYDatosEnElFlujoCompletoTests.test_flujo_completo) | «Cargo obligatorio para HECHO (RF-29)» | Llaman a `entregar(entregable, usuario)` (`apps/entregables/testing.py`) en lugar de `servicios.mover(..., HECHO, ...)` |
| `apps/entregables/test_adjuntos.py` (test_http_mensajes_claros_al_fallar_la_validacion) | «Comentario obligatorio al subir (formulario)» | Envía `comentario` |
| `apps/entregables/test_seed.py` (test_los_tipos_de_adjunto_son_variados) | «Cargo obligatorio…»: «el seed crea cargo y acta para los entregables cerrados» | El conjunto esperado de tipos suma `CARGO_RECEPCION` y `ACTA_CONFORMIDAD` |

**Ajustes derivados de RF-29 no previstos en la §11.3** (la prueba fija literalmente el historial del cierre, que ahora incluye el
cargo; conservan lo que verifican, con comentario en el código):

| Prueba | Ajuste |
|---|---|
| `apps/entregables/tests.py` (FlujoTests.test_camino_feliz_registra_historial) | Cuenta las 4 transiciones (`estado_anterior ≠ estado_nuevo`) en lugar de todas las líneas del historial: el cierre suma las líneas «Subió adjunto» de la versión final ficticia y «Registró el cargo…» |
| `apps/entregables/test_reglas.py` (AdjuntosYDatosEnElFlujoCompletoTests.test_flujo_completo) | Las dos comprobaciones de conteo del historial se hacen antes del cierre (3 transiciones + 1 subida) y, después de `entregar`, se comprueban las 4 transiciones |
| `apps/entregables/test_base_comun.py` (AyudanteEntregarTests, del S2-H2) | El ayudante ya no llama solo a `mover`: la prueba comprueba el cargo, la entrega, la versión bloqueada y una sola transición |

Otras pruebas del Sprint 2 actualizadas: `apps/clientes/test_lineas.py` (NavegacionTests) quita `/entregas/` de las «pantallas futuras»
porque ya existe (como se hizo con `/observaciones/` en el S2-H3). Todas las demás pruebas del Sprint 1 pasan sin cambios.

### Decisiones del S2-H5 (ficha de levantamiento)

1. **Inmutabilidad de `estado_inicial` garantizada en dos capas:** `servicios.confirmar` congela la fotografía inicial al pasar la ficha a `CONFIRMADA`, `servicios.actualizar_estado_documental` solo actualiza los cinco campos del estado actual (`update_fields`), y además `FichaLevantamiento.save()` consulta la base de datos cuando la fila ya estaba confirmada y restaura `estado_inicial` antes de escribir. Así ningún camino accidental en Python puede alterar el estado documental inicial congelado.
2. **Exclusión selectiva en la vista previa:** cada entrega proyectada se identifica por `(item_id, indice)` (por ejemplo `12:0`). Las casillas marcadas (o el botón «Quitar» de la tabla de vista previa) viajan como `excluir` al volver a calcular la vista previa y al confirmar, de modo que el senior confirma exactamente las filas que dejó activas.
3. **Acceso a `/fichas/` para los cuatro roles:** a diferencia de `/clientes/`, `/contratos/`, `/plantillas/` y `/lineas-servicio/` (exclusivas de gerente y admin), `/fichas/` está abierta a junior, senior, gerente y admin, filtrada siempre por `fichas_visibles(usuario)` (§7.5 y §8). La barra de pestañas de Gestión (`templates/clientes/_pestanas.html`) solo se muestra a gerente y admin para no exponer enlaces 403 a junior o senior.
4. **Creación de entregables con `EntregableForm` + `registrar_creacion`:** al confirmar la ficha dentro de `transaction.atomic()`, cada entregable pasa por `EntregableForm` (mismo Poka-Yoke que «Nuevo entregable», con `id_tdr=ficha.id_tdr` y `fecha_recepcion=hoy`) y por `servicios.registrar_creacion`, recibiendo código único `CT-AAAA-NNNNN`, entrada en el historial y notificación de asignación para el junior.

### Decisiones del S2-H4 (versiones y entregas)

1. **Cómo sabe `mover` que la entrega es del ciclo actual.** `Entrega.cierre` (FK nula al `HistorialEstado` del paso a Entregado):
   una entrega sin `cierre` es la del ciclo actual; `mover(..., HECHO)` exige una, la consume (`select_for_update`, una sola vez) y
   bloquea su versión enviada. Tras una reapertura la entrega anterior ya está cerrada, así que hace falta registrar otra (n.º + 1).
   Es un campo adicional a los de la §6.2.
2. **Un solo aviso de acta por entrega:** `Entrega.alerta_acta_en` (otro campo adicional), marcado con un UPDATE condicional antes de
   crear los avisos; sirve aunque la tarea corra varias veces o a la vez.
3. **«Más de 5 días»** es estricto: con `fecha_entrega` hace 5 días todavía no avisa; al sexto, sí (días desde la fecha de entrega,
   no desde el registro). `ACTA_DIAS_PENDIENTE` está en `settings.py` y `.env.example`.
4. **La versión enviada es obligatoria** (`Entrega.version_enviada` no admite nulo): por defecto la versión final vigente; si no hay
   ninguna y no se indica otra, el servicio lo rechaza diciendo qué falta. Es la lectura más conservadora de RF-28 (siempre hay una
   versión que bloquear). Puede indicarse cualquier adjunto del mismo entregable salvo el cargo y el acta.
5. **El cargo y el acta nacen bloqueados** (además de la versión enviada) y las referencias de `Entrega` son `PROTECT`: eliminar
   uno por cualquier camino fallaría con un error 500, así que `adjuntos.eliminar` y el panel técnico lo rechazan antes.
6. **El acta solo se registra o actualiza para la última entrega y mientras el entregable está Entregado**; cada archivo es una
   versión nueva de `ACTA_CONFORMIDAD`. Aceptar «Pendiente» no tiene sentido: el formulario solo ofrece Recibida y Observada.
7. **Quién se entera del acta:** el junior asignado y el senior revisor, salvo quien la registra (aviso tipo Acta, con el código y
   enlace a «Entregas y acta»).
8. **Entregados antes del Sprint 2.** Los 7 entregados de la base del Sprint 1 no tienen `Entrega` (no se puede inventar un cargo):
   no se pueden reabrir ni generan alerta de acta; los indicadores (S2-H8) usan el historial para ellos, como pide la §7.8.
9. **Textos del Sprint 1 que se conservan** («Subir un adjunto», «Ver versiones anteriores de …»): los fijan pruebas del Sprint 1 que
   la §11.3 no cubre.
10. **Tablero:** el servidor decide (permisos) y el script solo devuelve la tarjeta a «Aprobado» y envía la petición; así quien no
    puede entregar ve el 403 en el tablero y quien puede es llevado al formulario con `HX-Redirect`.
11. **La reapertura no se ofrece en «Mover entregable»:** vive en «Entregas y acta» (botón «Reabrir para corrección») solo con el
    acta observada, con su formulario de observación. El tablero la sigue intentando (arrastrar de Entregado a En proceso) y abre el
    mismo diálogo de observación del Sprint 1.

### Decisiones del S2-H1 (compatibilidad con el Sprint 1)

1. ~~**Datos de recepción y línea del contrato en peticiones anteriores al Sprint 2.**~~ Revertida en S2-H1-H2-ajustes: el S2-H1
   aceptaba una petición que no traía esas claves, lo que dejaba sin cumplir RF-20 y RF-24. Ahora son obligatorios siempre en los
   dos formularios (validación del servidor, mensaje del Poka-Yoke); la base de datos los sigue admitiendo vacíos para lo anterior.
2. **«Crítico» con el segundo umbral mayor de los positivos.** Con un solo umbral positivo se usa ese (así lo fija una prueba del
   Sprint 1 con `10,0`); con dos o más, el segundo mayor, como pide el SDD.
3. **Textos «verificación» que se conservan.** «No se puede enviar a verificación: …» y «… antes de pasar a verificación» no son la
   etiqueta del estado y los comparan pruebas del Sprint 1 que la §11.3 no cubre; el resto de textos fijos ya usa las etiquetas nuevas.

### Decisiones del S2-H2 (base común)

1. **A dónde lleva «Ver».** Al enlace, si el aviso lo tiene; si no, al detalle de su entregable; si no tiene ninguno de los
   dos, el aviso se muestra sin «Ver». Así un hito posterior puede llevar a una pantalla sin entregable (la ficha que espera
   confirmación) o a una sección concreta del detalle, y los avisos del Sprint 1, que no tienen enlace, siguen llevando al
   detalle.
2. **El enlace se comprueba tres veces.** Al guardar (salvo que solo se actualicen otros campos, para que un dato antiguo no
   impida marcar el aviso como leído), en la base de datos con una restricción sencilla y portable (vacío, o empieza con
   «/» y no con «//») y al mostrarlo: un enlace que no sea una ruta interna nunca se ofrece.
3. **Aviso de vencimiento siempre con entregable** (restricción `vencimiento_con_entregable`). La restricción «una alerta
   por umbral» no cambia, pero con el entregable vacío la base de datos no compararía la fila; así sigue cubriendo todo
   aviso de vencimiento, como en el Sprint 1.
4. **Columna `tipo` de 12 a 20 caracteres:** `INCORPORACION` tiene 13. Etiquetas de una palabra, como las del Sprint 1.
5. **Reversa de `alertas/0004`:** antes de volver a exigir el entregable borra los avisos que el esquema del Sprint 1 no
   puede guardar (sin entregable o de un tipo nuevo); los del Sprint 1 quedan intactos.
6. **`validar_archivo` en `apps/entregables/archivos.py`**, con el mismo criterio que `tipos.py` (módulo compartido sin
   modelos), en lugar de crear una app nueva que el SDD no prevé.
7. **El texto de la pantalla de avisos no cambia** («Avisos automáticos de asignaciones, observaciones, …»): los tipos
   nuevos todavía no se generan; cada hito lo actualizará cuando los use.

### Ajustes y revisión de S2-H1 y S2-H2 (S2-H1-H2-ajustes)

1. **Umbrales por defecto `5,2,1,0`** (RF-22, §10.1, aprobado en la §15) en `settings.py`, `.env.example` y el README. La prueba del
   Sprint 1 que verificaba `5,2,0` los fija con `override_settings` (tabla de ajustes de arriba).
2. **ID-TDR, fecha de recepción y línea de servicio obligatorios siempre** en sus formularios (RF-20, RF-24), aunque la petición no
   traiga la clave (antes se aceptaba como «petición anterior al Sprint 2»).
3. **Datos límite sin error 500:** `filtros.entero` descarta ids fuera del rango de un entero de 64 bits (SQLite lanzaba
   `OverflowError` en los filtros por cliente, contrato, responsable y línea de tablero, lista, calendario y consolidado); el
   calendario ignora un `start`/`end` que no es una fecha; «Nuevo entregable» usa `entero` en lugar de `str.isdigit()` para la
   plantilla («²» pasaba y fallaba la consulta).
4. **`/lineas-servicio/`:** un id de edición (`?editar=` o `linea` en el POST) mal escrito, fuera de rango o inexistente responde
   404; antes, en el POST, un id no numérico creaba una línea nueva en lugar de editar.
5. **Texto del botón** de «Nuevo entregable»: «Crear entregable», como en el wireframe aprobado `s2-nuevo`.
6. Revisado sin cambios: permisos de `/lineas-servicio/` (sin sesión al ingreso; junior y senior 403, como el resto de Gestión),
   calendario y avisos (cada persona solo ve y marca los suyos, 404 si no); filtros que parten de `entregables_visibles`; validación
   de `Notificacion.enlace`; CSRF; migraciones `clientes/0005`, `entregables/0003` y `alertas/0004` (con relleno y reversa, probadas
   otra vez sobre una copia de la base del Sprint 1 y una vacía); fechas locales de Lima en el código y la recepción.

### Decisiones del S2-H3 (observaciones y revisiones)

1. **Sin ajustes a pruebas del Sprint 1.** La fila «Sin observaciones pendientes para pasar a revisión o aprobar» de la §11.3 no
   tuvo pruebas afectadas: ninguna prueba del Sprint 1 devuelve y vuelve a enviar sin resolver. Las pruebas nuevas del rechazo
   están en `CondicionesDeMoverTests`. Se actualizaron dos pruebas del propio Sprint 2 (S2-H1): el título esperado de un evento
   del calendario en proceso con observaciones abiertas (ahora lleva el subestado) y la lista de «pantallas futuras», de la que
   sale `/observaciones/` porque ya existe.
2. **Una sola puerta y sin duplicados.** `servicios.mover` acepta, además de `tipo_error` y `descripcion` (Sprint 1), una lista
   `observaciones`; al devolver, valida y crea las observaciones dentro de su transacción. El servicio de registro, si el
   entregable está en revisión, se las pasa a `mover` en lugar de crearlas él. Textos del Sprint 1 intactos para una sola
   observación; con varias, «Devuelto con N observaciones (tipos)» y «… fue devuelto con N observaciones.».
3. **Sincronía `estado` ⇔ `resuelta`.** En `save()` gana el campo que cambió desde la lectura (así el código del Sprint 1 que
   marca `resuelta` sigue funcionando); las consultas de «abiertas» leen `resuelta=False` y las de «pendientes» además
   `estado=PENDIENTE`, para que un `update()` directo de `resuelta` (como hacen pruebas del Sprint 1) no deje datos incoherentes.
4. **Responsable posible:** el junior asignado (por defecto), el senior revisor o el senior responsable del contrato, es decir,
   quien ya ve el entregable (los responsables de apoyo llegarán con el S2-H6). El junior asignado que no es el responsable de
   una observación ve el entregable pero no registra su corrección (403).
5. **Corrección rechazada.** Vuelve a Pendiente conservando el texto, el autor y la fecha de la corrección rechazada (se muestra
   como «Corrección rechazada»); el motivo, opcional, queda en el historial. Los avisos de rechazo usan el tipo Observación.
6. **`/observaciones/<id>/resolver/` (Sprint 1)** sigue igual para las pendientes (una En corrección ya no: ver la revisión de abajo); ahora
   registra quién la resolvió y cuándo, deja constancia en el historial y rechaza resolver otra vez una observación ya resuelta
   (antes sobrescribía la solución). Redirige a la sección Observaciones del detalle (`#observaciones`).
7. **Pestañas de Entregables con `aria-current="true"`.** La barra principal conserva el único `aria-current="page"` de la
   sección (lo exige una prueba del Sprint 1); la pestaña activa es el elemento actual de su grupo.
8. **Respuesta a HTMX con `HX-Redirect`** a `#observaciones`: registrar, corregir o revisar pueden cambiar el estado, el subestado
   y lo que falta para avanzar, que están en otras partes del detalle.
9. **Sin consultas por fila.** El tablero y la lista calculan el subestado con el conteo de abiertas que ya traían; el calendario
   y el filtro usan EXISTS.

### Correcciones de la revisión de S2-H1-H2-ajustes y S2-H3

Pruebas en `apps/entregables/test_observaciones.py` (CorreccionesDeLaRevisionTests). Ninguna prueba del Sprint 1 cambió.

1. **Rechazar en Revisión senior devuelve el entregable** (§7.1, §7.2, RF-26). Antes la observación volvía a Pendiente con el
   entregable en revisión. Ahora `observaciones.rechazar` lo pasa a En proceso en la misma transacción con `servicios.mover`, que
   acepta `rechazo=<observación>`: la rechazada, ya Pendiente y del mismo entregable, es la observación de la devolución (no se crea
   otra). Historial «Devuelto por corrección rechazada (tipo)»; queda «Con correcciones pendientes»; se avisa al responsable y,
   si no es él, también al junior asignado.
2. **La resolución directa solo existe desde Pendiente** (diagrama de la §7.2). Una observación En corrección se confirma o se
   rechaza; `/observaciones/<id>/resolver/` la rechaza con un mensaje en lugar de sobrescribir la acción correctiva del responsable.
3. **No se registran observaciones en Aprobado ni en Entregado.** El SDD no fija este caso; como `LISTO_PARA_ENTREGA → HECHO` no
   comprueba observaciones, registrarlas ahí esquivaba la regla «no se aprueba con observaciones abiertas» (§7.1, caso 18). El
   servicio lo rechaza con el motivo y el detalle no ofrece el formulario en esos estados. Un entregado con acta observada se
   reabre con su observación por la transición `HECHO → EN_PROCESO` del S2-H4 (§7.4).
4. **Desviación registrada: texto del evento del calendario.** El wireframe `s2-calendario` lo escribe «[Estado] CÓDIGO Cliente:
   Título — Julia J. — Próximo»; el sistema escribe «[Estado] CÓDIGO Cliente (a cargo de Nombre Apellido): Título — Próximo».
   Contiene lo que exige la anotación 2 (responsable y código en el texto; estado y urgencia en texto). Se conserva porque en el
   Sprint 1 «—» solo introduce la urgencia: una prueba del Sprint 1 (`apps/calendario/tests.py`,
   test_lo_normal_y_lo_hecho_no_llevan_etiqueta_de_urgencia) exige que un evento sin urgencia no lo tenga y que termine en el
   título, y ningún requisito explícito del SDD obliga a cambiarla.

## Pendiente para cerrar el SDD

1. **Probar Docker Compose** y el asistente contra un Ollama real (elegir modelos y ajustar `ASSISTANT_MIN_SIMILARITY`).
2. **Confirmar** gunicorn y WhiteNoise (decisión n.º 8) y el índice vectorial propio en lugar de ChromaDB.
3. **Prueba de uso con personas del equipo** y revisión con lector de pantalla (RNF-02 y RNF-03).
4. **Pruebas de navegador dentro del repositorio.** Hoy se hicieron con Playwright desde fuera; incorporarlas exigiría sumar una dependencia de desarrollo, que no está en la lista aprobada.
5. **Decisiones de interfaz con valor por defecto** (las siete preguntas de `docs/wireframes/index.html`): siguen vigentes porque el equipo no pidió cambios al aprobar; confirmarlas por escrito.
