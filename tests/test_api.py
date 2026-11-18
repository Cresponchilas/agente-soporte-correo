"""Tests de la API: contratos, streaming de eventos, reanudación y manejo de errores.
Usan el LLM falso de conftest.py, así que no gastan tokens."""

import json

import pytest
from fastapi.testclient import TestClient

from soporte import llm
from soporte.api.ajustes import Ajustes
from soporte.api.app import crear_app
from soporte.api.limites import LimitadorDeCorridas

CORREO = {"remitente": "ana.ruiz@panaderialaespiga.co", "asunto": "Facturas", "cuerpo": "¿Dónde descargo mis facturas?"}


def leer_eventos(respuesta) -> list[dict]:
    """Convierte el texto SSE en una lista de eventos (los bloques 'data: ...')."""
    return [json.loads(linea.removeprefix("data: ")) for linea in respuesta.text.splitlines() if linea.startswith("data: ")]


def tipos(eventos: list[dict]) -> list[str]:
    return [e["tipo"] for e in eventos]


@pytest.fixture
def cliente():
    with TestClient(crear_app(Ajustes(corridas_por_ip_por_hora=50, corridas_por_dia=100))) as c:
        yield c


def test_salud_indica_persistencia_en_memoria(cliente):
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json()["persistencia"] == "memoria"


def test_casos_de_prueba_disponibles(cliente):
    casos = cliente.get("/casos").json()
    assert len(casos) == 8
    assert {"id", "entrada", "esperado"} <= set(casos[0])


def test_corrida_simple_transmite_cada_nodo_y_termina(cliente, clasificacion_falsa):
    clasificacion_falsa(intencion="pregunta", urgencia="baja")
    respuesta = cliente.post("/corridas", json=CORREO)

    assert respuesta.headers["content-type"].startswith("text/event-stream")
    eventos = leer_eventos(respuesta)
    assert eventos[0]["tipo"] == "inicio" and eventos[-1]["tipo"] == "fin"
    nodos_terminados = [e["nodo"] for e in eventos if e["tipo"] == "nodo_fin"]
    assert nodos_terminados[:2] == ["recibir_correo", "clasificar"]
    assert nodos_terminados[-1] == "enviar_respuesta"
    assert all(e["duracion_ms"] >= 0 for e in eventos if e["tipo"] == "nodo_fin")
    assert eventos[-1]["estado"]["enviado"] is True


def test_corrida_urgente_pausa_y_se_reanuda_con_la_decision(cliente, clasificacion_falsa):
    clasificacion_falsa(intencion="facturacion", urgencia="alta")
    eventos = leer_eventos(cliente.post("/corridas", json=CORREO))
    assert "pausa" in tipos(eventos)
    assert eventos[-1]["estado"]["pausado_en"] == ["revision_humana"]
    thread_id = eventos[0]["thread_id"]

    eventos = leer_eventos(cliente.post(f"/corridas/{thread_id}/decision", json={"accion": "editar", "texto": "Texto final"}))
    assert eventos[0]["reanudacion"] is True
    final = eventos[-1]["estado"]
    assert final["decision_humana"] == "editado"
    assert final["borrador"] == "Texto final"
    assert final["enviado"] is True

    assert cliente.get(f"/corridas/{thread_id}").json()["estado"]["enviado"] is True


def test_decision_sobre_corrida_inexistente_da_404(cliente):
    respuesta = cliente.post("/corridas/no-existe/decision", json={"accion": "aprobar"})
    assert respuesta.status_code == 404
    assert "error" in respuesta.json()


def test_decision_sobre_corrida_terminada_da_409(cliente, clasificacion_falsa):
    clasificacion_falsa(intencion="pregunta", urgencia="baja")
    thread_id = leer_eventos(cliente.post("/corridas", json=CORREO))[0]["thread_id"]
    assert cliente.post(f"/corridas/{thread_id}/decision", json={"accion": "aprobar"}).status_code == 409


@pytest.mark.parametrize(
    "cuerpo, campo",
    [
        ({**CORREO, "remitente": "no-es-un-correo"}, "remitente"),
        ({**CORREO, "cuerpo": ""}, "cuerpo"),
        ({**CORREO, "cuerpo": "x" * 5000}, "cuerpo"),
    ],
)
def test_entrada_invalida_da_422_con_el_campo(cliente, cuerpo, campo):
    respuesta = cliente.post("/corridas", json=cuerpo)
    assert respuesta.status_code == 422
    assert respuesta.json()["detalles"][0]["campo"] == campo


def test_editar_sin_texto_da_422(cliente):
    respuesta = cliente.post("/corridas/x/decision", json={"accion": "editar"})
    assert respuesta.status_code == 422
    assert "texto" in respuesta.json()["detalles"][0]["mensaje"]


def test_fallo_del_modelo_llega_como_evento_de_error(cliente, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("detalle interno que no debe filtrarse")

    monkeypatch.setattr(llm, "clasificar_con_llm", falla)
    eventos = leer_eventos(cliente.post("/corridas", json=CORREO))

    assert eventos[-1]["tipo"] == "error"
    assert eventos[-1]["mensaje"] == "Error interno procesando el correo."
    assert "detalle interno" not in json.dumps(eventos)


def test_limite_por_ip_responde_429_con_retry_after(clasificacion_falsa):
    clasificacion_falsa()
    with TestClient(crear_app(Ajustes(corridas_por_ip_por_hora=1, corridas_por_dia=100))) as cliente:
        assert cliente.post("/corridas", json=CORREO).status_code == 200
        respuesta = cliente.post("/corridas", json=CORREO)
    assert respuesta.status_code == 429
    assert int(respuesta.headers["retry-after"]) > 0


def test_limitador_libera_cupo_cuando_pasa_la_ventana():
    reloj = [0.0]
    limitador = LimitadorDeCorridas(por_ip_por_hora=1, por_dia=10, reloj=lambda: reloj[0])
    assert limitador.intentar("1.1.1.1") is None
    assert limitador.intentar("1.1.1.1") is not None
    assert limitador.intentar("2.2.2.2") is None  # otra IP tiene su propio cupo
    reloj[0] = 3601
    assert limitador.intentar("1.1.1.1") is None
