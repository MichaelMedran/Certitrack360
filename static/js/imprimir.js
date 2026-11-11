/* CertiTrack 360 — botón «Imprimir» de los reportes. Sin conexión a internet y sin código en línea. */
(function () {
  "use strict";
  document.addEventListener("click", function (evento) {
    const boton = evento.target.closest("[data-imprimir]");
    if (boton) {
      evento.preventDefault();
      window.print();
    }
  });
})();
