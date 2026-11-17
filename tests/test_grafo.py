"""Tests del flujo completo con LLM falso: verifican las rutas, el paralelismo,
la pausa con interrupt y las tres decisiones humanas."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

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
    assert "revision_humana" not in resultado["pasos"]
    assert len(servicios.BANDEJA_DE_SALIDA) == 1


def test_ramas_de_contexto_corren_y_redactar_corre_una_vez(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="bug", urgencia="media")
    resultado = grafo.invoke(CORREO, config())

    pasos = resultado["pasos"]
    assert {"buscar_documentacion", "consultar_historial", "crear_ticket"} <= set(pasos)
    assert pasos.count("redactar_respuesta") == 1  # las tres ramas se juntan en un solo superstep
    assert resultado["ticket_id"].startswith("TCK-")
    assert len(resultado["fragmentos"]) == 3


def test_urgencia_alta_pausa_y_aprobar_envia(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="facturacion", urgencia="alta")
    cfg = config()
    resultado = grafo.invoke(CORREO, cfg)

    assert "__interrupt__" in resultado
    pausa = resultado["__interrupt__"][0].value
    assert pausa["borrador"] == "Hola, este es un borrador de prueba."
    assert len(servicios.BANDEJA_DE_SALIDA) == 0  # nada se envía antes de aprobar

    final = grafo.invoke(Command(resume={"accion": "aprobar"}), cfg)
    assert final["decision_humana"] == "aprobado"
    assert final["enviado"] is True


def test_editar_cambia_el_texto_enviado(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="complejo", urgencia="baja")
    cfg = config()
    grafo.invoke(CORREO, cfg)

    final = grafo.invoke(Command(resume={"accion": "editar", "texto": "Texto corregido"}), cfg)
    assert final["decision_humana"] == "editado"
    assert servicios.BANDEJA_DE_SALIDA[-1]["cuerpo"] == "Texto corregido"


def test_rechazar_no_envia(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="facturacion", urgencia="critica")
    cfg = config()
    grafo.invoke(CORREO, cfg)

    final = grafo.invoke(Command(resume={"accion": "rechazar"}), cfg)
    assert final["decision_humana"] == "rechazado"
    assert not final.get("enviado")
    assert len(servicios.BANDEJA_DE_SALIDA) == 0


def test_cliente_reincidente_va_a_revision(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="pregunta", urgencia="baja")
    correo = {**CORREO, "remitente": "carlos.mejia@ferreteriamejia.com"}  # 3 contactos previos
    resultado = grafo.invoke(correo, config())
    assert "__interrupt__" in resultado


def test_busqueda_fallida_no_tumba_el_grafo(grafo, clasificacion_falsa, monkeypatch):
    from soporte import kb

    clasificacion_falsa()

    def falla(*args, **kwargs):
        raise TimeoutError("vector store caído")

    monkeypatch.setattr(kb, "buscar", falla)
    resultado = grafo.invoke(CORREO, config())
    assert resultado["fragmentos"][0]["fuente"] == "error"
    assert resultado["enviado"] is True


def test_entrada_incompleta_da_error_claro(grafo):
    with pytest.raises(ValueError, match="remitente"):
        grafo.invoke({"asunto": "x", "cuerpo": "hola"}, config())
