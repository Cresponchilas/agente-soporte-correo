"""Ejecuta el grafo y lo transmite como Server-Sent Events.

Nunca lanza excepciones hacia el cliente a mitad del stream: si algo falla, emite
un evento "error" y cierra la transmisión de forma ordenada.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from soporte.api.eventos import TraductorDeTareas, evento_sse, mensaje_para_usuario, resumen_del_estado

logger = logging.getLogger(__name__)


def configuracion(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


async def transmitir(grafo: CompiledStateGraph, entrada: dict | Command, thread_id: str) -> AsyncIterator[str]:
    """Corre el grafo (una entrada nueva o un Command de reanudación) y emite eventos."""
    config = configuracion(thread_id)
    traductor = TraductorDeTareas()
    yield evento_sse("inicio", {"thread_id": thread_id, "reanudacion": isinstance(entrada, Command)})
    try:
        async for tarea in grafo.astream(entrada, config, stream_mode="tasks"):
            for tipo, datos in traductor.traducir(tarea):
                yield evento_sse(tipo, datos)

        instantanea = await grafo.aget_state(config)
        yield evento_sse("fin", {"thread_id": thread_id, "estado": resumen_del_estado(instantanea.values, instantanea.next)})
    except Exception as error:  # noqa: BLE001 - se informa al cliente y se registra completo en el log
        logger.exception("La corrida %s falló", thread_id)
        yield evento_sse("error", {"thread_id": thread_id, "mensaje": mensaje_para_usuario(error)})


async def esta_pausada_en_revision(grafo: CompiledStateGraph, thread_id: str) -> bool | None:
    """None si el thread no existe; True/False según si espera una decisión humana."""
    instantanea = await grafo.aget_state(configuracion(thread_id))
    if not instantanea.values:
        return None
    return "revision_humana" in instantanea.next
