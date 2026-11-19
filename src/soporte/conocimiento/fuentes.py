"""Las fuentes de verdad contra las que se verifica: el catálogo (texto), el
inventario (SQL) y el grafo de equivalencias (JSON). La verificación final y la
herramienta del verificador buscan en las tres, para poder comprobar una
especificación, un precio o una equivalencia."""

from soporte.agente.estado import Fragmento
from soporte.conocimiento import grafo_de_equivalencias, rag
from soporte.datos import inventario


def todas() -> list[Fragmento]:
    # El catálogo no cambia mientras corre el proceso; el inventario sí (se recarga
    # cada día), por eso se lee en cada verificación. Son ~13 filas: es barato.
    return rag.catalogo() + inventario.fragmentos() + grafo_de_equivalencias.fragmentos_de_todo()
