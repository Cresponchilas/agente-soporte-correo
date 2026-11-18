"""Las llamadas al LLM del proyecto: clasificar, redactar y verificar.

Están aisladas en funciones pequeñas para poder reemplazarlas en los tests
(monkeypatch) y probar el grafo sin gastar tokens.
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langsmith import traceable

from soporte import config, kb, prompts, verificacion
from soporte.state import Clasificacion, EntregarVeredicto
from soporte.verificacion import Busqueda, RevisionDelVerificador

logger = logging.getLogger(__name__)

# Tope de vueltas del verificador: cada vuelta es una llamada al modelo. Sin tope,
# un agente que nunca entrega su veredicto gastaría tokens sin fin.
MAXIMO_VUELTAS = 5


class VerificadorSinVeredicto(RuntimeError):
    """El verificador agotó sus vueltas sin entregar un veredicto."""


def clasificar_con_llm(remitente: str, asunto: str, cuerpo: str) -> Clasificacion:
    # with_structured_output liga el esquema Pydantic al modelo y valida la salida:
    # el resultado ya es un objeto Clasificacion, no texto que haya que parsear.
    modelo = config.modelo_chat().with_structured_output(Clasificacion)
    return modelo.invoke(prompts.CLASIFICAR.format(remitente=remitente, asunto=asunto, cuerpo=cuerpo))


def redactar_con_llm(prompt: str) -> str:
    return config.modelo_chat().invoke(prompt).content


# ---------- Verificador agente ----------


@tool
def buscar_en_catalogo(termino: str) -> str:
    """Busca un texto literal en el catálogo de Andina Automatización (como grep) y devuelve
    las secciones que lo contienen, cada una con su fuente entre corchetes. Usa términos
    cortos y distintivos: un número de pieza (SI-M12-04P) o una palabra clave (garantía)."""
    return verificacion.buscar_en_catalogo(termino, kb.catalogo())["texto"]


@traceable(run_type="tool", name="buscar_en_catalogo")
def _ejecutar_busqueda(termino: str) -> Busqueda:
    # Se ejecuta aquí y no con buscar_en_catalogo.invoke() para guardar también las
    # fuentes encontradas: con ellas el código valida después lo que cite el modelo.
    return verificacion.buscar_en_catalogo(termino, kb.catalogo())


@traceable(run_type="chain", name="verificador_agente")
def verificar_con_llm(cuerpo: str, borrador: str) -> RevisionDelVerificador:
    """Un agente pequeño: un loop de herramientas con tope de vueltas.

    En cada vuelta el modelo TIENE que llamar una herramienta (tool_choice="any"):
    buscar_en_catalogo para buscar, o EntregarVeredicto para terminar. Así nunca
    responde en texto libre y el veredicto siempre llega con el esquema validado.
    """
    modelo = config.modelo_chat().bind_tools([buscar_en_catalogo, EntregarVeredicto], tool_choice="any")
    mensajes = [
        SystemMessage(prompts.VERIFICAR),
        HumanMessage(prompts.VERIFICAR_ENTRADA.format(cuerpo=cuerpo, borrador=borrador)),
    ]
    busquedas: list[Busqueda] = []

    for _ in range(MAXIMO_VUELTAS):
        respuesta: AIMessage = modelo.invoke(mensajes)
        mensajes.append(respuesta)
        llamadas = respuesta.tool_calls
        busca = any(llamada["name"] == "buscar_en_catalogo" for llamada in llamadas)

        for llamada in llamadas:
            if llamada["name"] == "EntregarVeredicto" and not busca:
                veredicto = EntregarVeredicto.model_validate(llamada["args"])
                return RevisionDelVerificador(
                    afirmaciones=[a.model_dump() for a in veredicto.afirmaciones],
                    busquedas=busquedas,
                )
            mensajes.append(ToolMessage(_responder(llamada, busquedas), tool_call_id=llamada["id"]))

        if not llamadas:  # no debería pasar con tool_choice="any", pero no se asume
            mensajes.append(HumanMessage("Responde llamando a buscar_en_catalogo o a EntregarVeredicto."))

    raise VerificadorSinVeredicto(f"Sin veredicto después de {MAXIMO_VUELTAS} vueltas")


def _responder(llamada: dict, busquedas: list[Busqueda]) -> str:
    """Lo que recibe el modelo como resultado de cada herramienta que pidió."""
    if llamada["name"] == "buscar_en_catalogo":
        resultado = _ejecutar_busqueda(str(llamada["args"].get("termino", "")))
        busquedas.append(Busqueda(termino=resultado["termino"], fuentes=resultado["fuentes"]))
        return resultado["texto"]
    if llamada["name"] == "EntregarVeredicto":
        # Pidió buscar y entregar en la misma vuelta: el veredicto se escribió antes de
        # ver los resultados, así que no se acepta todavía.
        return "Todavía no: lee primero los resultados de tus búsquedas y entrega el veredicto en la siguiente vuelta."
    return f"No existe la herramienta {llamada['name']}."
