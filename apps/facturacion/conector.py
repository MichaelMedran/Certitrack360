"""Conector de facturación de SOLO LECTURA (SDD del Sprint 3, §7.7 y RF-46).

`settings.FACTURACION_CONECTOR` apunta a la clase que consulta la facturación. El simulado lee `FacturaSimulada`; cuando
Sistemas autorice la conexión real se cambia esa variable por otra clase con el mismo contrato:

    consultar(numero) -> None (el número no existe) o un dict con «numero», «cliente», «contrato» y «estado»
                         (un valor de `FacturaSimulada.Estado`). Lanza `ErrorConexion` si no pudo consultar.

Ningún conector escribe: la plataforma nunca crea ni modifica facturas.
"""
from django.conf import settings
from django.utils.module_loading import import_string

from .models import FacturaSimulada


class ErrorConexion(Exception):
    """El sistema de facturación no respondió."""


class ConectorSimulado:
    """Lee la tabla local `FacturaSimulada`."""

    def consultar(self, numero):
        factura = FacturaSimulada.objects.filter(numero__iexact=numero).first()
        if factura is None:
            return None
        return {
            "numero": factura.numero, "cliente": factura.cliente_nombre, "contrato": factura.contrato_numero,
            "estado": factura.estado,
        }


def obtener_conector():
    """Instancia del conector configurado en `FACTURACION_CONECTOR`."""
    return import_string(settings.FACTURACION_CONECTOR)()
