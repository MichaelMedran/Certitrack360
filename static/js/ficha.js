/* Editor de entregables de la ficha de levantamiento: agregar y quitar filas, y mostrar los campos de la plantilla elegida. */
(function () {
  "use strict";
  const cuerpo = document.getElementById("filas-items");
  const plantilla = document.getElementById("fila-item-vacia");
  const agregar = document.getElementById("agregar-item");
  if (!cuerpo || !plantilla || !agregar) return;

  function ajustarPlantilla(fila) {
    const selector = fila.querySelector("[name=item_plantilla]");
    const elegida = selector ? selector.value : "";
    fila.querySelectorAll("[data-plantilla-campos]").forEach(function (bloque) {
      bloque.classList.toggle("oculto", bloque.dataset.plantillaCampos !== elegida);
    });
  }

  cuerpo.addEventListener("change", function (evento) {
    if (evento.target.name === "item_plantilla") ajustarPlantilla(evento.target.closest("tr"));
  });

  cuerpo.addEventListener("click", function (evento) {
    const boton = evento.target.closest("button[data-accion='quitar-item']");
    if (!boton) return;
    if (cuerpo.querySelectorAll("tr").length > 1) {
      boton.closest("tr").remove();
    }
  });

  agregar.addEventListener("click", function () {
    const fila = plantilla.content.firstElementChild.cloneNode(true);
    cuerpo.appendChild(fila);
    ajustarPlantilla(fila);
    const nombre = fila.querySelector("[name=item_nombre]");
    if (nombre) nombre.focus();
  });

  cuerpo.querySelectorAll("tr").forEach(ajustarPlantilla);
})();
