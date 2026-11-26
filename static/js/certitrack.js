/* CertiTrack — comportamiento compartido. Todo funciona sin conexión a internet. */
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

  // Los filtros del tablero y de la lista están a la vista; en pantallas angostas empiezan plegados para no tapar el contenido.
  if (window.matchMedia("(max-width: 980px)").matches) {
    document.querySelectorAll("[data-filtros-plegables]").forEach(function (panel) { panel.open = false; });
  }

  // Menú lateral en pantallas angostas: se abre con «Menú» y se cierra con Escape o al tocar fuera.
  const menu = document.getElementById("menu-lateral");
  const botonMenu = document.querySelector("[data-menu]");
  const telon = document.querySelector("[data-cerrar-menu]");
  function mostrarMenu(abrir) {
    menu.classList.toggle("abierto", abrir);
    botonMenu.setAttribute("aria-expanded", abrir ? "true" : "false");
    telon.hidden = !abrir;
    if (abrir) menu.querySelector("a").focus();
  }
  if (menu && botonMenu && telon) {
    botonMenu.addEventListener("click", function () { mostrarMenu(!menu.classList.contains("abierto")); });
    telon.addEventListener("click", function () { mostrarMenu(false); });
    document.addEventListener("keydown", function (evento) {
      if (evento.key !== "Escape" || !menu.classList.contains("abierto")) return;
      mostrarMenu(false);
      botonMenu.focus();
    });
  }

  // Formularios que piden confirmación antes de enviarse: <form data-confirmar="¿Seguro?">
  document.addEventListener("submit", function (evento) {
    const mensaje = evento.target.dataset ? evento.target.dataset.confirmar : null;
    if (mensaje && !window.confirm(mensaje)) evento.preventDefault();
  });

  // Datos de solo lectura que dependen de la opción elegida (p. ej., cliente y línea de servicio del contrato en
  // «Nuevo entregable»): <select id="x" data-reflejar> con opciones data-*, y <div data-reflejo-de="x"> con [data-dato].
  document.addEventListener("change", function (evento) {
    const control = evento.target;
    if (!control.matches || !control.matches("select[data-reflejar]")) return;
    const opcion = control.options[control.selectedIndex];
    document.querySelectorAll('[data-reflejo-de="' + control.id + '"] [data-dato]').forEach(function (salida) {
      salida.textContent = (opcion && opcion.dataset[salida.dataset.dato]) || "—";
    });
  });

  // Filas repetibles (p. ej., «+ Otra observación»): <button data-agregar-fila="id de un <template>" data-destino="id">.
  // Cada copia recibe identificadores propios (el marcador __n__ se reemplaza) para que cada etiqueta apunte a su campo.
  let filasAgregadas = 0;
  document.addEventListener("click", function (evento) {
    const boton = evento.target.closest ? evento.target.closest("[data-agregar-fila]") : null;
    if (!boton) return;
    const plantilla = document.getElementById(boton.dataset.agregarFila);
    const destino = document.getElementById(boton.dataset.destino);
    if (!plantilla || !destino) return;
    filasAgregadas += 1;
    const copia = plantilla.content.cloneNode(true);
    copia.querySelectorAll("[id], label[for]").forEach(function (elemento) {
      if (elemento.id) elemento.id = elemento.id.replace("__n__", String(filasAgregadas));
      if (elemento.htmlFor) elemento.htmlFor = elemento.htmlFor.replace("__n__", String(filasAgregadas));
    });
    destino.appendChild(copia);
    const primero = destino.lastElementChild && destino.lastElementChild.querySelector("select, textarea, input");
    if (primero) primero.focus();
  });
})();
