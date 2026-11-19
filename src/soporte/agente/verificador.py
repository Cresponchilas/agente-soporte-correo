"""El verificador agente: un segundo LLM que revisa el borrador antes de enviarlo.

Elige qué afirmaciones comprobar y las busca en el catálogo con una herramienta
determinista. Lo que devuelve es solo una opinión: las reglas que la juzgan y la
decisión final están en conocimiento/verificacion.py y en el nodo verificar_respuesta.

Está hecho con `create_agent` de LangChain v1, que trae el loop de herramientas ya
resuelto. Lo que se le agrega son middlewares: código que se engancha en ese loop
para poner reglas sin tocar el agente.

    create_agent
      ├── herramienta  buscar_en_catalogo        (el "grep", sin LLM)
      ├── salida       EntregarVeredicto          (esquema Pydantic, como herramienta)
      └── middleware
            ├── ModelCallLimitMiddleware          tope de llamadas al modelo
            ├── ToolCallLimitMiddleware           tope de búsquedas
            └── exigir_lectura_antes_del_veredicto (propio, wrap_model_call)
"""

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelResponse,
    ToolCallLimitMiddleware,
    wrap_model_call,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from soporte import config
from soporte.agente import prompts
from soporte.agente.estado import EntregarVeredicto
from soporte.conocimiento import fuentes, verificacion
from soporte.conocimiento.verificacion import Busqueda, RevisionDelVerificador

# Cada llamada al modelo cuesta tiempo y dinero; sin tope, un agente que nunca
# entrega su veredicto gastaría sin fin. Al pasarse, se lanza un error y el nodo
# manda la respuesta a revisión humana.
MAXIMO_LLAMADAS = 5
# Las búsquedas no cuestan tokens de salida, pero llenan el contexto. Al pasarse,
# la herramienta deja de correr y el modelo debe entregar con lo que tiene.
MAXIMO_BUSQUEDAS = 6


class VerificadorSinVeredicto(RuntimeError):
    """El verificador terminó sin entregar un veredicto."""


@tool(response_format="content_and_artifact")
def buscar_en_catalogo(termino: str) -> tuple[str, list[str]]:
    """Busca un texto literal en el catálogo y el inventario de Andina Automatización (como
    grep) y devuelve las secciones que lo contienen, cada una con su fuente entre corchetes.
    Las secciones inventario#CÓDIGO traen precio y stock. Usa términos cortos y distintivos:
    un número de pieza (SI-M12-04P) o una palabra clave (garantía)."""
    resultado = verificacion.buscar_en_catalogo(termino, fuentes.todas())
    # content_and_artifact: el modelo lee el texto; las fuentes viajan aparte, en el
    # ToolMessage, sin pasar por el modelo. Con ellas el código valida lo que cite.
    return resultado["texto"], resultado["fuentes"]


@wrap_model_call
def exigir_lectura_antes_del_veredicto(request, handler):
    """Middleware propio: si el modelo pide búsquedas y entrega el veredicto en la misma
    vuelta, el veredicto se escribió antes de leer los resultados. Se descarta y el
    loop sigue: las búsquedas corren y el modelo vuelve a entregar con lo que leyó.

    Va en wrap_model_call (y no en after_model) porque create_agent convierte la
    llamada a EntregarVeredicto en respuesta final DENTRO de la llamada al modelo:
    para impedirlo hay que tener la llamada en la mano.
    """
    respuesta = handler(request)
    mensaje = respuesta.result[0]
    busquedas = [ll for ll in getattr(mensaje, "tool_calls", []) if ll["name"] != EntregarVeredicto.__name__]
    if respuesta.structured_response is not None and busquedas:
        return ModelResponse(result=[mensaje.model_copy(update={"tool_calls": busquedas})], structured_response=None)
    return respuesta


def construir_verificador(modelo=None):
    return create_agent(
        model=modelo or config.modelo_chat(),
        tools=[buscar_en_catalogo],
        system_prompt=prompts.VERIFICAR,
        # ToolStrategy: el veredicto es una herramienta más con el esquema Pydantic, y
        # create_agent obliga al modelo a llamar alguna herramienta en cada vuelta
        # (tool_choice="any"), así que nunca responde en texto libre. Si el veredicto
        # llega mal formado, le devuelve el error al modelo para que lo corrija.
        response_format=ToolStrategy(EntregarVeredicto),
        middleware=[
            ModelCallLimitMiddleware(run_limit=MAXIMO_LLAMADAS, exit_behavior="error"),
            ToolCallLimitMiddleware(tool_name="buscar_en_catalogo", run_limit=MAXIMO_BUSQUEDAS, exit_behavior="continue"),
            exigir_lectura_antes_del_veredicto,
        ],
        # Corre dentro de un nodo del grafo principal: no necesita guardar su propio
        # historial de checkpoints.
        checkpointer=False,
        name="verificador_agente",  # así aparece en LangSmith
    )


def revisar(cuerpo: str, borrador: str) -> RevisionDelVerificador:
    entrada = prompts.VERIFICAR_ENTRADA.format(cuerpo=cuerpo, borrador=borrador)
    resultado = construir_verificador().invoke({"messages": [{"role": "user", "content": entrada}]})
    veredicto = resultado.get("structured_response")
    if veredicto is None:
        raise VerificadorSinVeredicto("El verificador terminó sin entregar un veredicto")
    return RevisionDelVerificador(
        afirmaciones=[a.model_dump() for a in veredicto.afirmaciones],
        busquedas=busquedas_hechas(resultado["messages"]),
    )


def busquedas_hechas(mensajes: list) -> list[Busqueda]:
    """Las búsquedas que de verdad corrieron, leídas de la conversación del agente:
    el término sale de la llamada del modelo y las fuentes, del artifact del resultado.
    Una búsqueda bloqueada por el tope no trae artifact y no cuenta."""
    terminos = {
        llamada["id"]: llamada["args"].get("termino", "")
        for mensaje in mensajes
        if isinstance(mensaje, AIMessage)
        for llamada in mensaje.tool_calls
    }
    return [
        Busqueda(termino=terminos.get(m.tool_call_id, ""), fuentes=m.artifact)
        for m in mensajes
        if isinstance(m, ToolMessage) and m.name == "buscar_en_catalogo" and m.artifact is not None
    ]
