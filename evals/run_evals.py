"""Evals offline en LangSmith (lo del curso Building Reliable Agents).

1. Sube data/correos_ejemplo.json como dataset (solo la primera vez).
2. Corre el grafo sobre cada ejemplo. Si se pausa en revisión humana, NO lo
   reanuda: evalúa el borrador tal como quedó.
3. Califica con tres evaluadores:
   - intencion_correcta      (código): ¿clasificó la intención esperada?
   - revision_correcta       (código): ¿pidió revisión humana cuando debía?
   - respuesta_fundamentada  (LLM juez): estrecho y binario; ¿el borrador
     afirma algo que NO está en la documentación recuperada?

    python evals/run_evals.py
"""

import json
import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client
from pydantic import BaseModel, Field

from soporte import config
from soporte.graph import construir_grafo

NOMBRE_DATASET = "agente-soporte-correo"
cliente = Client()
grafo = construir_grafo(checkpointer=InMemorySaver())


def asegurar_dataset() -> str:
    if cliente.has_dataset(dataset_name=NOMBRE_DATASET):
        return NOMBRE_DATASET
    ejemplos = json.loads((config.RAIZ / "data" / "correos_ejemplo.json").read_text(encoding="utf-8"))
    dataset = cliente.create_dataset(NOMBRE_DATASET, description="Correos de soporte con intención y revisión esperadas")
    cliente.create_examples(
        dataset_id=dataset.id,
        examples=[{"inputs": e["entrada"], "outputs": e["esperado"]} for e in ejemplos],
    )
    return NOMBRE_DATASET


def objetivo(inputs: dict) -> dict:
    """Lo que se evalúa: una corrida del grafo hasta que termina o se pausa."""
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    resultado = grafo.invoke(inputs, cfg)
    estado = grafo.get_state(cfg).values
    return {
        "clasificacion": estado.get("clasificacion"),
        "pidio_revision": "__interrupt__" in resultado,
        "borrador": estado.get("borrador", ""),
        "fragmentos": estado.get("fragmentos", []),
    }


# --- Evaluadores de código: deterministas y gratis ---

def intencion_correcta(outputs: dict, reference_outputs: dict) -> bool:
    esperada = reference_outputs["intencion"]
    validas = esperada if isinstance(esperada, list) else [esperada]
    return outputs["clasificacion"]["intencion"] in validas


def revision_correcta(outputs: dict, reference_outputs: dict) -> bool:
    return outputs["pidio_revision"] == reference_outputs["necesita_revision"]


# --- LLM como juez: una sola pregunta, respuesta binaria ---

class Veredicto(BaseModel):
    razonamiento: str = Field(description="Explicación breve, antes de decidir")
    fundamentada: bool = Field(description="True si TODO dato concreto del borrador aparece en la documentación")


PROMPT_JUEZ = """Revisas respuestas de soporte. Responde UNA sola pregunta:
¿Todos los datos concretos del borrador (plazos, montos, políticas, pasos, límites)
aparecen en la documentación? Saludos, empatía y frases como "un especialista dará
seguimiento" no cuentan como datos.

Documentación:
{documentacion}

Borrador:
{borrador}"""


def respuesta_fundamentada(outputs: dict) -> dict:
    documentacion = "\n\n".join(f["texto"] for f in outputs["fragmentos"]) or "(vacía)"
    juez = config.modelo_chat().with_structured_output(Veredicto)
    veredicto = juez.invoke(PROMPT_JUEZ.format(documentacion=documentacion, borrador=outputs["borrador"]))
    return {"key": "respuesta_fundamentada", "score": veredicto.fundamentada, "comment": veredicto.razonamiento}


if __name__ == "__main__":
    resultados = cliente.evaluate(
        objetivo,
        data=asegurar_dataset(),
        evaluators=[intencion_correcta, revision_correcta, respuesta_fundamentada],
        experiment_prefix=config.MODELO_CHAT.split(":")[-1],
        max_concurrency=2,
    )
    print("Listo. Abre el experimento en LangSmith para ver cada ejemplo y su traza.")
