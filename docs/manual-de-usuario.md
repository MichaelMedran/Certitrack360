# CertiTrack 360 — Manual de uso diario

Este manual es para quien usa la plataforma todos los días: junior, senior y gerente del área de Proyectos. Explica dónde está cada cosa, para qué sirve y qué hacer en cada momento de la jornada.

Para instalar o configurar el servidor, ver [`despliegue.md`](despliegue.md). Para el detalle de qué pidió el cliente y cómo se cubre, ver [`guia-de-uso.md`](guia-de-uso.md).

---

## 1. La idea en un minuto

CertiTrack 360 sigue cada **entregable** (un reporte, un informe, un acta) desde que se registra hasta que el cliente firma el acta de conformidad. Todo entregable pertenece a un **contrato** de un **cliente** y pasa siempre por los mismos cinco estados:

| Estado | Qué significa | Quién lo mueve al siguiente |
|---|---|---|
| **Por hacer** | Está registrado y asignado, nadie lo empezó | El junior asignado |
| **En proceso** | El junior lo está elaborando o corrigiendo | El junior, al enviarlo a revisión |
| **Revisión senior** | Espera la revisión del senior | El senior: lo aprueba o lo devuelve con observaciones |
| **Listo para entrega** | Aprobado; falta enviarlo al cliente | El senior, al registrar la entrega |
| **Entregado** | Se envió al cliente; queda pendiente el acta firmada | — |

La plataforma no deja avanzar si falta algo obligatorio, y siempre dice qué falta.

### Qué ve cada rol

| Rol | Qué ve | Qué hace |
|---|---|---|
| **Junior** | Solo sus entregables asignados | Elabora, sube archivos, corrige observaciones, envía a revisión, redacta fichas |
| **Senior** | Los entregables de sus contratos | Crea entregables, revisa, observa, aprueba, entrega, activa urgencias, confirma fichas |
| **Gerente** | Todo | Lo del senior, más el seguimiento general y la configuración (Gestión) |
| **Admin** | Todo | Lo del gerente, más el panel técnico |

---

## 2. Dónde está cada cosa

La barra superior está en todas las pantallas.

| En la barra | Para qué sirve | Úselo cuando… |
|---|---|---|
| **Inicio** | Resumen personal: saludo, próximos a vencer, vencidos y avisos recientes | Empieza el día |
| **Tablero** | Sus entregables como tarjetas, en cinco columnas (una por estado), ordenadas por prioridad | Quiere ver en qué está cada cosa y mover un entregable de estado |
| **Calendario** | Los plazos de todos sus clientes por mes, semana o lista | Planifica la semana o revisa si dos entregas coinciden |
| **Entregables** | La lista completa con filtros, y sus pestañas (ver abajo) | Busca un entregable concreto o quiere crear uno |
| **Repositorio** | Plantillas de cada cliente, ejemplos anonimizados y procedimientos del área | Necesita un formato, un modelo de carta o saber cómo se hace algo |
| **Indicadores** | Cinco cifras del desempeño: a tiempo, con reproceso, tiempo promedio, observaciones e información automatizada | Quiere saber cómo va el área (o usted) |
| **Asistente** | Responde preguntas en lenguaje natural citando procedimientos y casos anteriores | Tiene un caso atípico y no sabe cómo resolverlo |
| **Fichas** (junior y senior) | Fichas de levantamiento: de aquí sale el calendario de entregas de un contrato | Llega un contrato nuevo o cambia un TDR |
| **Consolidado** (gerente) | Totales del área, carga por persona, gráficos y reportes de avance | Hace seguimiento o prepara un informe para la jefatura |
| **Gestión** (gerente) | Clientes, contratos, plantillas, fichas, personal, líneas de servicio, etiquetas, checklist de calidad y certificados | Da de alta un cliente o cambia la configuración |
| **Buscar** (caja a la derecha) | Busca por código, título, ID-TDR, contrato, cliente y dentro del texto de los archivos | Recuerda un dato pero no dónde está |
| **Avisos** (a la derecha) | Todas sus notificaciones; el número indica las que no ha leído | Ve el número en rojo |

### Las pestañas de «Entregables»

| Pestaña | Qué muestra |
|---|---|
| **Entregables** | La lista con filtros por cliente, contrato, estado, fechas y etiquetas; botón «Nuevo entregable» (senior y gerente) |
| **Observaciones** | Todas las observaciones registradas, con su tipo y si ya se corrigieron |
| **Entregas** | Historial de entregas al cliente, con el cargo y el estado del acta |
| **Tiempos** | El tiempo registrado por etapa |
| **Checklists** | El avance del checklist por TDR de cada entregable |
| **Penalidades** | Las penalidades aplicadas por los clientes, con el total general y por cliente |

### La pantalla de un entregable

Al abrir un entregable (desde el Tablero, la lista, el Calendario o un aviso) se ve todo lo suyo en una sola página. Arriba, las tarjetas con cliente, contrato, plazo, estado, urgencia, prioridad, responsables y el número de reporte. Debajo, las secciones:

| Sección | Qué se hace ahí | Quién |
|---|---|---|
| **Alerta urgente** | Activar una urgencia, confirmar que se leyó, aceptar el caso | Senior y gerente la activan; los avisados responden |
| **Mover entregable** | Pasar al siguiente estado o devolverlo | Según el estado |
| **Datos del entregable** | Los campos de la plantilla del cliente | Junior los completa |
| **Extraer datos de un documento** | Subir un PDF o imagen para que la plataforma proponga los valores | Junior y senior |
| **Checklist por TDR** | Marcar cada requisito del TDR con su sustento; muestra el % cumplido | Junior |
| **Certificados y documentos con vigencia** | Ver si algún certificado del cliente está vencido o por vencer | Todos lo ven |
| **Adjuntos y versiones** | Subir archivos; cada subida es una versión nueva y las anteriores se conservan | Junior y senior |
| **Factura** | Escribir el número de factura y verificarlo | Junior verifica; senior justifica si sale observada |
| **Tiempo por etapa** | Cronómetro de Recopilación, Consolidación y Revisión | Junior |
| **Checklist de calidad** | Marcar cada ítem Conforme o No conforme | Senior |
| **Observaciones** | Registrar lo que hay que corregir y la corrección hecha | Senior observa; junior corrige |
| **Responsables** | Sumar a alguien de apoyo o reasignar | Senior y gerente |
| **Etiquetas** | Clasificar el entregable | Senior |
| **Exportar** | Generar el PDF o el Excel con el formato del cliente | Senior |
| **Entregas y acta de conformidad** | Registrar la entrega y subir el acta firmada | Senior |
| **Penalidades** | Registrar la penalidad que aplicó el cliente; avisa si hay atraso | Senior y gerente |
| **Historial** | Todo lo que pasó con el entregable, con fecha y autor | Todos lo ven |

No todas las secciones aparecen siempre: cada una se muestra cuando aplica al estado del entregable y a su rol.

---

## 3. El día a día del junior

### Al empezar el día

1. Entre a **Inicio**. Mire primero **Vencidos** y luego **Próximos a vencer**.
2. Abra **Avisos** si tiene notificaciones sin leer. Una franja roja «URGENTE» arriba de la pantalla significa que hay una alerta urgente para usted: ábrala y pulse **Confirmar lectura**.
3. Vaya al **Tablero**. Las tarjetas vienen ordenadas por prioridad (Alta, Media, Baja): empiece por la de arriba de «Por hacer» o siga con las de «En proceso».

### Elaborar un entregable

1. Abra la tarjeta y pase el entregable a **En proceso** (sección «Mover entregable»).
2. En **Tiempo por etapa**, pulse **▶ Iniciar** en la etapa en la que está. Pause cuando lo interrumpan y finalice la etapa al terminarla.
3. Complete los **Datos del entregable**. Si tiene el TDR o un documento con los datos, use **Extraer datos de un documento**: la plataforma propone los valores y usted confirma.
4. Suba sus archivos en **Adjuntos y versiones**, eligiendo el tipo de cada uno. Si corrige un archivo, súbalo otra vez con el mismo tipo: queda como versión nueva.
5. Marque el **Checklist por TDR** conforme cumple cada requisito.
6. Mire **Certificados y documentos con vigencia**: si alguno está vencido, no lo incluya en el entregable y avise al senior.
7. En **Factura**, escriba el número y pulse **Verificar**.
8. Pase el entregable a **Revisión senior**. Si falta un adjunto obligatorio, la plataforma lo dice y no deja avanzar. Si el checklist tiene pendientes o hay un certificado vencido, pide confirmar antes de enviar.

### Cuando el senior devuelve el entregable

1. Recibirá un aviso de tipo «Observación» y el entregable volverá a **En proceso**.
2. Ábralo y lea la sección **Observaciones**: cada una dice qué corregir.
3. Corrija, suba la versión nueva y registre en cada observación qué hizo (**Enviar corrección**).
4. Vuelva a pasarlo a **Revisión senior**.

### Cuando llega un contrato nuevo

1. Entre a **Fichas › Nueva ficha** y elija el contrato.
2. Anote lo que pide el TDR: requerimientos, formatos, penalidades y cada entregable con su frecuencia (Única, Semanal, Quincenal, Mensual, Bimestral, Trimestral o Semestral) y su primera fecha.
3. Revise la vista previa del cronograma y pida la confirmación. El senior la confirma y todos los entregables se crean solos con su plazo.

### Si no sabe cómo hacer algo

- **Repositorio › Procedimientos**: los pasos aprobados del área.
- **Repositorio**: plantillas y ejemplos anonimizados de entregables anteriores.
- **Asistente**: escriba la duda como se la preguntaría a un compañero.
- Si es nuevo, la tarjeta **Mi incorporación** en Inicio le indica qué leer y practicar cada semana.

---

## 4. El día a día del senior

### Al empezar el día

1. **Inicio**: vencidos, próximos a vencer y avisos.
2. **Tablero**, columna **Revisión senior**: es lo que espera por usted.
3. **Calendario**: confirme que no coincidan dos entregas grandes en la semana.

### Revisar un entregable

1. Ábralo desde la columna «Revisión senior».
2. Revise los archivos en **Adjuntos y versiones** y el **Checklist por TDR**.
3. Complete el **Checklist de calidad**, marcando cada ítem Conforme o No conforme.
4. Si todo está bien, páselo a **Listo para entrega**. La plataforma exige la revisión de calidad conforme y la factura sin observación (o justificada).
5. Si hay algo que corregir, pulse **Devolver**, registre las observaciones con su tipo de error y el junior recibirá el aviso. Use **+ Otra observación** para registrar varias a la vez.

### Entregar al cliente

1. En **Exportar**, genere el PDF o el Excel. Queda guardado como versión nueva.
2. Pulse **Marcar como entregado**, indique el medio (correo, mesa de partes, FileDoc o presencial), la fecha y adjunte el cargo de recepción.
3. Cuando llegue el acta firmada, súbala en **Entregas y acta de conformidad** como Recibida u Observada. Si pasan 5 días sin acta, la plataforma se lo recuerda.
4. Si el cliente aplicó una penalidad, regístrela en la sección **Penalidades**.

### Registrar un entregable suelto

1. **Entregables › Nuevo entregable** y elija la plantilla.
2. Opcional: **Prellenar desde un documento** para no digitar los datos.
3. Elija el junior: junto a cada nombre se ve cuántos entregables activos tiene. Si está sobrecargado o ausente, la plataforma avisa.
4. Si es urgente, marque la prioridad **Urgente** e indique la naturaleza y el plazo esperado.

### Atender una urgencia fuera de horario

1. Abra el entregable, sección **Alerta urgente**, y pulse **Activar y avisar**.
2. La persona de guardia y los responsables ven la franja roja en todas sus pantallas (y reciben el WhatsApp, si está activado).
3. Cada avisado pulsa **Confirmar lectura**; quien lo toma pulsa **Aceptar el caso** y la alerta se cierra.

### Otras tareas del senior

- **Confirmar fichas**: un aviso de tipo «Ficha» lo lleva a la ficha que redactó el junior; revísela y confírmela.
- **Certificados del cliente**: desde la sección del entregable, **Registrar o renovar documentos**. Registre cada certificado con su fecha de vencimiento; la plataforma avisa 30 días antes y el día en que vence.
- **Sumar apoyo o reasignar**: sección **Responsables** del entregable.

---

## 5. El día a día del gerente

| Para… | Vaya a… |
|---|---|
| Ver cómo va toda el área | **Consolidado**: totales, vencidos, próximos a vencer, carga por persona y gráficos con filtros |
| Tener un informe para la jefatura | **Consolidado › Reportes › Generar reporte** (PDF). También se genera solo con la periodicidad configurada |
| Medir el desempeño | **Indicadores**, con filtros por fechas, cliente, tipo de entregable y responsable |
| Saber cuánto se pagó en penalidades | **Entregables › Penalidades** |
| Revisar la carga y las ausencias | **Gestión › Personal**: activos, vencimientos en 7 días, ausencias y sobrecarga |
| Definir quién está de guardia | **Gestión › Personal**, columna «De guardia» |
| Registrar el celular de alguien para WhatsApp | **Gestión › Personal**, abra al colaborador y complete «Celular para avisos por WhatsApp» |
| Dar de alta un cliente | **Gestión › Clientes**, luego **Contratos**, **Plantillas** y **Checklist de calidad** |
| Registrar certificados de un cliente | **Gestión › Certificados** |
| Acompañar a alguien nuevo | **Gestión › Personal**, planes de incorporación |

---

## 6. Los avisos

Los avisos llegan solos a **Avisos** (y al WhatsApp del colaborador, si el administrador lo activó y registró su celular).

| Aviso | Cuándo llega | A quién |
|---|---|---|
| **Vencimiento** | 5 días, 48 horas y 24 horas antes del plazo, y el mismo día | Junior asignado y senior revisor |
| **Asignación** | Se le asigna un entregable | Junior |
| **Verificación** | Un entregable pasa a Revisión senior | Senior |
| **Observación** | El senior devuelve un entregable | Junior |
| **Corrección** | El junior registró lo que corrigió | Senior |
| **Acta** | Pasaron 5 días desde la entrega sin acta firmada | Junior y senior |
| **Urgente** | Se activó una alerta urgente | Guardia y responsables |
| **Ficha** | Una ficha espera confirmación | Senior del contrato |
| **Vigencia** | Un certificado del cliente vence en 30 días o ya venció | Senior del contrato y gerentes |
| **Reporte** | Se generó un reporte de avance | Gerentes |

Pulse **Ver** en un aviso para ir directo a lo que hay que atender.

---

## 7. ¿Cómo hago para…?

| Quiero… | Hago esto |
|---|---|
| Saber qué atender primero | **Tablero**: la tarjeta de más arriba en cada columna es la de mayor prioridad |
| Encontrar un entregable antiguo | **Buscar** con el código, el título, el ID-TDR o una palabra del contenido de sus archivos |
| Recuperar una versión anterior de un archivo | Entregable › **Adjuntos y versiones** › «Versiones» del archivo |
| Reemplazar un documento | Súbalo de nuevo con el mismo tipo; la anterior se conserva |
| Ver por qué me devolvieron algo | Entregable › **Observaciones** |
| Saber quién movió un entregable y cuándo | Entregable › **Historial** |
| Ver todas las fechas del mes | **Calendario**, vista de mes, con filtro por cliente |
| Conseguir el formato de un cliente | **Repositorio**, filtrando por cliente |
| Entregar con el formato del cliente | Entregable › **Exportar** › Excel |
| Saber si un certificado del cliente está vigente | Entregable › **Certificados y documentos con vigencia** |
| Saber qué número de reporte toca | Está en la tarjeta «ID-TDR · Línea» del entregable; sale solo |
| Pedir ayuda con la carga | Avise a su senior: él suma a alguien de apoyo en **Responsables** |
| Registrar que estaré ausente | Lo registra el gerente en **Gestión › Personal** |

---

## 8. Reglas que conviene recordar

- **Nada se pierde:** cada archivo subido es una versión y cada cambio queda en el historial.
- **Lo que no ve, no le corresponde:** si un enlace responde «no encontrado», el entregable no es de sus contratos.
- **La plataforma bloquea o advierte:** un bloqueo dice qué falta y hay que completarlo; una advertencia pide confirmar («Continuar de todos modos»).
- **La sesión se cierra sola** tras 60 minutos sin actividad. Tras 5 intentos fallidos de ingreso, la cuenta se bloquea 15 minutos.
- **Los pedidos del cliente siguen llegando por correo o WhatsApp:** regístrelos como entregable para que entren al calendario y a las alertas.
