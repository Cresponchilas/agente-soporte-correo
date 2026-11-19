"""Las fuentes de verdad contra las que se verifica: el catálogo (texto) y el
inventario (SQL). La verificación final y la herramienta del verificador buscan
en las dos, para poder comprobar tanto una especificación como un precio."""

from soporte.agente.estado import Fragmento
from soporte.conocimiento import rag
from soporte.datos import inventario


def todas() -> list[Fragmento]:
    # El catálogo no cambia mientras corre el proceso; el inventario sí (se recarga
    # cada día), por eso se lee en cada verificación. Son ~13 filas: es barato.
    return rag.catalogo() + inventario.fragmentos()
