# CertiTrack 360 — Guía de uso y verificación contra las entrevistas

Estado al 2026-11-11, rama `sprint-3` (Sprints 1, 2 y 3 completos, 1214 pruebas en verde).

Esta guía tiene tres partes:

1. [Cómo funciona](#1-cómo-funciona) y cómo entrar.
2. [Cómo se usa](#2-cómo-se-usa-paso-a-paso), paso a paso y por rol.
3. [Dónde está cada cosa que pidió el cliente](#3-dónde-está-cada-cosa-que-pidió-el-cliente), con el resultado de la verificación contra las entrevistas y [lo que falta](#4-lo-que-falta).

Las entrevistas se citan solo por rol (junior, senior), sin nombres de personas.

---

## 1. Cómo funciona

CertiTrack 360 es una plataforma web interna para el área de Proyectos. Sigue cada **entregable** (reporte, informe, acta) de un **contrato** de un **cliente**, desde que se registra hasta que el cliente firma el acta.

### El recorrido de un entregable

| Estado | Quién lo mueve | Qué exige la plataforma |
|---|---|---|
| **Por hacer** | Se crea a mano (senior, gerente) o sale de una ficha de levantamiento | Cliente, contrato, plantilla, ID-TDR, fecha de recepción y campos obligatorios |
| **En proceso** | Junior asignado | — |
| **Revisión senior** | Junior lo envía | Adjuntos requeridos; si el checklist del TDR tiene obligatorios pendientes, pide confirmación |
| **Listo para entrega** (aprobado) | Senior del entregable, gerente o admin | Revisión de calidad conforme y factura sin observación (o justificada) |
| **Entregado** | Senior, gerente o admin | Cargo de recepción (medio y fecha); después se sube el acta |

Si el senior observa algo, el entregable vuelve a «En proceso» con sus observaciones, y el junior registra la corrección.

### Roles

| Rol | Qué ve | Qué puede hacer |
|---|---|---|
| **Junior** | Solo lo que tiene asignado | Elaborar, subir adjuntos, corregir observaciones, enviar a revisión, redactar fichas |
| **Senior** | Los entregables de sus contratos | Crear entregables, revisar, observar, aprobar, entregar, activar urgencias, crear etiquetas |
| **Gerente** | Todo | Lo del senior, más Consolidado, Reportes y Gestión (clientes, contratos, plantillas, personal) |
| **Admin** | Todo | Lo del gerente, más el panel técnico `/admin/` |

Lo que no corresponde a un rol responde 403; lo que no puede ver, 404.

### Cómo entrar

- **Con Docker** (recomendado): `docker compose up -d --build` y abrir `http://localhost:8000/`. Levanta la web, PostgreSQL, el programador de avisos y Ollama.
- **Sin Docker**: `.\.venv\Scripts\python manage.py servir` (producción) o `runserver` (desarrollo). Los avisos de vencimiento y los reportes automáticos solo salen si además corre `manage.py programador`.
- **Datos de demostración**: `manage.py seed_demo --reset` (borra y recrea los datos de demostración). Con Docker: `docker compose exec web python manage.py seed_demo --reset`.
- **Instalación en un servidor**: ver [`despliegue.md`](despliegue.md).

Usuarios de demostración (todos ficticios, contraseña `demo1234`):

| Usuario | Rol | Para qué sirve en la demo |
|---|---|---|
| `admin_demo` | Admin | Panel técnico |
| `gerente_demo` | Gerente | Consolidado, reportes, gestión |
| `senior1` | Senior | Revisión, aprobación, entrega |
| `senior2` | Senior | Está de guardia: recibe las alertas urgentes |
| `junior1` | Junior | Elaboración y correcciones |
| `junior2` | Junior | Tiene una ausencia próxima (aviso al asignar) |
| `junior3` | Junior | Tiene un plan de incorporación activo |

Tras 5 intentos fallidos de ingreso, la cuenta queda bloqueada 15 minutos desde esa dirección.

### La barra de navegación

| Menú | Dirección | Junior | Senior | Gerente | Admin |
|---|---|---|---|---|---|
| Inicio | `/` | Sí | Sí | Sí | Sí |
| Tablero | `/tablero/` | Sí | Sí | Sí | Sí |
| Calendario | `/calendario/` | Sí | Sí | Sí | Sí |
| Entregables (pestañas: Observaciones, Entregas, Tiempos, Checklists) | `/entregables/` | Sí | Sí | Sí | Sí |
| Repositorio | `/repositorio/` | Sí | Sí | Sí | Sí |
| Indicadores | `/indicadores/` | Sí | Sí | Sí | Sí |
| Asistente | `/asistente/` | Sí | Sí | Sí | Sí |
| Buscar y Avisos | `/buscar/`, `/notificaciones/` | Sí | Sí | Sí | Sí |
| Consolidado (pestaña Reportes) | `/consolidado/`, `/reportes/` | No | No | Sí | Sí |
| Gestión (Clientes, Contratos, Plantillas, Fichas, Personal, Líneas de servicio, Etiquetas, Checklist de calidad) | `/gestion/` | No | No | Sí | Sí |
| Administración | `/admin/` | No | No | No | Sí |

Pantallas que no están en la barra de todos los roles:

- **Fichas de levantamiento** (`/fichas/`): el junior y el senior las usan, pero solo llegan por la dirección o por un aviso (ver [lo que falta](#4-lo-que-falta)).
- **Etiquetas** (`/etiquetas/`): el senior llega desde la sección «Etiquetas» del entregable.
- **Checklist de calidad** (`/calidad/`): el senior llega desde «Configurar los ítems del checklist» en el entregable.
- **Mi incorporación** (`/incorporacion/`): aparece como tarjeta en Inicio si la persona tiene un plan activo.

---

## 2. Cómo se usa, paso a paso

### 2.1 Preparar un cliente (gerente)

1. **Gestión › Clientes**: crear el cliente y su tipo (Estratégico, Regular, Ocasional). El tipo influye en la prioridad.
2. **Gestión › Contratos**: crear el contrato y su senior responsable.
3. **Gestión › Plantillas**: definir los campos obligatorios, los adjuntos requeridos y el plazo de cada tipo de entregable.
4. **Gestión › Checklist de calidad**: agregar los ítems propios del cliente (hay cuatro generales).

### 2.2 Cargar el calendario de un contrato (junior redacta, senior confirma)

1. Abrir `/fichas/nueva/` y elegir el contrato.
2. Anotar lo que pide el TDR: ítems, frecuencia (Única, Semanal, Quincenal, Mensual, Trimestral) y penalidades.
3. Revisar la vista previa del cronograma y quitar las entregas que no correspondan.
4. El senior del contrato confirma: se crean todos los entregables con su código `CT-AAAA-NNNNN`, su plazo y su checklist del TDR.

### 2.3 Registrar un entregable suelto (senior o gerente)

1. **Entregables › Nuevo entregable**.
2. Opcional: «Prellenar desde un documento» — se sube el PDF o la imagen del TDR y la plataforma propone los valores. Nada se guarda hasta confirmar.
3. Completar los campos. Si falta un obligatorio, el mensaje dice cuál.
4. En «Prioridad» elegir «Urgente» si corresponde, con naturaleza y plazo esperado.

### 2.4 Elaborar (junior)

1. **Inicio** o **Tablero**: los pendientes salen ordenados por prioridad (Alta, Media, Baja).
2. Abrir el entregable y moverlo a «En proceso».
3. Sección **Tiempo por etapa**: iniciar el cronómetro de Recopilación, Consolidación o Revisión.
4. Sección **Adjuntos y versiones**: subir el borrador. Cada subida es una versión nueva; las anteriores se conservan.
5. Sección **Checklist por TDR**: marcar cada requisito con su sustento. Se ve el % de cumplimiento.
6. Sección **Factura**: escribir el número y pulsar «Verificar».
7. Mover a «Revisión senior».

### 2.5 Revisar y aprobar (senior)

1. Sección **Checklist de calidad**: marcar cada ítem Conforme o No conforme. Un «No conforme» exige observación y devuelve el entregable.
2. Sección **Observaciones**: registrar lo que hay que corregir, con su tipo. El junior anota la corrección y el senior la confirma.
3. Si la factura salió observada, corregir el número o justificarla.
4. Mover a «Listo para entrega». Sin revisión conforme no se puede.

### 2.6 Exportar y entregar (senior)

1. Sección **Exportar**: generar el PDF o el Excel. Queda guardado como versión nueva.
2. **Marcar como entregado**: indicar el medio (correo, mesa de partes, FileDoc, presencial) y la fecha del cargo.
3. Cuando llegue el acta firmada, subirla en **Entregables › Entregas** como Recibida u Observada. Si pasan 5 días sin acta, la plataforma avisa.

### 2.7 Atender una urgencia

1. El senior o el gerente abre el entregable, sección **Alerta urgente**, y pulsa «Activar y avisar».
2. La persona de guardia y los responsables ven una franja roja «URGENTE» en todas las pantallas.
3. Cada uno pulsa «Confirmar lectura»; quien lo toma pulsa «Aceptar el caso» y la alerta se cierra.
4. La guardia se asigna en **Gestión › Personal**.

### 2.8 Seguimiento (gerente)

- **Consolidado**: cifras generales, carga por persona y cuatro gráficos con filtros por cliente, sector, contrato y fechas.
- **Consolidado › Reportes**: «Generar reporte» crea un PDF de avance. También se genera solo, con la periodicidad configurada.
- **Indicadores**: % a tiempo, % con reproceso, tiempo promedio y observaciones por tipo.
- **Gestión › Personal**: ausencias, guardia y carga. Al asignar, la plataforma avisa si la persona está sobrecargada o ausente.

### 2.9 Para todos

- **Calendario**: plazos por mes, semana o lista, con filtros.
- **Avisos**: vencimientos a 5 días, 48 h, 24 h y el día del plazo.
- **Buscar**: por código, título, ID-TDR, contrato o cliente.
- **Repositorio**: plantillas, ejemplos anonimizados y procedimientos aprobados.
- **Asistente**: preguntas en lenguaje natural; responde citando procedimientos y casos anteriores.

---

## 3. Dónde está cada cosa que pidió el cliente

Se revisaron seis documentos: dos entrevistas a juniors, una a un senior, la guía FILEKOM con respuestas, una entrevista de administración y una de contabilidad. Cada pedido se contrastó con el código, las rutas y las pruebas.

**Resultado de los 44 pedidos del área de Proyectos:** 19 se cumplen, 17 se cumplen en parte, 7 no están cubiertos y 1 quedó fuera de alcance por acuerdo.

Las entrevistas de administración y contabilidad describen otra empresa (una distribuidora), y la guía FILEKOM describe el negocio de custodia física de cajas, que opera en FileDoc. Sus 9 pedidos no se contaron; si el cliente considera que alguno debía entrar, pasa a «No cubierto».

### Plazos, calendario y alertas

| Lo que pidió | Quién | Estado | Dónde está |
|---|---|---|---|
| Un calendario único con las fechas de todos los clientes | Senior, juniors | Cumple | **Calendario** `/calendario/` |
| Alertas y recordatorios antes del vencimiento | Junior, senior | Cumple | **Avisos** `/notificaciones/` e Inicio. Requiere el programador en marcha |
| Saber qué atender primero cuando coinciden entregas | Senior, juniors | Cumple | Chip «Prioridad» en Tablero, Entregables e Inicio |
| Atender pedidos urgentes de última hora | Junior, senior | Cumple | Sección «Alerta urgente» del entregable; franja roja |
| Cada cliente con su propia frecuencia de reportes | Senior | En parte | `/fichas/nueva/`. Falta cada 2 y cada 6 meses |
| Evitar penalidades | Senior | En parte | Campo de penalidades en la ficha y alertas. No hay seguimiento de las incurridas |
| Que la alerta de madrugada llegue al celular | Senior | En parte | Solo dentro de la plataforma (y correo si hay servidor). Sin mensajería externa |

### Calidad y revisión

| Lo que pidió | Quién | Estado | Dónde está |
|---|---|---|---|
| Mantener la revisión antes de enviar al cliente | Junior, senior | Cumple | Columna «Revisión senior» del Tablero |
| Checklist de revisión por cliente | Junior | Cumple | Sección «Checklist de calidad»; configuración en `/calidad/` |
| No avanzar con información incompleta | Juniors, senior | Cumple | Validación al crear y al enviar a revisión |
| Registrar observaciones y medir reprocesos | Juniors, senior | Cumple | Sección «Observaciones»; historial en `/observaciones/` |
| Respaldo de lo entregado (acta, cargo) | Senior | Cumple | «Marcar como entregado» y `/entregas/` |
| Reemplazar un documento sin perder el anterior | Senior | Cumple | Sección «Adjuntos y versiones» |
| Verificar que la factura sea la correcta | Junior, senior | En parte | Sección «Factura». Base simulada; no compara montos |
| Detectar documentos vencidos (ISO, certificados) | Junior | En parte | Ítem manual del checklist. Sin fechas ni aviso |
| Número de caja y cantidad de movimientos correctos | Senior | No cubierto | Esos datos viven en FileDoc |

### Plantillas, reportes e indicadores

| Lo que pidió | Quién | Estado | Dónde está |
|---|---|---|---|
| Reportes e indicadores para la jefatura | Junior | Cumple | **Consolidado**, **Reportes**, **Indicadores** |
| Medir cuánto tarda cada etapa | Junior, senior | Cumple | Sección «Tiempo por etapa»; `/tiempos/` |
| Que quien recién entra no omita datos | Junior | Cumple | Campos obligatorios de la plantilla |
| Plantilla de reporte con los datos del cliente | Junior | En parte | **Gestión › Plantillas**. Sin numeración automática del n.º de reporte |
| Modelos de carta y cotización a mano | Junior | En parte | **Repositorio**. Se guardan y versionan; no se rellenan solos |
| Reducir la digitación manual | Junior, senior | En parte | «Prellenar desde un documento». El OCR de imágenes requiere instalar Tesseract |
| Entregar en el formato que pide el cliente | Senior, junior | En parte | Sección «Exportar». El Excel usa la plantilla del cliente; el PDF es estándar |
| Los seis indicadores de mejora | Senior | En parte | **Indicadores**. Falta «% de información automatizada» |
| Encontrar rápido documentos antiguos | Juniors | En parte | **Buscar**. No busca dentro del texto de los archivos |

### Sistemas e integración

| Lo que pidió | Quién | Estado | Dónde está |
|---|---|---|---|
| Perfiles de usuario y confidencialidad | Guía FILEKOM | Cumple | Cuatro roles, visibilidad por rol, bloqueo de ingreso |
| Un solo lugar en vez de correo, hojas y nube | Senior, junior | En parte | Toda la plataforma. Los pedidos del cliente siguen entrando por correo y WhatsApp |
| Integración con FileDoc y Odoo | Junior, senior | En parte | Solo un enlace «Abrir Filedoc» al entregar |
| Herramienta fácil de usar | Junior, senior | En parte | Falta la prueba de uso con personas del equipo |
| Pedidos del cliente por sistema, con guía y código | Senior | No cubierto | Es función de FileDoc |
| Reemplazar WhatsApp entre transporte y operaciones | Senior | No cubierto | CertiTrack no gestiona transporte |

### Conocimiento, personas y carga

| Lo que pidió | Quién | Estado | Dónde está |
|---|---|---|---|
| Manuales y procedimientos claros | Junior | Cumple | **Repositorio › Procedimientos** |
| Inducción para quien entra | Juniors | Cumple | Tarjeta «Mi incorporación» en Inicio |
| Resolver casos atípicos sin depender del líder | Juniors | Cumple | **Asistente**. Falta probarlo con un Ollama real |
| No depender de una sola persona | Senior | Cumple | Sección «Responsables»: apoyos y reasignación |
| Responsable, fechas y fuente claros en cada tarea | Junior | Cumple | Datos del entregable; visibles en tarjeta, lista y calendario |
| Repartir la carga | Senior | En parte | Carga por persona y aviso al asignar. No reparte sola |
| Métricas por persona | — | En parte | **Indicadores › Por responsable** |
| Consultar o escalar al senior desde la herramienta | Juniors | Fuera de alcance | Descartado por acuerdo el 2026-11-02 (HU-16) |
| Incentivos y metas | Junior, senior | No cubierto | Es política de personal, no de la plataforma |

### Licitaciones

| Lo que pidió | Quién | Estado | Dónde está |
|---|---|---|---|
| Armar y revisar propuestas | Senior | En parte | Ficha, checklist del TDR, checklist de calidad y Repositorio. Sin módulo de licitación |
| Armar constancias de experiencia | Senior | No cubierto | — |
| Costeo y viabilidad | Senior | No cubierto | — |
| Seguimiento de convocatorias | Senior | No cubierto | La plataforma no sale a internet por diseño |

---

## 4. Lo que falta

Ordenado por importancia para el cliente.

1. **Enlace a Fichas para junior y senior.** `/fichas/` es donde arranca el calendario de cada cliente, y solo está en Gestión, que ven gerente y admin.
2. **Los avisos dependen del programador.** Sin `manage.py programador` no salen avisos de vencimiento, de acta pendiente ni reportes automáticos. Con Docker ya corre como servicio.
3. **Frecuencias cada 2 y cada 6 meses.** El senior las mencionó; la ficha solo llega a Trimestral.
4. **Movimientos y cajas.** El senior señaló el número de caja equivocado como causa principal de reprocesos. Requiere decidir con el cliente si CertiTrack debe leer los movimientos de FileDoc.
5. **Facturación real.** La verificación usa una base simulada y no compara montos con el contrato. El conector real depende del área de Sistemas.
6. **Vigencia de certificados.** No hay fechas de vencimiento ni aviso.
7. **Penalidades.** Solo se anotan como texto.
8. **Alerta urgente fuera de la plataforma.** El senior usa hoy mensajería en el teléfono.
9. **Licitaciones.** Sin costeo, constancias de experiencia ni convocatorias.
10. **Sin probar en condiciones reales:** el asistente con un Ollama real, el OCR con Tesseract instalado y la prueba de uso con personas del equipo.
11. **Documentación:** la lista «Rutas principales» del README cita tres rutas del repositorio que ya no existen y describe `apps/reportes` como pendiente.

El detalle requisito por requisito, con el archivo de código y la prueba de cada uno, está en [`trazabilidad.md`](trazabilidad.md).
