"""Tests del flujo con LLM falso: no gastan tokens ni necesitan llaves."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from soporte import servicios
from soporte.graph import construir_grafo

CORREO = {"remitente": " Ana.Ruiz@panaderialaespiga.co ", "asunto": "Duda", "cuerpo": "¿Cómo descargo mis facturas?"}


@pytest.fixture
def grafo():
    servicios.BANDEJA_DE_SALIDA.clear()
    return construir_grafo(checkpointer=InMemorySaver())


def config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def test_pregunta_simple_se_envia_sin_revision(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="pregunta", urgencia="baja")
    resultado = grafo.invoke(CORREO, config())

    assert resultado["enviado"] is True
    assert "__interrupt__" not in resultado
    assert resultado["remitente"] == "ana.ruiz@panaderialaespiga.co"  # normalizado
    assert resultado["pasos"] == ["recibir_correo", "clasificar", "redactar_respuesta", "enviar_respuesta"]
    assert len(servicios.BANDEJA_DE_SALIDA) == 1

