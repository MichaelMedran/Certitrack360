/* CertiTrack 360 — comportamiento compartido. Todo funciona sin conexión a internet. */
(function () {
  "use strict";

  // HTMX no guarda copias de las páginas en el almacenamiento del navegador: al volver con «Atrás» pide al servidor el
  // estado real (sin datos de la operación guardados en un equipo compartido, y sin tableros desactualizados).
  if (window.htmx) window.htmx.config.historyCacheSize = 0;

  // Las búsquedas con HTMX no deben llevar parámetros vacíos: así las direcciones quedan limpias y se pueden compartir.
  document.addEventListener("htmx:configRequest", function (evento) {
    if (evento.detail.verb !== "get") return;
    const vacios = [];
    evento.detail.formData.forEach(function (valor, clave) {
      if (valor === "") vacios.push(clave);
    });
    vacios.forEach(function (clave) {
      evento.detail.formData.delete(clave);
      delete evento.detail.parameters[clave];
    });
  });

  // El servidor responde 422 (falta algo) o 403 (sin permiso) con el tablero ya actualizado y el motivo:
  // htmx debe mostrarlo en lugar de descartarlo como si fuera un error de red.
  document.addEventListener("htmx:beforeSwap", function (evento) {
    const estado = evento.detail.xhr.status;
    if (estado === 403 || estado === 422) {
      evento.detail.shouldSwap = true;
      evento.detail.isError = false;
    }
  });

  // Los controles del panel de filtros reflejan siempre la dirección actual (al quitar un filtro, limpiar o volver atrás),
  // porque HTMX solo reemplaza los resultados y no el panel.
  function sincronizarFiltros() {
    const formulario = document.querySelector("form[data-filtros]");
    if (!formulario) return;
    const parametros = new URLSearchParams(window.location.search);
    formulario.querySelectorAll("select").forEach(function (control) {
      const valor = parametros.get(control.name);
      control.value = valor === null ? control.options[0].value : valor;
      if (control.selectedIndex < 0) control.selectedIndex = 0; // valor que no está entre las opciones
    });
  }
  document.addEventListener("htmx:afterSettle", sincronizarFiltros);
  document.addEventListener("htmx:historyRestore", sincronizarFiltros);

  // Formularios que piden confirmación antes de enviarse: <form data-confirmar="¿Seguro?">
  document.addEventListener("submit", function (evento) {
    const mensaje = evento.target.dataset ? evento.target.dataset.confirmar : null;
    if (mensaje && !window.confirm(mensaje)) evento.preventDefault();
  });
})();
