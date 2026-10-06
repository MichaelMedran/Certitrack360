# Hoja de ruta (SDD §19)

La propuesta recomendada es **empezar simple y crecer por fases**: cada fase se lanza solo cuando la anterior esté en uso real.

| Fase | Contenido | Estado |
|---|---|---|
| 1 — MVP | Poka-Yoke, Kanban, calendario con alertas, adjuntos, accesos por rol, filtros y consolidado | Construida, con la interfaz de los wireframes aprobados el 2026-10-05; falta la prueba de uso con personas del equipo (ver `docs/trazabilidad.md`) |
| 2 — Conocimiento | Asistente de lecciones aprendidas, local | Construida; falta probarla contra un Ollama real |
| 3 — Optimización | Asignación automática por carga y capacitación; reportes para el gerente | **Solo visión; no implementar** |
| 4 — Expansión | Extender la herramienta a otras áreas o líneas de negocio | Visión |

## Fase 3 (visión, no implementada)

1. **Asignación automática por carga y capacitación.** Al crear un entregable, sugerir el junior del contrato con menos entregables activos y con experiencia previa en el
   tipo de plantilla o cliente. El senior confirma la sugerencia. Reutilizará el conteo de entregables activos por persona que ya calcula el consolidado.
2. **Reportes y exportación para el Gerente de Proyectos** (`apps/reportes`): entregables por estado y cliente, cumplimiento de plazos, tasa de devoluciones por tipo
   de error, carga por persona. Exportables, siempre desde el servidor local.
3. **Mejoras del asistente:** si el corpus de lecciones crece, reemplazar el índice vectorial propio por ChromaDB o pgvector.

## Fase 4 (visión)

Sumar áreas o líneas de negocio reutilizando el modelo común (clientes, contratos, plantillas configurables), los módulos que se activan uno por uno y los roles como base.

## Qué hace escalable la solución

1. Un modelo de datos común para todos los clientes, con plantillas configurables.
2. Arquitectura por módulos que se activan uno por uno.
3. Roles y permisos como base desde el inicio.
4. Historial de observaciones estructurado desde la fase 1.
5. Instalación en servidor local desde el diseño.
