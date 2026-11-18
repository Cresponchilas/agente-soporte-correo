"""Tests del flujo completo con LLM falso: verifican las rutas, el paralelismo,
la pausa con interrupt y las tres decisiones humanas."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from soporte import servicios
from soporte.graph import construir_grafo

CORREO = {"remitente": " Ingenieria@IntegracionesNorte.co ", "asunto": "Duda", "cuerpo": "¿Qué alimentación tiene el SI-M18-08P?"}


@pytest.fixture
def grafo():
    servicios.BANDEJA_DE_SALIDA.clear()
    return construir_grafo(checkpointer=InMemorySaver())


def config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def test_pregunta_simple_se_envia_sin_revision(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    resultado = grafo.invoke(CORREO, config())

    assert resultado["enviado"] is True
    assert "__interrupt__" not in resultado
    assert resultado["remitente"] == "ingenieria@integracionesnorte.co"  # normalizado
    assert "crear_ticket" not in resultado["pasos"]
    assert "revision_humana" not in resultado["pasos"]
    assert len(servicios.BANDEJA_DE_SALIDA) == 1


def test_ramas_de_contexto_corren_y_redactar_corre_una_vez(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="garantia", urgencia="media")
    resultado = grafo.invoke(CORREO, config())

    pasos = resultado["pasos"]
    assert {"buscar_documentacion", "consultar_historial", "crear_ticket"} <= set(pasos)
    assert pasos.count("redactar_respuesta") == 1  # las tres ramas se juntan en un solo superstep
    assert resultado["ticket_id"].startswith("TCK-")
    assert len(resultado["fragmentos"]) == 3


def test_urgencia_alta_pausa_y_aprobar_envia(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="cotizacion", urgencia="alta")
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
    clasificacion_falsa(intencion="cotizacion", urgencia="critica")
    cfg = config()
    grafo.invoke(CORREO, cfg)

    final = grafo.invoke(Command(resume={"accion": "rechazar"}), cfg)
    assert final["decision_humana"] == "rechazado"
    assert not final.get("enviado")
    assert len(servicios.BANDEJA_DE_SALIDA) == 0


def test_cliente_reincidente_va_a_revision(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    correo = {**CORREO, "remitente": "mantenimiento@textilesandes.com"}  # 3 contactos previos
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


def test_busqueda_exacta_agrega_la_ficha_de_la_pieza_al_contexto(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    resultado = grafo.invoke(CORREO, config())  # el correo menciona el SI-M18-08P

    assert "busqueda_exacta" in resultado["pasos"]
    origen = {f["fuente"]: f["origen"] for f in resultado["contexto"]}
    assert origen["sensores-inductivos#SI-M18-08P"] in ("exacta", "ambas")
    assert resultado["verificacion"]["aprobada"] is True


def test_pieza_inexistente_pedida_por_el_cliente_va_a_revision(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="cotizacion", urgencia="baja")
    correo = {**CORREO, "cuerpo": "¿Tienen en stock el SI-M12-06P? Necesito 4."}
    resultado = grafo.invoke(correo, config())

    assert "__interrupt__" in resultado
    motivos = resultado["__interrupt__"][0].value["motivos"]
    assert motivos == ["El cliente pide SI-M12-06P, que no existe en el catálogo."]


def test_pieza_inventada_por_el_modelo_va_a_revision(grafo, clasificacion_falsa, monkeypatch):
    from soporte import llm

    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    monkeypatch.setattr(llm, "redactar_con_llm", lambda prompt: "Le sirve el SI-M18-09P, a USD 46.")
    resultado = grafo.invoke(CORREO, config())

    assert "__interrupt__" in resultado
    assert "SI-M18-09P" in " ".join(resultado["__interrupt__"][0].value["motivos"])
    assert len(servicios.BANDEJA_DE_SALIDA) == 0  # nada sale sin que una persona lo vea


def test_dato_de_otra_pieza_lo_detecta_el_verificador_agente(grafo, clasificacion_falsa, revision_falsa, monkeypatch):
    """El piso literal no lo ve (8 mm existe, pero es del SI-M18-08P); el verificador sí,
    y el código respeta su veredicto."""
    from soporte import llm

    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    monkeypatch.setattr(llm, "redactar_con_llm", lambda prompt: "El SI-M18-08P detecta a 4 mm.")
    revision_falsa(
        afirmaciones=[
            {
                "afirmacion": "El SI-M18-08P detecta a 4 mm",
                "veredicto": "contradicha",
                "fuente": "sensores-inductivos#SI-M18-08P",
                "explicacion": "La ficha dice 8 mm.",
            }
        ],
        busquedas=[{"termino": "SI-M18-08P", "fuentes": ["sensores-inductivos#SI-M18-08P"]}],
    )
    resultado = grafo.invoke(CORREO, config())

    assert "__interrupt__" in resultado
    piso = resultado["verificacion"]["afirmaciones"]
    assert all(a["estado"] != "no_encontrado" for a in piso)  # el piso solo no lo habría frenado
    assert "contradice el catálogo" in resultado["__interrupt__"][0].value["motivos"][0]


def test_si_el_verificador_falla_va_a_revision(grafo, clasificacion_falsa, monkeypatch):
    from soporte import llm

    clasificacion_falsa(intencion="especificacion", urgencia="baja")

    def falla(cuerpo, borrador):
        raise TimeoutError("el modelo no respondió")

    monkeypatch.setattr(llm, "verificar_con_llm", falla)
    resultado = grafo.invoke(CORREO, config())

    assert "__interrupt__" in resultado  # falla de forma segura: no se envía sin verificar
    assert resultado["verificacion"]["error"] == "el modelo no respondió"
    assert len(servicios.BANDEJA_DE_SALIDA) == 0
