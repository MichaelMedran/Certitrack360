# CertiTrack 360 — SDD del Sprint 3

| | |
|---|---|
| **Proyecto** | CertiTrack 360, plataforma de seguimiento de entregables del área de Proyectos de CERTICOM S.A.C. |
| **Versión** | 3.0 (Sprint 3) |
| **Fecha** | 2026-11-10 |
| **Estado** | En construcción. Las decisiones de la sección 15 se tomaron con el valor propuesto porque el equipo pidió ejecutar el sprint de inmediato; quedan **por ratificar** |
| **Se apoya en** | SDD v1.0 (2026-10-05) y SDD del Sprint 2 (`docs/sdd-sprint-2.md`), vigentes en todo lo que este documento no cambia |
| **Fuente del alcance** | Tablero de Trello del equipo: las 13 historias con la etiqueta «Sprint 3» (leídas el 2026-11-10) |

> **Cómo usar este documento.** Es la especificación del Sprint 3. Los identificadores RF-01 a RF-38, las reglas de negocio, los permisos y
> las restricciones del cliente (RC-01 a RC-09) **siguen vigentes**. Cada requisito nuevo (RF-40 en adelante; RF-39 quedó reservado) nace de
> una historia (HU-xx), se asigna a un hito (sección 12) y se traza a pruebas (sección 13).
> Regla de oro: **ningún hito se da por terminado si alguna prueba de los sprints anteriores falla** (868 pruebas en verde al empezar).

---

## 1. Resumen

El Sprint 2 dejó observaciones con estados, versiones, entregas con cargo, ficha de levantamiento, personal, tiempo por etapa, indicadores,
repositorio, buscador, asistente ampliado y plan de incorporación. El Sprint 3 construye las **13 historias** con la etiqueta «Sprint 3»:

| Grupo | Historias | Qué aporta |
|---|---|---|
| A. Clasificar y priorizar | HU-23, HU-29, HU-28 | Etiquetas de colores, orden automático por prioridad y alerta de urgencia fuera de horario |
| B. Calidad antes de enviar | HU-25, HU-26, HU-30 | Checklist por TDR, checklist de control de calidad por cliente y verificación del número de factura |
| C. Menos digitación | HU-24, HU-27 | Prellenado desde documentos escaneados (OCR local) y exportación a PDF y Excel |
| D. Gerencia | HU-22, HU-31 | Gráficos gerenciales en el consolidado y reportes automáticos de avance |
| E. Plataforma | HU-09 | Plataforma independiente: servidor propio, acceso seguro y sin salida de datos a nubes externas |
| F. Ya construidas | HU-11, HU-13 | Tiempo por etapa (RF-32) e indicadores (RF-33) se entregaron en el Sprint 2; aquí se **auditan** contra sus criterios y se cierran brechas |

---

## 2. Historias ya construidas que Trello mantiene en el Sprint 3

HU-11 y HU-13 llevan ahora la etiqueta «Sprint 3», pero se construyeron en los hitos S2-H7 y S2-H8. No se reconstruyen: el hito S3-H1
compara criterio por criterio y agrega solo lo que falte, con su prueba.

| Historia | Criterio | Situación | Qué se hace |
|---|---|---|---|
| HU-11 | 1. Iniciar, pausar y finalizar por etapa desde la ficha | Hecho (RF-32) | Verificar |
| HU-11 | 2. Guarda entregable, cliente, etapa, responsable, fecha, inicio y fin | Hecho: cliente y fecha se derivan | Verificar que el listado los muestre todos |
| HU-11 | 3. Ajuste manual con motivo y marca «Manual» | Hecho | Verificar |
| HU-11 | 4. Acumulado por etapa y total en la ficha | Hecho | Verificar |
| HU-11 | 5. Visibilidad por rol y filtros (cliente, etapa, responsable, fechas) | Hecho | Verificar |
| HU-13 | 1 a 5 (cuatro indicadores, cálculo automático, filtros, fórmula visible, visibilidad por rol) | Hecho (RF-33) | Verificar; toda brecha se corrige como RF-40 |

---

## 3. Conflictos con los SDD anteriores y cómo se resuelven

| # | Choque | Resolución | Tipo |
|---|---|---|---|
| D1 | **RNF-13** («sin dependencias nuevas») contra HU-27 (archivos que abran en Excel y en un visor de PDF «sin ajustes»), HU-31 (PDF) y HU-24 (OCR) | Se agregan cuatro bibliotecas **locales**, sin servicios externos: `openpyxl` (Excel), `reportlab` (PDF), `pypdf` (texto de PDF) y `pypdfium2` con `Pillow` (convertir páginas escaneadas en imagen). RNF-13 se reemplaza por RNF-15 | Por ratificar |
| D2 | **HU-24** exige OCR de PDF escaneados; el servidor debe tener un motor de OCR | Motor **Tesseract** instalado en el servidor (programa externo, local). Si no está, la extracción funciona con PDF que traen texto y avisa que el OCR no está disponible; el usuario completa a mano (misma degradación que el asistente sin Ollama, RNF-09) | Por ratificar |
| D3 | **HU-28** pide «notificación push o correo»; C4 del Sprint 2 dejó solo avisos dentro de la plataforma | Aviso **destacado dentro de la plataforma** (franja roja «URGENTE» en todas las pantallas hasta confirmar lectura). El correo se envía **solo si** se configura un servidor de correo local (`EMAIL_HOST`); por defecto está apagado | Por ratificar |
| D4 | **HU-28** habla de «grupo de guardia» y «Líder de operaciones», que no existen como roles | No se crea un rol nuevo: `Usuario.de_guardia` (lo marca gerente o admin en Gestión › Personal). Activan la alerta senior, gerente y admin | Por ratificar |
| D5 | **HU-29** ordena por «tipo de cliente», que no existe | `Cliente.tipo`: Estratégico, Regular (por defecto) u Ocasional, editable en Gestión › Clientes | Por ratificar |
| D6 | **HU-26** criterio 4 (solo se aprueba con los ítems obligatorios conformes) cambia la regla `VERIFICACION_SENIOR → LISTO_PARA_ENTREGA` | Se agrega la condición. Cambio de comportamiento **deliberado**: las pruebas y el `seed_demo` que aprueban entregables usan el ayudante `aprobar()` (sección 11.3) | Aprobado por la HU |
| D7 | **HU-30** criterio 3 dice «Listo para entrega»; en el tablero ese estado se llama «Aprobado» (RF-23) | Es el mismo estado (`LISTO_PARA_ENTREGA`). La condición aplica solo si el entregable **tiene** número de factura; sin número no se exige nada | Decisión de diseño |
| D8 | **HU-25** criterio 4 dice «advertir», no «bloquear» | Aviso con confirmación: el envío a Revisión senior con ítems obligatorios pendientes pide un segundo clic y queda en el historial | Decisión de diseño |
| D9 | **HU-09** «instalada en un servidor propio de CERTICOM» no se puede cumplir desde el repositorio | Se entrega lo que depende del software: servidor de aplicación de producción, guía de despliegue, cabeceras que impiden enviar datos a otros orígenes y bloqueo de intentos de ingreso. La instalación física queda como tarea del área de Sistemas (sección 16) | Parcial por naturaleza |
| D10 | **HU-09** «solo a Filedoc» | `FILEDOC_URL` es el **único** origen externo permitido por la política de contenido; vacío por defecto (ninguno) | Por ratificar |
| D11 | **HU-27** «respetar la plantilla del cliente» | Excel: si la plantilla TDR enlaza un formato `.xlsx` del repositorio (RF-34), se rellenan sus marcadores `{{campo}}`; si no, se usa el formato estándar. PDF: formato estándar con los campos de la plantilla en su orden | Por ratificar |
| D12 | **HU-31/HU-22** frente al consolidado (RF-16) | El consolidado no cambia sus cifras; los gráficos se suman debajo y los reportes viven en la pestaña «Reportes» del consolidado | Compatible |

---

## 4. Alcance del Sprint 3 (requisitos funcionales nuevos)

| Id | Requisito | Historia | Prioridad | Hito |
|---|---|---|---|---|
| RF-40 | Cierre de brechas de tiempo por etapa e indicadores, si la auditoría encuentra alguna | HU-11, HU-13 | M | S3-H1 |
| RF-41 | **Etiquetas** de colores configurables para contratos y entregables, con filtro en tablero y lista; las crean los seniors | HU-23 | M | S3-H2 |
| RF-42 | **Prioridad** calculada (Alta, Media, Baja) que combina urgencia, cercanía del plazo y tipo de cliente; orden por defecto del tablero, la lista y el inicio | HU-29 | M | S3-H3 |
| RF-43 | **Alerta de urgencia** fuera de horario: selector al registrar, aviso «URGENTE» a guardia y responsables, y confirmación de lectura y de aceptación | HU-28 | M | S3-H4 |
| RF-44 | **Checklist por TDR** por entregable, generado desde la ficha de levantamiento, con estados, sustento, % de cumplimiento y aviso antes de la revisión | HU-25 | M | S3-H5 |
| RF-45 | **Checklist de control de calidad** configurable por cliente; condición para aprobar; cada revisión queda registrada | HU-26 | M | S3-H6 |
| RF-46 | **Verificación del número de factura** contra una base de facturación simulada, en solo lectura, con historial y justificación del senior | HU-30 | M | S3-H7 |
| RF-47 | **Exportación** del entregable a PDF y Excel con validación de obligatorios, registrada y guardada como versión | HU-27 | M | S3-H8 |
| RF-48 | **Extracción de datos** (OCR local) con vista previa editable y aviso de ilegibilidad | HU-24 | M | S3-H9 |
| RF-49 | **Gráficos gerenciales** en el consolidado (4 gráficos, filtros por cliente, sector, contrato y fechas) | HU-22 | M | S3-H10 |
| RF-50 | **Reportes de avance** automáticos y a pedido, guardados, en PDF, con aviso al gerente | HU-31 | M | S3-H11 |
| RF-51 | **Plataforma independiente**: servidor de producción, política de contenido sin orígenes externos (salvo Filedoc), bloqueo de intentos de ingreso y guía de despliegue | HU-09 | M | S3-H12 |

Requisitos no funcionales: rigen RNF-01 a RNF-12 y RNF-14. Cambios:

| Id | Requisito |
|---|---|
| RNF-15 | **Dependencias locales (reemplaza a RNF-13).** Solo se agregan bibliotecas que trabajan en el servidor sin conectarse a internet: `openpyxl`, `reportlab`, `pypdf`, `pypdfium2`, `Pillow`, `waitress` y `whitenoise`. Los gráficos se dibujan en el servidor como SVG, sin bibliotecas de JavaScript nuevas. |
| RNF-16 | **Sin salida de datos.** Ninguna pantalla carga recursos ni envía formularios a otro origen que el propio servidor (y `FILEDOC_URL`, si se configura). Lo comprueba una prueba que recorre plantillas y archivos estáticos, y lo impone la cabecera `Content-Security-Policy`. |
| RNF-17 | **Módulos independientes.** Cada historia nueva vive en su propia app; se integra con el detalle del entregable y con la máquina de estados mediante los puntos de extensión de `apps/entregables/extensiones.py`, sin editar `servicios.mover`. |

---

## 5. Arquitectura

Se mantiene el monolito modular de Django con HTMX. Apps nuevas y cambios:

```
apps/
  entregables/    + extensiones.py (puntos de extensión); orden «prioridad»; TipoAdjunto.EXPORTACION
  clientes/       + Cliente.tipo
  cuentas/        + Usuario.de_guardia; bloqueo de intentos de ingreso; cabeceras de seguridad
  etiquetas/      NUEVA: Etiqueta (HU-23)
  urgencias/      NUEVA: AlertaUrgente, LecturaAlerta (HU-28)
  checklists/     NUEVA: ItemChecklistTDR (HU-25); ItemCalidad, RevisionCalidad, RespuestaCalidad (HU-26)
  facturacion/    NUEVA: FacturaSimulada, VerificacionFactura y conector de solo lectura (HU-30)
  exportacion/    NUEVA: generación de PDF y Excel (HU-27); utilidades de PDF compartidas
  extraccion/     NUEVA: Extraccion y motores de texto/OCR (HU-24)
  consolidado/    + graficos.py (SVG en el servidor) (HU-22)
  reportes/       ReporteAvance, ConfiguracionReporte, tarea programada (HU-31)
```

### 5.1 Puntos de extensión (`apps/entregables/extensiones.py`, RNF-17)

`servicios.mover` sigue siendo la **única puerta** para cambiar de estado. Las condiciones nuevas no se escriben dentro de él: cada app las
registra en su `AppConfig.ready()`.

| Función | Uso |
|---|---|
| `registrar_condicion(fn)` | `fn(entregable, nuevo_estado, usuario, opciones) -> str | Advertencia | None`. Un texto **bloquea** el paso (se suma a los motivos de `mover`). Una `Advertencia(clave, mensaje)` lo detiene solo hasta que quien mueve la confirma (`opciones["confirmadas"]` contiene la clave) |
| `registrar_al_mover(fn)` | `fn(entregable, anterior, nuevo, usuario, opciones)`; se ejecuta dentro de la transacción de `mover`, después de guardar el cambio |
| `registrar_seccion(fn)` | `fn(usuario, entregable) -> dict | None` con `orden`, `plantilla` (ruta del parcial) y `contexto`; el detalle las muestra en orden, antes del historial |
| `registrar_tarjeta(fn)` | `fn(entregables, usuario)`; agrega atributos a las tarjetas del tablero y a las filas de la lista con consultas por lote (nunca una por tarjeta) |

`mover(..., confirmadas=())` recibe las advertencias ya confirmadas. Una advertencia sin confirmar lanza `ValidationError` con
`code="advertencia"` y `params={"clave": ..., "mensaje": ...}`; el tablero abre un diálogo de confirmación (igual que el de devolución) y el
detalle muestra un botón «Enviar de todos modos».

Principios que se conservan: la visibilidad se aplica en el queryset base (`entregables_visibles`), las reglas viven en servicios, y toda
subida o descarga de archivos pasa por la validación común y por una vista con verificación de permisos.

---

## 6. Modelo de datos

### 6.1 Cambios en modelos existentes (todos aditivos)

| Modelo | Cambio | Migración |
|---|---|---|
| `Cliente` | `tipo` (`ESTRATEGICO`, `REGULAR`, `OCASIONAL`; por defecto `REGULAR`) | Los existentes quedan `REGULAR` |
| `Usuario` | `de_guardia` (bool, por defecto falso) | — |
| `TipoAdjunto` | Suma `EXPORTACION` («Exportación»): la crea la exportación, no la subida manual | Solo cambian las opciones |
| `Notificacion.Tipo` | Suma `URGENTE`, `REPORTE`, `CHECKLIST` y `FACTURA` | Solo cambian las opciones |

### 6.2 Modelos nuevos

**Etiqueta** (`etiquetas`): `nombre` (único sin distinguir mayúsculas), `color` (uno de 8 colores con contraste comprobado), `linea_servicio`
(uno a uno, opcional: la etiqueta de la línea), `activa`, `creada_por`, `creada_en`, `contratos` (M2M) y `entregables` (M2M). Una migración
crea una etiqueta por cada línea de servicio existente. La tarjeta muestra las etiquetas del entregable **y** las de su contrato.

**AlertaUrgente** (`urgencias`): `entregable`, `naturaleza` (texto obligatorio), `plazo_esperado` (fecha y hora), `fuera_de_horario`
(calculado al activar con `HORARIO_LABORAL`), `activada_por`, `activada_en`, `aceptada_por`, `aceptada_en`, `cerrada_en`. A lo sumo una
alerta sin cerrar por entregable. **LecturaAlerta**: `alerta`, `usuario`, `leida_en` (única por alerta y usuario).

**ItemChecklistTDR** (`checklists`): `entregable`, `texto`, `tipo` (`REQUISITO`, `DOCUMENTO`, `FORMATO`), `obligatorio`, `estado`
(`PENDIENTE`, `EN_REVISION`, `CUMPLIDO`), `marcado_por`, `marcado_en`, `adjunto` (FK opcional a un adjunto del mismo entregable), `origen`
(`FICHA`, `MANUAL`), `orden`, `creado_por`, `creado_en`.

**ItemCalidad** (`checklists`): `cliente` (vacío = aplica a todos), `texto`, `categoria` (`INFORMACION_COMPLETA`, `CONSISTENCIA`,
`FECHAS_VIGENCIA`, `FORMATO`, `OTRO`), `obligatorio`, `activo`, `orden`. Una migración crea los cuatro ítems generales mínimos (HU-26
criterio 1). **RevisionCalidad**: `entregable`, `revisor`, `fecha`, `resultado` (`CONFORME`, `NO_CONFORME`). **RespuestaCalidad**:
`revision`, `item` (FK opcional), `texto` y `obligatorio` (copia del ítem al revisar), `resultado` (`CONFORME`, `NO_CONFORME`),
`observacion`. Las revisiones nunca se editan: una nueva revisión es un registro nuevo.

**FacturaSimulada** (`facturacion`): `numero` (único), `cliente_nombre`, `contrato_numero`, `estado` (`EMITIDA`, `PAGADA`, `ANULADA`),
`fecha_emision`, `monto`. Es la base de facturación **simulada** (HU-30 criterio 5): la plataforma solo la lee.
**VerificacionFactura**: `entregable`, `numero`, `resultado` (`CORRECTA`, `NO_EXISTE`, `OTRO_CLIENTE`, `OTRO_CONTRATO`, `ANULADA`,
`SIN_CONEXION`), `detalle` (JSON con lo que devolvió la consulta), `usuario`, `fecha`, `justificacion`, `justificada_por`, `justificada_en`.
El número vigente del entregable es el de su última verificación.

**Extraccion** (`extraccion`): `usuario`, `archivo` (validado, carpeta `extracciones/`), `nombre_original`, `motor` (`TEXTO_PDF`,
`TESSERACT`, `NINGUNO`), `texto`, `campos` (JSON: valor propuesto, confianza y origen por campo), `ilegible` (bool) y `avisos` (JSON),
`entregable` (opcional), `aplicada_en`, `creada_en`. Cada usuario ve solo las suyas.

**ReporteAvance** (`reportes`): `origen` (`AUTOMATICO`, `MANUAL`), `generado_por` (opcional), `generado_en`, `datos_al` (fecha y hora de los
datos), `datos` (JSON con todas las cifras), `archivo` (PDF, carpeta `reportes/`). **ConfiguracionReporte** (una sola fila): `periodicidad`
(`DIARIA`, `SEMANAL`, `MENSUAL`, `DESACTIVADA`), `dia_semana`, `dia_mes`, `hora`, `ultimo_automatico`.

**IntentoIngreso** (`cuentas`): `usuario_texto`, `ip`, `fecha`, `exitoso`. Sirve para el bloqueo temporal (RF-51).

---

## 7. Reglas de negocio

### 7.1 Flujo de estados

Los códigos y las transiciones no cambian. Condiciones nuevas, todas registradas como extensiones (5.1):

| Transición | Condición nueva | Tipo |
|---|---|---|
| `EN_PROCESO → VERIFICACION_SENIOR` | Ítems obligatorios del checklist por TDR aún pendientes (RF-44) | Advertencia con confirmación |
| `VERIFICACION_SENIOR → LISTO_PARA_ENTREGA` | Si hay ítems de calidad aplicables: la última revisión de calidad del **ciclo de revisión actual** debe ser `CONFORME` (RF-45) | Bloqueo |
| `VERIFICACION_SENIOR → LISTO_PARA_ENTREGA` | Si el entregable tiene número de factura: su última verificación debe ser `CORRECTA` o tener la justificación de un senior (RF-46) | Bloqueo |

El **ciclo de revisión actual** empieza en el último paso a `VERIFICACION_SENIOR` del historial: una revisión de calidad anterior a ese
paso no sirve para aprobar.

### 7.2 Etiquetas (RF-41)

- Crean y editan etiquetas: senior, gerente y admin (pestaña «Etiquetas» de Gestión para gerente y admin; los seniors, desde un formulario
  breve en la pantalla «Nuevo entregable» y en el detalle). Dar de baja: gerente y admin. Una etiqueta de baja deja de ofrecerse, pero se
  conserva donde ya estaba.
- Colores: lista cerrada de 8 (gris, azul, verde, ámbar, rojo, morado, turquesa, rosa); el nombre siempre va en texto (no solo color).
- Asignar a un entregable: quien lo crea, en «Nuevo entregable» (viene marcada la etiqueta de la línea del contrato), y después el senior del
  entregable, el gerente o el admin desde el detalle. Asignar a un contrato: gerente y admin en Gestión › Contratos.
- Filtro «Etiqueta» en tablero y lista: coincide con las etiquetas del entregable o de su contrato; se combina con los demás filtros y nunca
  amplía la visibilidad.

### 7.3 Prioridad (RF-42)

Se calcula en el momento, no se guarda; por eso se recalcula sola al cambiar un plazo, el tipo de cliente o una alerta (criterio 4).

| Nivel | Cuándo | Color (siempre con texto) |
|---|---|---|
| **Alta** | Vencido, crítico (vence en `critico` días o menos), con alerta urgente abierta, o próximo y de cliente Estratégico | Rojo |
| **Media** | Próximo (no estratégico), o normal de cliente Estratégico que vence en `PRIORIDAD_DIAS_ESTRATEGICO` días o menos (por defecto 10) | Ámbar |
| **Baja** | El resto. Un entregable Entregado no tiene prioridad | Verde |

Orden «Prioridad» (nuevo valor por defecto del tablero, la lista y los pendientes del inicio): nivel (Alta, Media, Baja), después alerta
urgente abierta primero, plazo más próximo, tipo de cliente (Estratégico, Regular, Ocasional) e id. Los órdenes anteriores (plazo, urgencia,
cliente) se conservan. La urgencia del Sprint 1 (Vencido, Crítico, Próximo, Normal) no cambia y se sigue mostrando.

### 7.4 Alerta de urgencia fuera de horario (RF-43)

- «Nuevo entregable» incluye el selector **Prioridad: Normal / Urgente – fuera de horario**. Si se elige urgente son obligatorios la
  naturaleza de la urgencia y el plazo esperado (fecha y hora futuras). También se puede activar después, desde el detalle. La activan senior
  del entregable, gerente y admin.
- Al activar: se crea la alerta y un aviso `URGENTE` para cada destinatario: usuarios **de guardia** activos, senior responsable del contrato,
  senior revisor y junior asignado (sin repetir, sin quien la activa). El mensaje empieza con «URGENTE» y dice cliente, naturaleza y plazo
  esperado, con enlace al entregable.
- Mientras un destinatario no confirme la lectura, ve una franja roja «URGENTE» en todas las pantallas. «Confirmar lectura» registra quién
  y cuándo. «Aceptar el caso» (un destinatario o un senior del entregable) registra quién atiende la contingencia; solo una persona lo acepta.
- La alerta se cierra al aceptarla o cuando el entregable pasa a Entregado. `fuera_de_horario` se calcula con `HORARIO_LABORAL`
  (por defecto lunes a viernes de 09:00 a 18:00, hora de Lima) y se muestra en la alerta.
- Correo (D3): si `EMAIL_HOST` está configurado, se envía además un correo con asunto «URGENTE: …» a los destinatarios con dirección
  registrada. Un fallo del correo no impide la alerta.

### 7.5 Checklist por TDR (RF-44)

- **Generación:** al confirmar una ficha de levantamiento, cada entregable generado recibe su checklist; en cualquier entregable cuyo contrato
  tenga una ficha confirmada, «Generar desde el TDR» lo crea a pedido (no duplica ítems ya generados). Un ítem por línea no vacía de
  `requerimientos` (tipo Requisito), de `documentos_disponibles` y `documentos_faltantes` (Documento) y de `formatos` y `formato_esperado`
  (Formato). Los requisitos y los documentos nacen obligatorios. Se pueden **agregar ítems a mano** (obligatorios o no).
- Marcan y agregan: los responsables activos del entregable (junior asignado, apoyos y seniors del entregable). Cada cambio guarda quién y
  cuándo. Un ítem puede enlazar un adjunto del mismo entregable como sustento.
- El detalle muestra el **% de cumplimiento** (cumplidos ÷ total) y resalta los obligatorios pendientes.
- **Aviso (D8):** al enviar a Revisión senior con obligatorios sin cumplir se pide confirmación; si se confirma, el historial registra
  «Enviado a revisión con N ítems obligatorios del checklist pendientes».
- **Consulta:** pestaña «Checklists» de Entregables, con filtros por cliente, contrato e ID-TDR, sobre los entregables visibles.

### 7.6 Checklist de control de calidad (RF-45)

- **Configuración:** pestaña «Checklist de calidad» en Gestión (gerente y admin) y, para los seniors, la misma pantalla limitada a los
  clientes de sus contratos. Los ítems generales (sin cliente) solo los edita gerente o admin. A un entregable le aplican los ítems activos
  generales más los de su cliente.
- **Revisión:** el checklist aparece en el detalle cuando el entregable está en Revisión senior. El senior del entregable (o gerente o admin)
  marca **cada** ítem Conforme o No conforme; un No conforme exige su observación.
- Al guardar se crea la revisión con revisor, fecha, hora y resultado (criterio 5). Si hay algún No conforme: resultado `NO_CONFORME`, se
  registra una observación por ítem no conforme con `observaciones.registrar` (tipo de error según la categoría) y, como en RF-26, el
  entregable vuelve a En proceso con «Con correcciones pendientes» y se avisa al junior. Si todos los obligatorios están conformes:
  `CONFORME` y el entregable ya puede aprobarse.
- Un ítem **no obligatorio** marcado No conforme genera su observación, pero no impide el resultado `CONFORME`… salvo por la regla existente
  de que no se aprueba con observaciones abiertas.
- El detalle muestra el historial de revisiones de calidad del entregable.

### 7.7 Verificación de factura (RF-46)

- En el detalle, los responsables activos ingresan el número de factura o correlativo y pulsan «Verificar».
- El **conector** (`facturacion/conector.py`) consulta en solo lectura y devuelve si existe, a qué cliente y contrato pertenece y su estado.
  El conector simulado lee `FacturaSimulada`; `FACTURACION_CONECTOR` permite cambiarlo por el del sistema real cuando Sistemas lo autorice.
- Resultado: `CORRECTA` si existe, no está anulada y coincide con el cliente y el número de contrato del entregable. Si no, se muestra la
  advertencia con el motivo exacto.
- Cada verificación se guarda (usuario, fecha, hora, resultado) y se suma al historial del entregable.
- Con una verificación no correcta, el entregable no pasa a Aprobado hasta que se verifique un número correcto o un senior del entregable
  registre la **justificación** (texto obligatorio; queda en el historial).

### 7.8 Exportación a PDF y Excel (RF-47)

- Botón «Exportar» en el detalle, con las opciones PDF y Excel, para los responsables activos, el gerente y el admin.
- Datos consolidados: código, título, cliente, contrato, línea de servicio, ID-TDR, **periodo** (mes y año del plazo), fecha de recepción,
  plazo, estado, responsables y todos los campos de la plantilla con su etiqueta.
- **Validación:** si falta algún campo obligatorio de la plantilla, el ID-TDR o la fecha de recepción, no se exporta y se dice qué falta.
- **Excel (D11):** con formato `.xlsx` enlazado, se rellenan los marcadores `{{codigo}}`, `{{cliente}}`, `{{contrato}}`, `{{periodo}}`,
  `{{titulo}}`, `{{id_tdr}}`, `{{plazo}}`, `{{fecha_recepcion}}`, `{{linea_servicio}}`, `{{junior}}`, `{{senior}}` y `{{<nombre del campo>}}`;
  sin formato, una hoja estándar con dos columnas. **PDF:** documento A4 estándar con encabezado, tabla de datos y pie con fecha y usuario.
- Cada exportación crea un `Adjunto` de tipo `EXPORTACION` (versión nueva; nunca se sobrescribe), registra usuario, fecha y hora en el
  historial y descarga el archivo.

### 7.9 Extracción de datos con OCR (RF-48)

- **Dónde:** (a) en «Nuevo entregable», «Prellenar desde un documento» (PDF o imagen); (b) en el detalle, «Extraer datos» sobre un adjunto
  ya subido, para completar los datos de la plantilla (elaboradores y seniors del entregable, en Por hacer o En proceso).
- **Motores, en orden:** texto del propio PDF (`pypdf`); si la página no trae texto, o el archivo es una imagen, **Tesseract** (cada página
  se convierte en imagen con `pypdfium2`). Sin Tesseract instalado se avisa «El OCR no está disponible en este servidor» y se sigue a mano.
- **Campos que busca:** cliente (por coincidencia con los clientes que el usuario puede ver), número de contrato (contra los contratos
  visibles), ID-TDR, fechas (recepción y plazo) y cada campo de la plantilla por su etiqueta («Etiqueta: valor»).
- **Vista previa (criterio 3):** tabla con cada campo, el valor propuesto (editable), de dónde salió y su confianza. Nada se guarda hasta
  que el usuario confirma; al confirmar, los valores pasan al formulario normal y se validan con el mismo Poka-Yoke.
- **Ilegibilidad (criterio 4):** se avisa si la confianza media del OCR es menor que `OCR_CONFIANZA_MINIMA` (por defecto 60), si una página
  no dio texto o si un campo no se encontró; esos campos quedan vacíos y resaltados para completarlos a mano (criterio 5).
- En «Nuevo entregable», el documento usado se adjunta como TDR al crear el entregable. Límite: `OCR_MAX_PAGINAS` (por defecto 10).

### 7.10 Gráficos gerenciales (RF-49)

En `/consolidado/` (solo gerente y admin), debajo de las cifras actuales, cuatro gráficos de barras dibujados como SVG en el servidor:
entregables activos por persona, % de entregables cumplidos dentro del plazo por mes, tiempo promedio de atención por cliente (días entre la
recepción y la entrega) y observaciones por tipo de error. Filtros: cliente, **sector**, contrato y rango de fechas; cada gráfico muestra el
filtro aplicado y, debajo, su tabla de datos (accesible). Sin datos, lo dice en texto. Reutiliza los cálculos de `indicadores.servicios`.

### 7.11 Reportes de avance (RF-50)

- Contenido, por cliente y contrato: cantidad de entregables en cada estado, vencidos, por vencer (ventana `CONSOLIDADO_WINDOW_DAYS`) y
  observaciones pendientes; totales del área; fecha y hora de los datos (criterio 3).
- Se genera **a pedido** («Generar reporte») y **automáticamente** según `ConfiguracionReporte`, que el gerente edita en pantalla. La tarea
  programada existente revisa cada hora si corresponde generar uno (a lo sumo uno por periodo).
- Cada reporte se guarda con sus cifras y su PDF; se puede ver en pantalla (con estilo de impresión), descargar o imprimir. Al crearse se
  avisa a los gerentes activos (tipo `REPORTE`, con enlace).
- Acceso: solo gerente y admin; los demás roles reciben 403.

### 7.12 Plataforma independiente (RF-51)

- **Servidor de producción:** `manage.py servir` arranca la aplicación con `waitress` y sirve los estáticos con `whitenoise`; Docker lo usa
  en lugar del servidor de desarrollo (cierra la decisión abierta n.º 8 del SDD v1.0).
- **URL propia:** `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS` con el nombre interno que asigne Sistemas; `docs/despliegue.md`
  explica la instalación en un servidor Windows o Linux de CERTICOM, las copias de respaldo y el programador.
- **Acceso seguro:** además de lo existente (contraseñas validadas, cierre por inactividad, cookies seguras), tras `LOGIN_MAX_INTENTOS`
  intentos fallidos (por defecto 5) el ingreso de ese usuario desde esa dirección se bloquea `LOGIN_BLOQUEO_MINUTOS` (por defecto 15).
- **Sin salida de datos (RNF-16):** cabecera `Content-Security-Policy` con `default-src 'self'`; `form-action` y `connect-src` solo al
  propio servidor y a `FILEDOC_URL` si está configurado; `Referrer-Policy: same-origin`. Si `FILEDOC_URL` existe, el formulario de entrega
  muestra el enlace «Abrir Filedoc» cuando el medio es FileDoc.

---

## 8. Roles y permisos (se suma a los SDD anteriores)

| Acción | Junior | Senior | Gerente | Admin |
|---|---|---|---|---|
| Crear y editar etiquetas | No | Sí | Sí | Sí |
| Asignar etiquetas a un entregable | No | Sí (sus entregables) | Sí | Sí |
| Activar una alerta urgente | No | Sí (sus entregables) | Sí | Sí |
| Confirmar lectura o aceptar una alerta | Si es destinatario | Si es destinatario o senior del entregable | Sí | Sí |
| Marcar el checklist por TDR | Sí (responsable activo) | Sí (sus entregables) | Sí | Sí |
| Configurar el checklist de calidad | No | Sí (sus clientes) | Sí | Sí |
| Registrar la revisión de calidad | No | Sí (sus entregables) | Sí | Sí |
| Verificar una factura | Sí (responsable activo) | Sí | Sí | Sí |
| Justificar una factura observada | No | Sí (sus entregables) | Sí | Sí |
| Exportar a PDF o Excel | Sí (responsable activo) | Sí | Sí | Sí |
| Extraer datos de un documento | Sí (en el detalle) | Sí | Sí | Sí |
| Ver gráficos gerenciales y reportes | No | No | Sí | Sí |
| Marcar a alguien «de guardia» | No | No | Sí | Sí |

Lo que el usuario no puede ver responde 404; lo que ve pero no puede hacer, 403.

---

## 9. Interfaz

Wireframes de baja fidelidad en `docs/wireframes/sprint-3.html` (archivos `s3-*.html`). Como el equipo pidió construir sin esperar, su
aprobación queda **por ratificar** junto con las decisiones (sección 15).

| Pantalla | Tipo | Historias |
|---|---|---|
| Detalle del entregable: Etiquetas, Alerta urgente, Checklist por TDR, Checklist de calidad, Factura, Exportar, Extraer datos | Modificada | HU-23, 28, 25, 26, 30, 27, 24 |
| Nuevo entregable: etiquetas, prioridad urgente y prellenado desde un documento | Modificada | HU-23, 28, 24 |
| Tablero y lista: etiquetas, prioridad, filtro por etiqueta, orden por prioridad, diálogo de confirmación | Modificada | HU-23, 29, 25 |
| Franja «URGENTE» en todas las pantallas | Nueva | HU-28 |
| Checklists (pestaña de Entregables) | Nueva | HU-25 |
| Gestión › Etiquetas y Checklist de calidad; «de guardia» en Personal; tipo de cliente | Nuevas pestañas | HU-23, 26, 28, 29 |
| Consolidado con gráficos y pestaña Reportes | Modificada / nueva | HU-22, 31 |

Navegación (RNF-14): la barra principal **no cambia**. Todo lo nuevo vive en pestañas de pantallas existentes.

---

## 10. Rutas nuevas

| Ruta | Método | Descripción |
|---|---|---|
| `/etiquetas/`, `/etiquetas/nueva/`, `/etiquetas/<id>/` | GET, POST | Catálogo de etiquetas |
| `/entregables/<id>/etiquetas/` | POST | Asignar etiquetas al entregable |
| `/entregables/<id>/urgencia/` | POST | Activar la alerta urgente |
| `/urgencias/<id>/leer/`, `/urgencias/<id>/aceptar/` | POST | Confirmar lectura · aceptar el caso |
| `/entregables/<id>/checklist/` | POST | Generar, agregar o marcar ítems del checklist por TDR |
| `/checklists/` | GET | Consulta de checklists con filtros |
| `/calidad/` | GET, POST | Configuración del checklist de calidad |
| `/entregables/<id>/calidad/` | POST | Registrar la revisión de calidad |
| `/entregables/<id>/factura/` | POST | Verificar o justificar el número de factura |
| `/entregables/<id>/exportar/<formato>/` | POST | Exportar a `pdf` o `excel` |
| `/extraccion/nueva/`, `/extraccion/<id>/` | POST, GET/POST | Extraer datos y confirmar la vista previa |
| `/adjuntos/<id>/extraer/` | POST | Extraer datos de un adjunto del entregable |
| `/reportes/`, `/reportes/generar/`, `/reportes/<id>/`, `/reportes/<id>/pdf/` | GET, POST | Reportes de avance |

### 10.1 Configuración nueva (`.env.example`)

| Variable | Por defecto | Uso |
|---|---|---|
| `PRIORIDAD_DIAS_ESTRATEGICO` | `10` | Días para que un entregable normal de cliente Estratégico sea de prioridad Media |
| `HORARIO_LABORAL` | `1-5,09:00-18:00` | Días (1 = lunes) y horas laborales, para marcar «fuera de horario» |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_FROM` | vacío, `25`, `certitrack@localhost` | Servidor de correo **local** opcional para la alerta urgente |
| `FACTURACION_CONECTOR` | `apps.facturacion.conector.ConectorSimulado` | Conector de solo lectura a facturación |
| `TESSERACT_CMD` | `tesseract` | Programa de OCR instalado en el servidor |
| `OCR_IDIOMAS` | `spa+eng` | Idiomas de Tesseract |
| `OCR_CONFIANZA_MINIMA` | `60` | Confianza media por debajo de la cual se avisa de texto poco legible |
| `OCR_MAX_PAGINAS` | `10` | Páginas que se leen por documento |
| `FILEDOC_URL` | vacío | Único origen externo permitido |
| `LOGIN_MAX_INTENTOS`, `LOGIN_BLOQUEO_MINUTOS` | `5`, `15` | Bloqueo temporal de intentos de ingreso |
| `SERVIDOR_PUERTO`, `SERVIDOR_HILOS` | `8000`, `8` | `manage.py servir` |

---

## 11. Compatibilidad con los sprints anteriores (no regresión)

### 11.1 Lo que no se toca

Códigos de estado, transiciones, nombres de URL y rutas existentes; `entregables_visibles`; la urgencia calculada; el consolidado y sus
cifras; el asistente; las reglas de observaciones, versiones y entregas. `servicios.mover` solo gana las llamadas a las extensiones.

### 11.2 Migraciones

Todas aditivas, una por app y por hito, con reversa en las de datos. Las apps nuevas no modifican tablas de las anteriores (las relaciones
M2M de `Etiqueta` viven en su propia app).

### 11.3 Cambios deliberados que exigen ajustar pruebas existentes

| Cambio | Afecta a | Ajuste |
|---|---|---|
| Revisión de calidad conforme para aprobar (RF-45) | Pruebas y `seed_demo` que pasan a `LISTO_PARA_ENTREGA` | Ayudante `aprobar(entregable, usuario)` en `apps/entregables/testing.py`: registra una revisión de calidad conforme y llama a `mover` |
| Orden por defecto «prioridad» (RF-42) | Pruebas que comprueban el orden por defecto del tablero o la lista | Pedir `orden=plazo` de forma explícita o comprobar el orden nuevo |
| Cabecera `Content-Security-Policy` (RF-51) | El único `<script>` en línea (calendario) | Pasa a un archivo estático |

Cualquier otro cambio en una prueba anterior es una señal de regresión.

---

## 12. Plan de implementación por hitos

Al terminar cada hito: correr **todas** las pruebas, actualizar `docs/trazabilidad.md` y hacer un commit.

| Hito | Contenido | Criterio de aceptación |
|---|---|---|
| **S3-H0 — SDD, base y wireframes** | Este documento; apps nuevas registradas; puntos de extensión (5.1); ayudante `aprobar`; dependencias; wireframes | Las 868 pruebas siguen pasando con la base nueva |
| **S3-H1 — Auditoría de HU-11 y HU-13** | Sección 2; RF-40 | Cada criterio tiene una prueba que lo cubre |
| **S3-H2 — Etiquetas** | RF-41 | Un senior crea una etiqueta y un junior no; el filtro no amplía la visibilidad; la tarjeta muestra nombre y color |
| **S3-H3 — Prioridad** | RF-42 | El orden por defecto pone primero los vencidos y urgentes; cambiar un plazo cambia el nivel sin ninguna otra acción |
| **S3-H4 — Urgencias** | RF-43 | Activar avisa a guardia y responsables con «URGENTE», cliente, naturaleza y plazo; la lectura y la aceptación quedan registradas |
| **S3-H5 — Checklist por TDR** | RF-44 | Se genera desde la ficha; el % coincide; enviar con obligatorios pendientes pide confirmación |
| **S3-H6 — Checklist de calidad** | RF-45 | No se aprueba sin revisión conforme del ciclo actual; un No conforme devuelve el entregable con su observación |
| **S3-H7 — Factura** | RF-46 | Un número inexistente o de otro cliente impide aprobar hasta corregirlo o justificarlo; cada verificación queda en el historial |
| **S3-H8 — Exportación** | RF-47 | El PDF y el Excel se abren con `pypdf` y `openpyxl`; sin obligatorios no exporta; queda como versión nueva |
| **S3-H9 — Extracción (OCR)** | RF-48 | Con un motor simulado prellena y marca lo ilegible; sin Tesseract avisa y permite seguir a mano; nada se guarda sin confirmar |
| **S3-H10 — Gráficos gerenciales** | RF-49 | Un senior recibe 403; las cifras coinciden con datos preparados; el filtro aplicado se muestra |
| **S3-H11 — Reportes** | RF-50 | Se genera a pedido y por la tarea programada una sola vez por periodo; avisa al gerente; el PDF se abre |
| **S3-H12 — Plataforma independiente** | RF-51 | Ninguna plantilla ni estático apunta a otro origen; el sexto intento fallido se bloquea; `manage.py servir` arranca |
| **S3-H13 — Datos, documentación y recorrido** | `seed_demo` ampliado, guion de demostración del Sprint 3 en el README, trazabilidad, recorrido en navegador | Con la base vacía, `seed_demo --reset` deja todo demostrable y todas las pruebas pasan |

### 12.1 Datos simulados que se agregan al `seed_demo`

Siempre ficticios (RC-03): tipo de cliente en los clientes; etiquetas de las cinco líneas y dos personalizadas; una persona de guardia y
una alerta urgente abierta; checklists por TDR con avance parcial; ítems de calidad de un cliente y revisiones conformes y no conformes;
facturas simuladas (correctas, anulada y de otro cliente) y verificaciones; dos exportaciones; un reporte de avance; configuración semanal.

---

## 13. Estrategia de pruebas y trazabilidad

Casos clave nuevos (siguen la numeración del Sprint 2):

| # | Caso | Requisito |
|---|---|---|
| 31 | Solo senior, gerente y admin crean etiquetas; el filtro por etiqueta no devuelve entregables no visibles | RF-41 |
| 32 | La prioridad cambia al cambiar el plazo o el tipo de cliente, sin guardar nada; el orden por defecto es por prioridad | RF-42 |
| 33 | La alerta urgente avisa a guardia y responsables una sola vez; lectura y aceptación quedan con usuario y hora | RF-43 |
| 34 | El checklist por TDR se genera sin duplicar; el envío con obligatorios pendientes exige confirmación y queda en el historial | RF-44 |
| 35 | No se aprueba sin revisión de calidad conforme del ciclo actual; un No conforme sin observación se rechaza | RF-45 |
| 36 | Una factura inexistente, anulada o de otro cliente impide aprobar; la justificación del senior lo permite; un junior no justifica | RF-46 |
| 37 | La exportación valida obligatorios, crea una versión y sus archivos se leen con `pypdf` y `openpyxl` | RF-47 |
| 38 | La extracción no guarda nada hasta confirmar; marca lo ilegible; sin motor de OCR degrada con aviso | RF-48 |
| 39 | Los gráficos solo los ven gerente y admin y sus cifras coinciden con un conjunto conocido | RF-49 |
| 40 | El reporte automático se genera una vez por periodo y avisa al gerente; un senior no accede | RF-50 |
| 41 | Ninguna plantilla ni estático referencia otro origen; la cabecera de política de contenido está presente; el ingreso se bloquea tras los intentos fallidos | RF-51, RNF-16 |
| 42 | **Regresión:** las pruebas de los sprints 1 y 2 pasan y `migrate` funciona sobre una base del Sprint 2 | RNF-11 |

Cada historia se considera terminada cuando todos sus criterios tienen al menos una prueba y figuran en `docs/trazabilidad.md`.

---

## 14. Fuera de alcance

Conexión con el sistema real de facturación (depende de Sistemas), instalación física en el servidor de CERTICOM, notificaciones push al
teléfono, OCR de manuscritos, y edición del diseño del PDF por cliente.

---

## 15. Registro de decisiones

Tomadas el 2026-11-10 con el valor propuesto para no detener la construcción; **por ratificar por el equipo**:

| # | Decisión | Valor usado |
|---|---|---|
| D1 | Bibliotecas locales nuevas (PDF, Excel, OCR, servidor) | Sí (RNF-15) |
| D2 | Motor de OCR | Tesseract en el servidor; sin él, solo PDF con texto |
| D3 | Canal de la alerta urgente | Franja y aviso en la plataforma; correo solo con servidor local configurado |
| D4 | Grupo de guardia | Marca «de guardia» por usuario; activan senior, gerente y admin |
| D5 | Tipo de cliente | Estratégico, Regular, Ocasional |
| D8 | Checklist por TDR | Advierte y pide confirmación; no bloquea |
| D10 | Filedoc | Único origen externo, configurable; vacío por defecto |
| D11 | Plantilla del cliente en la exportación | Marcadores en un `.xlsx` del repositorio; PDF estándar |
| 7.3 | Umbrales de prioridad | Los de la sección 7.3 y `PRIORIDAD_DIAS_ESTRATEGICO` = 10 |
| 7.12 | Bloqueo de ingreso | 5 intentos, 15 minutos |

---

## 16. Pendiente fuera del repositorio

Instalar la plataforma en el servidor de CERTICOM con su nombre interno; instalar Tesseract con el idioma español; decidir con Sistemas el
conector real de facturación y la dirección de Filedoc; probar Docker y Ollama en un entorno real (pendiente desde el Sprint 1).
