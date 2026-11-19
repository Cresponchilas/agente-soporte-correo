"""Arma el grafo de LangGraph: el FLUJO de control del agente.

Ojo con la palabra "grafo": aquí cada nodo es un PASO del programa y cada arista
el orden en que corren. No es un grafo de conocimiento (datos y relaciones).

             START
               |
         recibir_correo
               |
           clasificar
      /     |       |       \\          <- arista condicional que devuelve una lista: ramas en paralelo
 vectorial exacta historial  ticket     (búsqueda vectorial, búsqueda exacta tipo grep, CRM, caso)
      \\     |       |       /
       redactar_respuesta              <- el LLM redacta con las dos búsquedas combinadas
               |
      verificar_respuesta              <- sin LLM: lo que dice el borrador ¿existe en el catálogo?
          /          \\                  (Command: revisión humana o envío directo)
 revision_humana --> enviar_respuesta --> END
   (interrupt)  \\--> END (rechazado)
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from soporte.agente import nodos
from soporte.agente.estado import EntradaCorreo, EstadoCorreo


def construir_grafo(checkpointer: BaseCheckpointSaver | None = None):
    # input_schema: el grafo solo acepta remitente, asunto y cuerpo como entrada;
    # el resto del estado lo llenan los nodos.
    builder = StateGraph(EstadoCorreo, input_schema=EntradaCorreo)

    builder.add_node("recibir_correo", nodos.recibir_correo)
    builder.add_node("clasificar", nodos.clasificar)
    builder.add_node("buscar_documentacion", nodos.buscar_documentacion)
    builder.add_node("consultar_historial", nodos.consultar_historial)
    builder.add_node("crear_ticket", nodos.crear_ticket)
    builder.add_node("busqueda_exacta", nodos.busqueda_exacta)
    builder.add_node("redactar_respuesta", nodos.redactar_respuesta)
    builder.add_node("verificar_respuesta", nodos.verificar_respuesta)
    builder.add_node("revision_humana", nodos.revision_humana)
    builder.add_node("enviar_respuesta", nodos.enviar_respuesta)

    builder.add_edge(START, "recibir_correo")
    builder.add_edge("recibir_correo", "clasificar")
    builder.add_conditional_edges("clasificar", nodos.rutas_tras_clasificar, nodos.RAMAS_DE_CONTEXTO)

    # Cada rama apunta a redactar. Como todas terminan en el mismo superstep,
    # redactar corre UNA vez, ya con la documentación, el historial y el ticket.
    for rama in nodos.RAMAS_DE_CONTEXTO:
        builder.add_edge(rama, "redactar_respuesta")

    builder.add_edge("redactar_respuesta", "verificar_respuesta")
    # Las salidas de verificar_respuesta y revision_humana las crean sus Command.
    builder.add_edge("enviar_respuesta", END)

    return builder.compile(checkpointer=checkpointer)


# Para `langgraph dev` / Studio: la plataforma pone su propio checkpointer,
# por eso este grafo se compila sin uno.
graph = construir_grafo()
