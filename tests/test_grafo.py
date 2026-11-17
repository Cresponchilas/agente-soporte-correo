"""Tests del flujo completo con LLM falso: verifican las rutas, el paralelismo
y la recuperación de errores."""

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
    assert "crear_ticket" not in resultado["pasos"]
    assert len(servicios.BANDEJA_DE_SALIDA) == 1


def test_ramas_de_contexto_corren_y_redactar_corre_una_vez(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="bug", urgencia="media")
    resultado = grafo.invoke(CORREO, config())

    pasos = resultado["pasos"]
    assert {"buscar_documentacion", "consultar_historial", "crear_ticket"} <= set(pasos)
    assert pasos.count("redactar_respuesta") == 1  # las tres ramas se juntan en un solo superstep
    assert resultado["ticket_id"].startswith("TCK-")
    assert len(resultado["fragmentos"]) == 3


def test_busqueda_fallida_no_tumba_el_grafo(grafo, clasificacion_falsa, monkeypatch):
    from soporte import kb

    clasificacion_falsa()

    def falla(*args, **kwargs):
        raise TimeoutError("vector store caído")

    monkeypatch.setattr(kb, "buscar", falla)
    resultado = grafo.invoke(CORREO, config())
    assert resultado["fragmentos"][0]["fuente"] == "error"
    assert resultado["enviado"] is True
