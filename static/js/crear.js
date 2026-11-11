/* «Nuevo entregable»: (1) la plantilla elegida recarga la pantalla y (2) al elegir el contrato se marca la etiqueta de su
   línea de servicio (RF-41). Sin JavaScript en línea: la página lo enlaza como archivo estático. */
(function () {
  "use strict";

  function lineaDelContrato(selector) {
    const caja = document.querySelector("[data-lineas-por-contrato]");
    if (!caja || !selector.value) return "";
    try {
      return String(JSON.parse(caja.dataset.lineasPorContrato)[selector.value] || "");
    } catch (error) {
      return "";
    }
  }

  function marcarEtiquetaDeLinea(selector) {
    const linea = lineaDelContrato(selector);
    document.querySelectorAll("input[name='etiquetas'][data-auto]").forEach(function (casilla) {
      casilla.checked = false; // la que se marcó sola por el contrato anterior
      delete casilla.dataset.auto;
    });
    if (!linea) return;
    document.querySelectorAll("input[name='etiquetas'][data-linea-id='" + linea + "']").forEach(function (casilla) {
      if (!casilla.checked) {
        casilla.checked = true;
        casilla.dataset.auto = "1";
      }
    });
  }

  document.addEventListener("change", function (evento) {
    const campo = evento.target;
    if (!campo.matches) return;
    if (campo.matches("select[data-autoenviar]")) {
      campo.form.submit();
    } else if (campo.matches("select[data-reflejar]")) {
      marcarEtiquetaDeLinea(campo);
    } else if (campo.matches("input[name='etiquetas']")) {
      delete campo.dataset.auto; // la persona decidió: ya no se toca
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    const selector = document.querySelector("select[data-reflejar]");
    // Al volver con errores, lo que la persona marcó se respeta; en un formulario nuevo se marca la etiqueta de la línea.
    if (selector && selector.value && !document.querySelector("input[name='etiquetas']:checked")) marcarEtiquetaDeLinea(selector);
  });
})();
