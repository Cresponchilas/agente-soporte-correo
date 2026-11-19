"""Memoria de largo plazo: sobrevive entre hilos, solo guarda lo enviado y los
patrones los concluye el código."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from soporte import memoria
from soporte.agente.flujo import construir_grafo

REMITENTE = "compras@empacadoraelvalle.com"


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def grafo(store):
    return construir_grafo(checkpointer=InMemorySaver(), store=store)


def hilo_nuevo():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def correo(cuerpo):
    return {"remitente": REMITENTE, "asunto": "Consulta", "cuerpo": cuerpo}


def test_el_id_del_cliente_no_tiene_puntos_ni_el_correo_de_la_persona():
    assert memoria.id_cliente("Juan.Perez@Empacadora.El-Valle.com") == "empacadora_el_valle_com"


def test_un_solo_correo_no_es_un_patron():
    assert memoria.consolidar({"SI-M12-04P": 1}) == {}


def test_varias_consultas_que_coinciden_son_una_preferencia():
    assert memoria.consolidar({"SI-M12-04P": 1, "SI-M18-08P": 1}) == {"salida": "PNP"}


def test_si_las_consultas_no_coinciden_no_hay_preferencia():
    assert memoria.consolidar({"SI-M12-04P": 2, "SI-M12-04N": 1}) == {}


def test_lo_de_un_correo_se_recuerda_en_el_siguiente_hilo(grafo, clasificacion_falsa):
    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    primero = grafo.invoke(correo("¿Qué alcance tiene el SI-M12-04P?"), hilo_nuevo())
    assert primero["memoria_cliente"] == {}  # al empezar no sabía nada
    assert primero["memoria_actualizada"] == {"piezas": {"SI-M12-04P": 1}, "preferencias": {}}  # una consulta: sin patrón

    segundo = grafo.invoke(correo("¿Y el SI-M18-08P?"), hilo_nuevo())  # otro hilo: su corto plazo empieza vacío
    assert segundo["memoria_cliente"]["piezas"] == {"SI-M12-04P": 1}  # pero el Store recordaba el primero
    assert segundo["memoria_actualizada"]["preferencias"] == {"salida": "PNP"}  # dos que coinciden: ya es un patrón


def test_lo_que_ve_el_redactor_incluye_la_memoria(grafo, clasificacion_falsa, monkeypatch):
    from soporte.agente import llm

    prompts = []
    monkeypatch.setattr(llm, "redactar_con_llm", lambda prompt: prompts.append(prompt) or "Borrador.")
    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    grafo.invoke(correo("Datos del SI-M12-04P"), hilo_nuevo())
    grafo.invoke(correo("Datos del SI-M18-08P"), hilo_nuevo())
    grafo.invoke(correo("Necesito un sensor para una banda nueva"), hilo_nuevo())

    assert "Suele pedir sensores con salida PNP" in prompts[-1]


def test_una_respuesta_rechazada_no_deja_recuerdos(grafo, store, clasificacion_falsa):
    clasificacion_falsa(intencion="cotizacion", urgencia="alta")  # va a revisión
    cfg = hilo_nuevo()
    grafo.invoke(correo("Precio del SI-M12-04P"), cfg)
    grafo.invoke(Command(resume={"accion": "rechazar"}), cfg)

    assert memoria.leer(store, REMITENTE) == {}


def test_una_respuesta_aprobada_si_se_recuerda(grafo, store, clasificacion_falsa):
    clasificacion_falsa(intencion="cotizacion", urgencia="alta")
    cfg = hilo_nuevo()
    grafo.invoke(correo("Precio del SI-M12-04P"), cfg)
    grafo.invoke(Command(resume={"accion": "aprobar"}), cfg)

    assert memoria.leer(store, REMITENTE)["piezas"] == {"SI-M12-04P": 1}


def test_sin_store_el_grafo_funciona_igual(clasificacion_falsa):
    clasificacion_falsa(intencion="especificacion", urgencia="baja")
    resultado = construir_grafo(checkpointer=InMemorySaver()).invoke(correo("Datos del SI-M12-04P"), hilo_nuevo())
    assert resultado["enviado"] is True
