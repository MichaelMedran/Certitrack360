/* Editor de campos de una plantilla: agregar, quitar, reordenar y mostrar las opciones solo en los campos de tipo «opción». */
(function () {
  "use strict";
  const cuerpo = document.getElementById("filas-campos");
  const plantilla = document.getElementById("fila-vacia");
  const agregar = document.getElementById("agregar-campo");
  if (!cuerpo || !plantilla || !agregar) return;

  function ajustarOpciones(fila) {
    const esOpcion = fila.querySelector("[name=campo_tipo]").value === "opcion";
    fila.querySelector("[name=campo_opciones]").classList.toggle("oculto", !esOpcion);
    fila.querySelector(".sin-opciones").classList.toggle("oculto", esOpcion);
  }

  cuerpo.addEventListener("change", function (evento) {
    if (evento.target.name === "campo_tipo") ajustarOpciones(evento.target.closest("tr"));
  });

  cuerpo.addEventListener("click", function (evento) {
    const boton = evento.target.closest("button[data-accion]");
    if (!boton) return;
    const fila = boton.closest("tr");
    const accion = boton.dataset.accion;
    if (accion === "quitar") {
      fila.remove();
    } else if (accion === "subir" && fila.previousElementSibling) {
      cuerpo.insertBefore(fila, fila.previousElementSibling);
      boton.focus();
    } else if (accion === "bajar" && fila.nextElementSibling) {
      cuerpo.insertBefore(fila.nextElementSibling, fila);
      boton.focus();
    }
  });

  agregar.addEventListener("click", function () {
    const fila = plantilla.content.firstElementChild.cloneNode(true);
    cuerpo.appendChild(fila);
    ajustarOpciones(fila);
    fila.querySelector("[name=campo_etiqueta]").focus();
  });

  cuerpo.querySelectorAll("tr").forEach(ajustarOpciones);
})();
