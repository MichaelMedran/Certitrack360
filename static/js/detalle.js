/* Detalle del entregable: pestañas. Cada pestaña es un enlace a su sección, así que sin este script la página se lee completa.
   Los enlaces con ancla de otras pantallas (#observaciones, #tiempo, #urgencia…) abren la pestaña que contiene ese elemento. */
(function () {
  "use strict";
  const raiz = document.querySelector("[data-paneles]");
  if (!raiz) return;
  const menu = raiz.querySelector(".paneles-menu");
  const enlaces = Array.from(menu.querySelectorAll("a"));
  const CLAVE = "certitrack-panel";

  function panelDe(enlace) {
    return document.getElementById(enlace.hash.slice(1));
  }

  function activar(elegido, enfocar) {
    enlaces.forEach(function (enlace) {
      const activo = enlace === elegido;
      enlace.setAttribute("aria-selected", activo ? "true" : "false");
      enlace.tabIndex = activo ? 0 : -1;
      panelDe(enlace).hidden = !activo;
    });
    if (enfocar) elegido.focus();
  }

  function enlaceDe(elemento) {
    const panel = elemento ? elemento.closest(".panel") : null;
    return panel ? enlaces.find(function (enlace) { return panelDe(enlace) === panel; }) : null;
  }

  function irAlAncla() {
    const id = decodeURIComponent(window.location.hash.slice(1));
    const destino = id ? document.getElementById(id) : null;
    const enlace = enlaceDe(destino);
    if (!enlace) return false;
    activar(enlace);
    destino.scrollIntoView({ block: destino.classList.contains("panel") ? "nearest" : "start" });
    return true;
  }

  menu.setAttribute("role", "tablist");
  enlaces.forEach(function (enlace) {
    enlace.setAttribute("role", "tab");
    enlace.setAttribute("aria-controls", enlace.hash.slice(1));
    panelDe(enlace).setAttribute("role", "tabpanel");
  });

  menu.addEventListener("click", function (evento) {
    const enlace = evento.target.closest("a");
    if (!enlace) return;
    evento.preventDefault();
    activar(enlace);
    window.history.replaceState(null, "", enlace.hash);
  });

  menu.addEventListener("keydown", function (evento) {
    const actual = enlaces.indexOf(document.activeElement);
    if (actual < 0) return;
    const destinos = { ArrowRight: actual + 1, ArrowLeft: actual - 1, Home: 0, End: enlaces.length - 1 };
    if (!(evento.key in destinos)) return;
    evento.preventDefault();
    activar(enlaces[(destinos[evento.key] + enlaces.length) % enlaces.length], true);
  });

  // Después de guardar un formulario la página se recarga: se vuelve a la pestaña donde se estaba trabajando.
  raiz.addEventListener("submit", function (evento) {
    const enlace = enlaceDe(evento.target);
    try {
      if (enlace) window.sessionStorage.setItem(CLAVE, window.location.pathname + enlace.hash);
    } catch (e) { /* sin almacenamiento: se abre la primera pestaña */ }
  });

  // Un enlace al ancla que ya está en la dirección no dispara «hashchange»: se atiende el clic.
  document.addEventListener("click", function (evento) {
    const enlace = evento.target.closest ? evento.target.closest('a[href^="#"]') : null;
    if (!enlace || menu.contains(enlace) || !enlaceDe(document.getElementById(enlace.hash.slice(1)))) return;
    evento.preventDefault();
    window.history.replaceState(null, "", enlace.hash);
    irAlAncla();
  });
  window.addEventListener("hashchange", irAlAncla);

  let guardado = "";
  try {
    guardado = window.sessionStorage.getItem(CLAVE) || "";
    window.sessionStorage.removeItem(CLAVE);
  } catch (e) { /* sin almacenamiento */ }

  raiz.classList.add("listo");
  const pendiente = enlaceDe(raiz.querySelector("[data-abrir-panel], .errorlist"));
  if (pendiente) {
    activar(pendiente);
  } else if (!irAlAncla()) {
    activar(enlaces.find(function (enlace) { return guardado === window.location.pathname + enlace.hash; }) || enlaces[0]);
  }
})();
