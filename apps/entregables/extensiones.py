"""Puntos de extensión del entregable (SDD del Sprint 3, §5.1 y RNF-17).

Cada módulo nuevo (etiquetas, urgencias, checklists, facturación, exportación, extracción) vive en su propia app y se
engancha aquí desde su `AppConfig.ready()`, sin editar la máquina de estados ni el detalle:

- `registrar_condicion(fn)`: `fn(entregable, nuevo_estado, usuario, opciones)` devuelve un texto (BLOQUEA el paso), una
  `Advertencia` (lo detiene solo hasta que quien mueve la confirma) o None. `servicios.mover` sigue siendo la única puerta.
- `registrar_al_mover(fn)`: `fn(entregable, anterior, nuevo, usuario, opciones)`, dentro de la transacción de `mover`,
  después de guardar el cambio y su registro del historial (`opciones["cambio"]`).
- `registrar_seccion(fn)`: `fn(usuario, entregable)` devuelve None o un dict con `plantilla` (ruta del parcial), `contexto`
  (lo recibe el parcial en la variable `s`), `orden` (entero) y `zona` («cabecera», debajo de las tarjetas de resumen, o
  «cuerpo», antes del historial; por defecto «cuerpo»).
- `registrar_tarjeta(fn)`: `fn(entregables, usuario)` agrega atributos a las tarjetas del tablero y a las filas de la lista,
  con consultas por lote (nunca una por tarjeta).

`opciones` es un dict; hoy lleva `confirmadas` (claves de las advertencias que el usuario ya confirmó).
"""
from dataclasses import dataclass

_condiciones, _al_mover, _secciones, _tarjetas = [], [], [], []


@dataclass(frozen=True)
class Advertencia:
    """Algo que conviene revisar antes de mover, pero que no lo impide: se pide una confirmación (segundo clic)."""

    clave: str
    mensaje: str


def _registrar(lista, fn):
    if fn not in lista:  # ready() puede ejecutarse más de una vez (pruebas, recarga)
        lista.append(fn)
    return fn


def registrar_condicion(fn):
    return _registrar(_condiciones, fn)


def registrar_al_mover(fn):
    return _registrar(_al_mover, fn)


def registrar_seccion(fn):
    return _registrar(_secciones, fn)


def registrar_tarjeta(fn):
    return _registrar(_tarjetas, fn)


def evaluar_condiciones(entregable, nuevo_estado, usuario, opciones):
    """(motivos que bloquean, advertencias sin confirmar), en el orden en que se registraron las condiciones."""
    confirmadas = set(opciones.get("confirmadas") or ())
    motivos, advertencias = [], []
    for fn in _condiciones:
        resultado = fn(entregable, nuevo_estado, usuario, opciones)
        if not resultado:
            continue
        if isinstance(resultado, Advertencia):
            if resultado.clave not in confirmadas:
                advertencias.append(resultado)
        else:
            motivos.append(str(resultado))
    return motivos, advertencias


def ejecutar_al_mover(entregable, anterior, nuevo, usuario, opciones):
    for fn in _al_mover:
        fn(entregable, anterior, nuevo, usuario, opciones)


def secciones(usuario, entregable):
    """Secciones del detalle que aportan los módulos, ordenadas: {"cabecera": [...], "cuerpo": [...]}."""
    salida = {"cabecera": [], "cuerpo": []}
    for fn in _secciones:
        seccion = fn(usuario, entregable)
        if seccion:
            seccion.setdefault("contexto", {})
            seccion.setdefault("orden", 100)
            salida.setdefault(seccion.get("zona") or "cuerpo", []).append(seccion)
    for lista in salida.values():
        lista.sort(key=lambda s: s["orden"])
    return salida


def enriquecer_tarjetas(entregables, usuario):
    for fn in _tarjetas:
        fn(entregables, usuario)
    return entregables
