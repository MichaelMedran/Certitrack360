/* Tablero Kanban: arrastrar y soltar (SortableJS) + HTMX. El servidor decide si el movimiento vale: responde con el
   tablero ya actualizado, así que una tarjeta rechazada vuelve sola a su columna y se muestra el motivo.

   HTMX reemplaza partes de la página (al filtrar, al mover y al volver con «Atrás»), por eso este script no guarda
   referencias a elementos: busca lo que necesita en el momento y se vuelve a enganchar con htmx.onLoad. */
(function () {
  "use strict";
  if (window.__tableroListo) return; // el script puede ejecutarse de nuevo al restaurar el historial: no duplicar eventos
  window.__tableroListo = true;

  function resultados() {
    return document.getElementById("resultados");
  }

  function urlMover(id) {
    // La dirección lleva los filtros actuales para que el tablero devuelto respete la misma vista.
    return resultados().dataset.moverUrl.replace("/0/", "/" + id + "/") + window.location.search;
  }

  function enviar(id, valores) {
    return htmx.ajax("POST", urlMover(id), {
      target: "#resultados", swap: "innerHTML", values: valores,
      headers: { "X-CSRFToken": resultados().dataset.csrf },
    });
  }

  function activarArrastre(raiz) {
    const zonas = Array.from(raiz.querySelectorAll ? raiz.querySelectorAll(".zona") : []);
    if (raiz.matches && raiz.matches(".zona")) zonas.push(raiz);
    zonas.forEach(function (zona) {
      if (Sortable.get(zona)) return;
      new Sortable(zona, {
        group: "tablero", animation: 120, ghostClass: "sortable-ghost", chosenClass: "sortable-chosen",
        // Arrastre por puntero (no el de HTML5): igual con ratón, pantalla táctil (tabletas) y lápiz.
        forceFallback: true, fallbackOnBody: true, fallbackTolerance: 4,
        onEnd: function (evento) {
          if (evento.from !== evento.to) enviar(evento.item.dataset.id, { estado: evento.to.dataset.estado });
        },
      });
    });
  }

  // Se llama con la página al cargar y con cada contenido nuevo que HTMX inserta (filtros, movimientos, «Atrás»).
  htmx.onLoad(activarArrastre);

  // Si la petición ni siquiera llegó al servidor, la tarjeta quedaría donde se soltó: se vuelve a pedir el tablero real.
  document.addEventListener("htmx:sendError", function () {
    if (resultados()) htmx.ajax("GET", window.location.href, { target: "#resultados", swap: "innerHTML" });
  });

  // Devolver desde «Verificación senior» exige una observación: el servidor lo pide y aquí se abre el diálogo.
  let pendiente = null;
  document.addEventListener("pedirObservacion", function (evento) {
    const dialogo = document.getElementById("dialogo-devolver");
    if (!dialogo) return;
    pendiente = evento.detail;
    document.getElementById("form-devolver").reset();
    document.getElementById("devolver-entregable").textContent = "«" + pendiente.titulo + "»";
    dialogo.showModal();
    document.getElementById("d-tipo").focus();
  });

  document.addEventListener("submit", function (evento) {
    if (evento.target.id !== "form-devolver") return;
    evento.preventDefault();
    const datos = {
      estado: "EN_PROCESO",
      tipo_error: document.getElementById("d-tipo").value,
      descripcion: document.getElementById("d-desc").value,
    };
    const id = pendiente.id;
    document.getElementById("dialogo-devolver").close();
    enviar(id, datos);
  });

  document.addEventListener("click", function (evento) {
    if (evento.target.id === "d-cancelar") document.getElementById("dialogo-devolver").close();
  });
})();
