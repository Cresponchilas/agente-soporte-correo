"""Arma el grafo (versión 1: flujo lineal).

START -> recibir_correo -> clasificar -> redactar_respuesta -> enviar_respuesta -> END
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from soporte import nodes
from soporte.state import EstadoCorreo


def construir_grafo(checkpointer: BaseCheckpointSaver | None = None):
    builder = StateGraph(EstadoCorreo)

    builder.add_node("recibir_correo", nodes.recibir_correo)
    builder.add_node("clasificar", nodes.clasificar)
    builder.add_node("redactar_respuesta", nodes.redactar_respuesta)
    builder.add_node("enviar_respuesta", nodes.enviar_respuesta)

    builder.add_edge(START, "recibir_correo")
    builder.add_edge("recibir_correo", "clasificar")
    builder.add_edge("clasificar", "redactar_respuesta")
    builder.add_edge("redactar_respuesta", "enviar_respuesta")
    builder.add_edge("enviar_respuesta", END)

    return builder.compile(checkpointer=checkpointer)


# Para `langgraph dev` / Studio: la plataforma pone su propio checkpointer,
# por eso este grafo se compila sin uno.
graph = construir_grafo()
