"""Arma el grafo.

             START
               |
         recibir_correo
               |
           clasificar
        /      |       \\          <- arista condicional que devuelve una lista: ramas en paralelo
  buscar_doc  historial  crear_ticket (solo si bug o urgencia crítica)
        \\      |       /
       redactar_respuesta          <- Command: decide revisión humana o envío directo
          /          \\
 revision_humana --> enviar_respuesta --> END
   (interrupt)  \\--> END (rechazado)
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from soporte import nodes
from soporte.state import EstadoCorreo


def construir_grafo(checkpointer: BaseCheckpointSaver | None = None):
    builder = StateGraph(EstadoCorreo)

    builder.add_node("recibir_correo", nodes.recibir_correo)
    builder.add_node("clasificar", nodes.clasificar)
    builder.add_node("buscar_documentacion", nodes.buscar_documentacion)
    builder.add_node("consultar_historial", nodes.consultar_historial)
    builder.add_node("crear_ticket", nodes.crear_ticket)
    builder.add_node("redactar_respuesta", nodes.redactar_respuesta)
    builder.add_node("revision_humana", nodes.revision_humana)
    builder.add_node("enviar_respuesta", nodes.enviar_respuesta)

    builder.add_edge(START, "recibir_correo")
    builder.add_edge("recibir_correo", "clasificar")
    builder.add_conditional_edges("clasificar", nodes.rutas_tras_clasificar, nodes.RAMAS_DE_CONTEXTO)

    # Cada rama apunta a redactar. Como todas terminan en el mismo superstep,
    # redactar corre UNA vez, ya con la documentación, el historial y el ticket.
    for rama in nodes.RAMAS_DE_CONTEXTO:
        builder.add_edge(rama, "redactar_respuesta")

    # Las salidas de redactar_respuesta y revision_humana las crean sus Command.
    builder.add_edge("enviar_respuesta", END)

    return builder.compile(checkpointer=checkpointer)


# Para `langgraph dev` / Studio: la plataforma pone su propio checkpointer,
# por eso este grafo se compila sin uno.
graph = construir_grafo()
