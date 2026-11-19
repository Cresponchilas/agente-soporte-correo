"""Las dos llamadas directas al LLM: clasificar y redactar.

Están aisladas en funciones pequeñas para poder reemplazarlas en los tests
(monkeypatch) y probar el grafo sin gastar tokens. El tercer uso del modelo, el
verificador agente, está en agente/verificador.py.
"""

from soporte import config
from soporte.agente import prompts
from soporte.agente.estado import Clasificacion


def clasificar_con_llm(remitente: str, asunto: str, cuerpo: str) -> Clasificacion:
    # with_structured_output liga el esquema Pydantic al modelo y valida la salida:
    # el resultado ya es un objeto Clasificacion, no texto que haya que parsear.
    modelo = config.modelo_chat().with_structured_output(Clasificacion)
    return modelo.invoke(prompts.CLASIFICAR.format(remitente=remitente, asunto=asunto, cuerpo=cuerpo))


def redactar_con_llm(prompt: str) -> str:
    return config.modelo_chat().invoke(prompt).content
